"""
Autofix validation: apply search/replace edits safely, policy checks, minimal re-score.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

RISK_SCORER_URL = os.getenv("RISK_SCORER_SERVICE_URL", "http://localhost:8003")
PARSER_SERVICE_URL = os.getenv("PARSER_SERVICE_URL", "http://localhost:8001")
GRAPH_ENGINE_SERVICE_URL = os.getenv("GRAPH_ENGINE_SERVICE_URL", "http://localhost:8002")
ALLOW_PLACEHOLDER_RESOURCES = os.getenv("ALLOW_PLACEHOLDER_RESOURCES", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

GRAPH_DEPENDENT_FINDING_TYPES = frozenset(
    {
        "INTERNET_EXPOSED_ADMIN_EC2",
        "PRIVILEGED_EC2_TO_SENSITIVE_DB",
        "PUBLIC_CHAIN_TO_DATABASE",
        "OVERPERMISSIVE_SG_CHAIN",
        "CROSS_AZ_REPLICATION_EXPOSURE",
        "LATERAL_MOVEMENT_VIA_SG",
    }
)


def canonical_rel_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def resolve_path_to_snapshot_key(requested: str, snapshot_keys: list[str]) -> str | None:
    """
    Map model/edit paths like 'insecure.tf' or './terraform/foo.tf' onto a key in the scan snapshot.
    """
    if not requested or not snapshot_keys:
        return None
    cand = canonical_rel_path(requested)
    normalized_keys = {canonical_rel_path(k): k for k in snapshot_keys}
    if cand in normalized_keys:
        return normalized_keys[cand]
    basename = cand.split("/")[-1]
    matches = [k for k in snapshot_keys if canonical_rel_path(k).endswith(basename)]
    if len(matches) == 1:
        return matches[0]
    for k in snapshot_keys:
        nk = canonical_rel_path(k)
        if nk.endswith("/" + cand) or nk.endswith("/" + basename):
            return k
    return None


def _normalize_parser_base(raw: str) -> str:
    base = raw.strip().rstrip("/")
    if base.lower().endswith("/api"):
        base = base[:-4].rstrip("/")
    return base


def _build_graph_resource(resource: dict[str, Any]) -> dict[str, Any]:
    """Mirror of services/api/main._build_graph_resource (avoid circular imports)."""
    inbound = resource.get("inbound_rules", [])
    rules = []
    for rule in inbound:
        try:
            port = int(str(rule.get("port", "0")).split("-")[0])
        except (ValueError, TypeError):
            port = 0
        rules.append(
            {
                "port": port,
                "protocol": str(rule.get("protocol", "tcp")),
                "cidr": str(rule.get("cidr", "0.0.0.0/0")),
            }
        )

    resource_type = resource.get("resource_type", "")
    normalized_type = (
        resource_type.replace("aws_", "").replace("kubernetes_", "").replace("aws_", "")
    )
    if normalized_type == "instance":
        normalized_type = "ec2_instance"
    return {
        "resource_id": resource.get("resource_id"),
        "type": normalized_type,
        "provider": resource.get("provider", "unknown"),
        "rules": rules,
    }


def apply_edits(
    file_map: dict[str, str],
    edits: list[dict[str, Any]],
) -> tuple[dict[str, str], list[str]]:
    """Validate edits, then apply all-or-nothing."""
    errors: list[str] = []
    snapshot_keys = list(file_map.keys())

    validated: list[tuple[str, str, str, bool]] = []
    for e in edits or []:
        raw_path = str(e.get("path", "")).strip()
        path = resolve_path_to_snapshot_key(raw_path, snapshot_keys) or raw_path
        search = e.get("search")
        replace = e.get("replace")

        if not raw_path:
            errors.append("Edit missing path")
            continue

        if path not in file_map:
            errors.append(
                f"Unknown file path '{raw_path}' (resolved '{path}'). Allowed paths: {snapshot_keys}"
            )
            continue

        if search is None or replace is None:
            errors.append(f"Missing search/replace for {path}")
            continue

        if not isinstance(search, str) or not isinstance(replace, str):
            errors.append(f"search/replace must be strings for {path}")
            continue

        content = file_map[path]
        count = content.count(search)
        if count == 0:
            errors.append(f"search substring not found in '{path}'")
            continue
        replace_all = False
        if count != 1:
            # Allow repeated replacements only when search is specific enough.
            # This avoids brittle model output that targets common short tokens.
            if len(search.strip()) < 8:
                errors.append(f"'{path}' search is too short for multi-match replace, found {count}")
                continue
            replace_all = True

        risky = _dangerous_wide_open(replace, search)
        if risky:
            errors.append(f"Rejected risky edit on {path}: {risky}")
            continue

        validated.append((path, search, replace, replace_all))

    if errors:
        return dict(file_map), errors

    new_map = dict(file_map)
    for path, search, replace, replace_all in validated:
        if replace_all:
            new_map[path] = new_map[path].replace(search, replace)
        else:
            new_map[path] = new_map[path].replace(search, replace, 1)

    return new_map, []


def _dangerous_wide_open(new_text: str, old_text: str) -> Optional[str]:
    """Block obvious widenings toward public internet."""
    needle = "0.0.0.0/0"
    if needle in new_text and needle not in old_text:
        return "replacing adds 0.0.0.0/0 (possible over-exposure)"
    if not ALLOW_PLACEHOLDER_RESOURCES and _looks_like_placeholder_resource(new_text):
        return "replacement includes placeholder resource identifiers (possible hallucinated infra)"
    return None


def _looks_like_placeholder_resource(text: str) -> bool:
    lowered = text.lower()
    return (
        "123456789012" in text
        or "arn:aws:kms:" in lowered
        or "00000000-0000-0000-0000-000000000000" in lowered
    )


def policy_denies_edits(edits: list[dict[str, Any]]) -> list[str]:
    """Aggregate policy checks."""
    err: list[str] = []
    for e in edits or []:
        s = str(e.get("replace", "") or "")
        o = str(e.get("search", "") or "")
        r = _dangerous_wide_open(s, o)
        if r:
            err.append(str(e.get("path", "?")) + ": " + r)
    return err


def validate_patched_terraform_syntax(file_map: dict[str, str]) -> list[str]:
    """Cheap local parse gate so malformed LLM Terraform fails before downstream HTTP parses."""
    try:
        import hcl2
    except ImportError:
        return []
    errs: list[str] = []
    for path, body in sorted(file_map.items()):
        if not path.endswith(".tf"):
            continue
        try:
            hcl2.loads(body)
        except Exception as exc:
            errs.append(f"Patched Terraform is invalid syntax in '{path}': {exc}")
    return errs


def validate_aws_security_group_rule_blocks(file_map: dict[str, str]) -> list[str]:
    """
    Reject patched SGs whose ingress blocks omit ports (would parse as port 0 / all-ports)
    or still declare 0-65535 on ingress.
    """
    try:
        import hcl2
    except ImportError:
        return []
    errs: list[str] = []
    for path, body in sorted(file_map.items()):
        if not path.endswith(".tf"):
            continue
        try:
            data = hcl2.loads(body)
        except Exception:
            continue
        for res_group in data.get("resource") or []:
            if not isinstance(res_group, dict):
                continue
            for raw_rtype, instances in res_group.items():
                if raw_rtype == "__is_block__":
                    continue
                rtype_label = str(raw_rtype).strip().strip('"').split("${", 1)[0]
                if rtype_label != "aws_security_group":
                    continue
                if not isinstance(instances, dict):
                    continue
                for raw_name, values in instances.items():
                    if raw_name == "__is_block__":
                        continue
                    if not isinstance(values, dict):
                        continue
                    name_clean = str(raw_name).strip().strip('"').split("${", 1)[0]
                    rid = f"aws_security_group.{name_clean}"
                    ingress = values.get("ingress")
                    if not isinstance(ingress, list):
                        continue
                    for idx, block in enumerate(ingress):
                        if not isinstance(block, dict):
                            continue
                        if "from_port" not in block or "to_port" not in block:
                            errs.append(
                                f"'{path}' {rid} ingress block #{idx + 1}: "
                                f"missing from_port/to_port — do not delete them; narrow the port range."
                            )
                            continue
                        fp, tp = block.get("from_port"), block.get("to_port")
                        try:
                            fpi, tpi = int(fp), int(tp)
                        except (TypeError, ValueError):
                            continue
                        if fpi == 0 and tpi == 65535:
                            errs.append(
                                f"'{path}' {rid} ingress block #{idx + 1}: "
                                f"still allows all ports (0-65535); replace with specific ports only."
                            )
    return errs


def parse_snapshot_to_resources(client: httpx.Client, file_map: dict[str, str]) -> list[dict[str, Any]]:
    resources: list[dict[str, Any]] = []
    base = _normalize_parser_base(PARSER_SERVICE_URL)
    parser_endpoints = [f"{base}/parse", f"{base}/api/parse"]
    for filename, body in sorted(file_map.items()):
        payload: dict[str, Any] | None = None
        last_exc: httpx.HTTPError | None = None
        for endpoint in parser_endpoints:
            try:
                resp = client.post(endpoint, files={"file": (filename, body)})
                resp.raise_for_status()
                payload = resp.json()
                break
            except httpx.HTTPStatusError as exc:
                # Some deployments expose /parse, others /api/parse.
                if exc.response is not None and exc.response.status_code == 404:
                    last_exc = exc
                    continue
                detail = ""
                if exc.response is not None:
                    try:
                        payload_j = exc.response.json()
                        if isinstance(payload_j, dict):
                            det = payload_j.get("detail")
                            if isinstance(det, dict):
                                detail = str(det)
                            else:
                                detail = repr(det)
                    except ValueError:
                        detail = (exc.response.text[:500]).strip()
                    msg = (
                        f"Client error '{exc.response.status_code} "
                        f"{exc.response.reason_phrase}' for url '{exc.request.url}'."
                    )
                    if detail:
                        msg += f" Detail: {detail}"
                    raise RuntimeError(msg) from exc
                raise

        if payload is None:
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("Parser returned no payload")
        resources.extend(payload.get("resources") or [])
    return resources


def run_rescore_same_files(
    file_map_after: dict[str, str],
    original_resource_id: str,
    original_finding_type: str,
) -> tuple[bool, str, Optional[list[dict[str, Any]]]]:
    """Re-parse snapshot and call risk scorer with empty graph_context — MVP regression."""

    gc = {"nodes": [], "edges": [], "newly_exposed": [], "exposure_delta": 0}

    with httpx.Client(timeout=120.0) as client:
        try:
            resources = parse_snapshot_to_resources(client, file_map_after)
        except (httpx.HTTPError, RuntimeError) as exc:
            return False, f"Parser unreachable or failed after patch: {exc}", None

        if not resources:
            return False, "Parser produced no resources from patched snapshot", None

        try:
            gr = client.post(
                f"{GRAPH_ENGINE_SERVICE_URL}/graph/build",
                json={
                    "resources": [_build_graph_resource(r) for r in resources],
                },
            )
            gr.raise_for_status()
            head = gr.json()

            gc = {
                "nodes": head.get("nodes") or [],
                "edges": head.get("edges") or [],
                "newly_exposed": [],
                "exposure_delta": 0,
            }

            score = client.post(
                f"{RISK_SCORER_URL}/score",
                json={"resources": resources, "graph_context": gc},
            )
            score.raise_for_status()
            findings = score.json().get("findings") or []
        except httpx.HTTPError as exc:
            return False, f"Graph/risk scorer failed after patch: {exc}", None

    for finding in findings:
        if finding.get("resource_id") != original_resource_id:
            continue
        if finding.get("finding_type") == original_finding_type:
            return False, "Original finding still present after patched re-scan", findings

    return True, "Original finding absent in patched re-scan", findings
