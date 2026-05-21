"""Deterministic (no-LLM) IaC security fixes for common Terraform finding types.

Handles SSH_EXPOSED_TO_PUBLIC, RDP_EXPOSED_TO_PUBLIC, ALL_PORTS_OPEN,
PUBLIC_DB_PORT_EXPOSED, UNENCRYPTED_STORAGE.  MISSING_TAGS is handled by
missing_tags_fix.py but is also dispatched from here.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

from .missing_tags_fix import (
    _find_matching_brace,
    _locate_resource_block,
    apply_missing_tags_terraform,
    canonical_basename,
)

_DB_PORTS = {5432, 3306, 1433, 27017, 6379, 5984}

_INGRESS_HEAD = re.compile(r"^(\s*)ingress\s*\{", re.MULTILINE)

_CIDR_OPEN = re.compile(r'"0\.0\.0\.0/0"')


def _resolve_source_path(file_map: dict[str, str], source_file: str) -> str | None:
    """Find the snapshot key matching source_file."""
    if source_file in file_map:
        return source_file
    bn = canonical_basename(source_file)
    cands = [k for k in file_map if k.endswith("/" + bn) or canonical_basename(k) == bn]
    return cands[0] if len(cands) == 1 else None


def _find_ingress_blocks(block_text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of ``ingress { ... }`` sub-blocks."""
    results: list[tuple[int, int]] = []
    for m in _INGRESS_HEAD.finditer(block_text):
        brace = block_text.find("{", m.end() - 1)
        if brace < 0:
            continue
        close = _find_matching_brace(block_text, brace)
        if close < 0:
            continue
        results.append((m.start(), close + 1))
    return results


def _extract_int(text: str, key: str) -> int | None:
    m = re.search(rf"{key}\s*=\s*(-?\d+)", text)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _has_open_cidr(text: str) -> bool:
    return bool(_CIDR_OPEN.search(text))


def _replace_open_cidr(text: str, replacement: str) -> str:
    return _CIDR_OPEN.sub(f'"{replacement}"', text)


# ---------------------------------------------------------------------------
# Individual finding-type fixers
# ---------------------------------------------------------------------------

def _fix_ssh_rdp(content: str, resource_id: str, port: int) -> tuple[str, bool, str]:
    """Restrict 0.0.0.0/0 → 10.0.0.0/8 on SSH (22) or RDP (3389) ingress."""
    parts = resource_id.split(".", 1)
    if len(parts) != 2:
        return content, False, ""
    span = _locate_resource_block(content, parts[0], parts[1])
    if span is None:
        return content, False, ""
    start, end = span
    block = content[start:end]
    changed = False
    for sb_s, sb_e in reversed(_find_ingress_blocks(block)):
        sub = block[sb_s:sb_e]
        fp = _extract_int(sub, "from_port")
        if fp != port:
            continue
        if not _has_open_cidr(sub):
            continue
        block = block[:sb_s] + _replace_open_cidr(sub, "10.0.0.0/8") + block[sb_e:]
        changed = True
    if not changed:
        return content, False, ""
    proto = "SSH" if port == 22 else "RDP"
    return (
        content[:start] + block + content[end:],
        True,
        f"Restricted {proto} (port {port}) ingress from 0.0.0.0/0 to 10.0.0.0/8 (private network).",
    )


def _fix_all_ports_open(content: str, resource_id: str) -> tuple[str, bool, str]:
    """Narrow 0-65535 ingress to port 443 only and restrict CIDR."""
    parts = resource_id.split(".", 1)
    if len(parts) != 2:
        return content, False, ""
    span = _locate_resource_block(content, parts[0], parts[1])
    if span is None:
        return content, False, ""
    start, end = span
    block = content[start:end]
    changed = False
    for sb_s, sb_e in reversed(_find_ingress_blocks(block)):
        sub = block[sb_s:sb_e]
        fp = _extract_int(sub, "from_port")
        tp = _extract_int(sub, "to_port")
        if fp == 0 and tp == 65535:
            new_sub = re.sub(r"(from_port\s*=\s*)\d+", r"\g<1>443", sub)
            new_sub = re.sub(r"(to_port\s*=\s*)\d+", r"\g<1>443", new_sub)
            if _has_open_cidr(new_sub):
                new_sub = _replace_open_cidr(new_sub, "10.0.0.0/8")
            block = block[:sb_s] + new_sub + block[sb_e:]
            changed = True
    if not changed:
        return content, False, ""
    return (
        content[:start] + block + content[end:],
        True,
        "Narrowed all-ports ingress (0-65535) to port 443 (HTTPS) and restricted CIDR to 10.0.0.0/8.",
    )


def _fix_public_db_port(content: str, resource_id: str) -> tuple[str, bool, str]:
    """Restrict 0.0.0.0/0 → 10.0.0.0/16 on database port ingress."""
    parts = resource_id.split(".", 1)
    if len(parts) != 2:
        return content, False, ""
    span = _locate_resource_block(content, parts[0], parts[1])
    if span is None:
        return content, False, ""
    start, end = span
    block = content[start:end]
    changed = False
    for sb_s, sb_e in reversed(_find_ingress_blocks(block)):
        sub = block[sb_s:sb_e]
        fp = _extract_int(sub, "from_port")
        if fp not in _DB_PORTS:
            continue
        if not _has_open_cidr(sub):
            continue
        block = block[:sb_s] + _replace_open_cidr(sub, "10.0.0.0/16") + block[sb_e:]
        changed = True
    if not changed:
        return content, False, ""
    return (
        content[:start] + block + content[end:],
        True,
        "Restricted database port ingress from 0.0.0.0/0 to 10.0.0.0/16 (VPC-local).",
    )


def _fix_unencrypted_storage(content: str, resource_id: str) -> tuple[str, bool, str]:
    """Set ``encrypted = true`` on storage resources."""
    parts = resource_id.split(".", 1)
    if len(parts) != 2:
        return content, False, ""
    span = _locate_resource_block(content, parts[0], parts[1])
    if span is None:
        return content, False, ""
    start, end = span
    block = content[start:end]

    enc_false = re.compile(r"(encrypted\s*=\s*)(false|\"false\")", re.IGNORECASE)
    if enc_false.search(block):
        new_block = enc_false.sub(r"\g<1>true", block)
        return (
            content[:start] + new_block + content[end:],
            True,
            "Changed encrypted = false to encrypted = true.",
        )

    if not re.search(r"encrypted\s*=", block, re.IGNORECASE):
        brace0 = block.find("{")
        if brace0 < 0:
            return content, False, ""
        indent = re.match(r"^(\s*)", block)
        prop_indent = (indent.group(1) if indent else "") + "  "
        new_block = block[: brace0 + 1] + f"\n{prop_indent}encrypted = true" + block[brace0 + 1 :]
        return (
            content[:start] + new_block + content[end:],
            True,
            "Added encrypted = true to storage resource.",
        )

    return content, False, ""


# ---------------------------------------------------------------------------
# Handler registry
# ---------------------------------------------------------------------------

_FixFn = Callable[[str, str], tuple[str, bool, str]]

_HANDLERS: dict[str, _FixFn] = {
    "SSH_EXPOSED_TO_PUBLIC": lambda c, rid: _fix_ssh_rdp(c, rid, 22),
    "RDP_EXPOSED_TO_PUBLIC": lambda c, rid: _fix_ssh_rdp(c, rid, 3389),
    "ALL_PORTS_OPEN": _fix_all_ports_open,
    "PUBLIC_DB_PORT_EXPOSED": _fix_public_db_port,
    "UNENCRYPTED_STORAGE": _fix_unencrypted_storage,
}


def try_deterministic_fix(
    file_map: dict[str, str],
    finding_type: str,
    resource_id: str,
    source_file: str | None,
) -> tuple[dict[str, str], bool, str]:
    """
    Attempt a deterministic fix for *finding_type*.

    Returns ``(patched_file_map, success, rationale)``.
    """
    if finding_type == "MISSING_TAGS":
        from .missing_tags_fix import try_apply_missing_tags

        new_map, ok = try_apply_missing_tags(file_map, resource_id, source_file)
        if ok:
            return new_map, True, "Applied deterministic Terraform tags (environment, owner, project)."
        return file_map, False, ""

    handler = _HANDLERS.get(finding_type)
    if not handler:
        return file_map, False, ""

    if not resource_id or not source_file:
        return file_map, False, ""

    path = _resolve_source_path(file_map, source_file)
    if not path or not path.endswith(".tf"):
        return file_map, False, ""

    body = file_map[path]
    new_body, ok, rationale = handler(body, resource_id)
    if not ok:
        return file_map, False, ""

    out = dict(file_map)
    out[path] = new_body
    return out, True, rationale
