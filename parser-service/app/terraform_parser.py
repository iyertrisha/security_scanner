import re

import hcl2

# Match top-level resource declarations: resource "aws_instance" "foo" {
_RESOURCE_LINE_RE = re.compile(
    r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)


def _terraform_resource_line_map(content: str) -> dict[str, int]:
    """Map ``resource_type.resource_name`` -> 1-based line number."""
    lines = content.splitlines()
    mapping: dict[str, int] = {}
    for idx, line in enumerate(lines, start=1):
        m = _RESOURCE_LINE_RE.match(line)
        if not m:
            continue
        rtype, name = m.group(1), m.group(2)
        mapping[f"{rtype}.{name}"] = idx
    return mapping

# python-hcl2 7.x uses literal quote characters in dict keys and many string values.
def _hcl2_label(value) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        return str(value)
    s = value.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


SUPPORTED_RESOURCES = [
    "aws_vpc",
    "aws_subnet",
    "aws_security_group",
    "aws_instance",
    "aws_lb",
    "aws_db_instance",
    "aws_s3_bucket",
    "aws_iam_role",
    "aws_internet_gateway",
    "aws_nat_gateway"
]


def _evaluate_module_source(source_url: str) -> dict:
    """
    Evaluate Terraform module source trust and version pinning.
    """
    value = _hcl2_label(source_url or "")
    lower = value.lower()

    if lower.startswith("http://"):
        trust_level = "untrusted_transport"
    elif "github.com" in lower:
        trust_level = "non_registry"
    else:
        trust_level = "registry_or_local"

    has_ref_pin = "?ref=" in lower
    version_status = "pinned" if has_ref_pin else "unpinned"

    # v2.0 asks medium flags for unversioned/non-registry/http.
    should_flag = (not has_ref_pin) or ("github.com" in lower) or lower.startswith("http://")
    return {
        "source_url": value,
        "version_status": version_status,
        "trust_level": trust_level,
        "flag_severity": "MEDIUM" if should_flag else "NONE",
    }


def parse_module_sources(content):
    data = hcl2.loads(content)
    module_sources = []

    for module_block in data.get("module", []):
        for _module_name, module_values in module_block.items():
            if _module_name == "__is_block__":
                continue
            source_url = module_values.get("source")
            if source_url:
                module_sources.append(_evaluate_module_source(source_url))

    return module_sources

def _sg_rule_blocks_to_netguard_rules(blocks: list | None, *, outbound: bool) -> list[dict]:
    """Map aws_security_group ingress/egress blocks to inbound_rules / outbound_rules."""
    if not blocks:
        return []
    out: list[dict] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        from_p_present = "from_port" in block
        to_p_present = "to_port" in block
        if not from_p_present or not to_p_present:
            continue
        from_p = block.get("from_port")
        to_p = block.get("to_port")
        proto = _hcl2_label(str(block.get("protocol", "tcp")))
        cidrs = block.get("cidr_blocks") or []
        if isinstance(cidrs, str):
            cidrs = [cidrs]
        if from_p == to_p:
            port_val: str | int = from_p
        else:
            port_val = f"{from_p}-{to_p}"
        for cidr in cidrs:
            out.append({"port": port_val, "protocol": proto, "cidr": _hcl2_label(str(cidr))})
    return out


def parse_terraform(content: str, *, source_file: str | None = None):

    data = hcl2.loads(content)
    line_map = _terraform_resource_line_map(content)

    resources = []

    if "resource" not in data:
        return resources

    for resource in data["resource"]:

        for raw_rtype, instances in resource.items():
            if raw_rtype == "__is_block__":
                continue
            rtype = _hcl2_label(raw_rtype)
            if rtype not in SUPPORTED_RESOURCES:
                continue

            for raw_name, values in instances.items():
                if raw_name == "__is_block__":
                    continue
                name = _hcl2_label(raw_name)
                props = values if isinstance(values, dict) else {}
                rid_key = f"{rtype}.{name}"
                resource_data = {
                    "resource_id": rid_key,
                    "resource_type": rtype,
                    "provider": "aws",
                    "properties": props,
                    "inbound_rules": [],
                    "outbound_rules": [],
                    "tags": props.get("tags") if isinstance(props.get("tags"), dict) else {},
                    "source_file": source_file,
                    "source_line": line_map.get(rid_key),
                }

                if rtype == "aws_security_group":
                    ingress = values.get("ingress")
                    if isinstance(ingress, list):
                        resource_data["inbound_rules"] = _sg_rule_blocks_to_netguard_rules(
                            ingress, outbound=False
                        )
                    egress = values.get("egress")
                    if isinstance(egress, list):
                        resource_data["outbound_rules"] = _sg_rule_blocks_to_netguard_rules(
                            egress, outbound=True
                        )

                resources.append(resource_data)

    return resources