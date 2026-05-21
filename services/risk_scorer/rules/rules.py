"""
11 deterministic security rules for NetGuard.
Each function takes a Resource and returns a Finding or None.
No AI involved here — pure logic, always consistent.

Phase 3 (v2.0): Also includes cross-resource and supply-chain rules.
"""
from typing import Any, Optional, List
from ..schemas import Resource, Finding, Severity, GraphContext, finding_location_kwargs as _loc
from .cross_resource_rules import run_cross_resource_rules
from .supply_chain_rules import run_supply_chain_rules


def _port(val) -> int:
    """Normalise port to int (Vinay's parser gives ports as strings)."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return -1


def _is_public(cidr: str) -> bool:
    """True if the CIDR means 'entire internet'."""
    return cidr in ("0.0.0.0/0", "::/0")


# ── CRITICAL rules ─────────────────────────────────────────────────────────────

def check_ssh_rdp_public(resource: Resource) -> Optional[Finding]:
    """Rule 1 — SSH (22) or RDP (3389) open to 0.0.0.0/0 → CRITICAL."""
    for rule in resource.inbound_rules:
        if _port(rule.port) in (22, 3389) and _is_public(rule.cidr):
            proto = "SSH" if _port(rule.port) == 22 else "RDP"
            return Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type=f"{proto}_EXPOSED_TO_PUBLIC",
                severity=Severity.CRITICAL,
                explanation=(
                    f"{proto} port {rule.port} is open to {rule.cidr}. "
                    "This allows anyone on the internet to attempt authentication."
                ),
                remediation=(
                    f"Restrict the ingress rule for port {rule.port} "
                    "to known corporate IP ranges only."
                ),
                **_loc(resource),
            )
    return None


def check_public_db_port(resource: Resource) -> Optional[Finding]:
    """Rule 2 — Database ports exposed to 0.0.0.0/0 → CRITICAL."""
    db_ports = {
        5432: "PostgreSQL",
        3306: "MySQL",
        1433: "MSSQL",
        27017: "MongoDB",
        6379: "Redis",
        5984: "CouchDB",
    }
    for rule in resource.inbound_rules:
        p = _port(rule.port)
        if p in db_ports and _is_public(rule.cidr):
            return Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type="PUBLIC_DB_PORT_EXPOSED",
                severity=Severity.CRITICAL,
                explanation=(
                    f"{db_ports[p]} port {p} is publicly accessible. "
                    "Database ports should never be exposed to the internet."
                ),
                remediation=(
                    f"Remove the public ingress rule for port {p}. "
                    "Place the database in a private subnet and use a bastion host or VPN."
                ),
                **_loc(resource),
            )
    return None


def check_public_s3(resource: Resource) -> Optional[Finding]:
    """Rule 3 — S3 bucket with public access enabled → CRITICAL."""
    if resource.resource_type != "aws_s3_bucket":
        return None
    props = resource.properties
    # Check common Terraform S3 public access properties
    if (
        props.get("acl") in ("public-read", "public-read-write")
        or props.get("public_access_block") is False
        or props.get("block_public_acls") is False
        or props.get("block_public_policy") is False
    ):
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="PUBLIC_S3_BUCKET",
            severity=Severity.CRITICAL,
            explanation=(
                "This S3 bucket has public access enabled. "
                "Anyone on the internet can read or write its contents."
            ),
            remediation=(
                "Set block_public_acls, block_public_policy, ignore_public_acls, "
                "and restrict_public_buckets to true in aws_s3_bucket_public_access_block."
            ),
            **_loc(resource),
        )
    return None


def check_all_ports_open(resource: Resource) -> Optional[Finding]:
    """Rule 4 — Security group with all ports open (0-65535) → CRITICAL."""
    for rule in resource.inbound_rules:
        p = _port(rule.port)
        if p == 0 or str(rule.port) == "0-65535":
            return Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type="ALL_PORTS_OPEN",
                severity=Severity.CRITICAL,
                explanation=(
                    "This security group allows inbound traffic on ALL ports. "
                    "This is equivalent to having no firewall."
                ),
                remediation=(
                    "Replace the all-ports rule with specific rules "
                    "for only the ports your application requires."
                ),
                **_loc(resource),
            )
    return None


# ── HIGH rules ─────────────────────────────────────────────────────────────────

def check_http_without_https(resource: Resource) -> Optional[Finding]:
    """Rule 5 — HTTP port 80 open without HTTPS redirect → HIGH."""
    has_http = any(_port(r.port) == 80 for r in resource.inbound_rules)
    has_https = any(_port(r.port) == 443 for r in resource.inbound_rules)
    if has_http and not has_https:
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="HTTP_WITHOUT_HTTPS",
            severity=Severity.HIGH,
            explanation=(
                "Port 80 (HTTP) is open but port 443 (HTTPS) is not configured. "
                "Traffic is transmitted unencrypted."
            ),
            remediation=(
                "Add an HTTPS listener on port 443 and configure a redirect "
                "from HTTP (80) to HTTPS (443)."
            ),
            **_loc(resource),
        )
    return None


def check_permissive_iam(resource: Resource) -> Optional[Finding]:
    """Rule 6 — Overly permissive IAM role (* actions or * resources) → HIGH."""
    if "iam" not in resource.resource_type.lower():
        return None
    props = resource.properties
    statements = props.get("statement", props.get("policy", {}).get("Statement", []))
    if isinstance(statements, list):
        for stmt in statements:
            actions = stmt.get("actions", stmt.get("Action", []))
            resources = stmt.get("resources", stmt.get("Resource", []))
            if isinstance(actions, str):
                actions = [actions]
            if isinstance(resources, str):
                resources = [resources]
            if "*" in actions or "*" in resources:
                return Finding(
                    resource_id=resource.resource_id,
                    resource_type=resource.resource_type,
                    finding_type="PERMISSIVE_IAM_POLICY",
                    severity=Severity.HIGH,
                    explanation=(
                        "This IAM policy uses wildcard (*) for actions or resources. "
                        "This grants far more permissions than necessary."
                    ),
                    remediation=(
                        "Apply the principle of least privilege. Replace * with "
                        "specific actions and resource ARNs your workload requires."
                    ),
                    **_loc(resource),
                )
    return None


def check_missing_network_policy(resource: Resource) -> Optional[Finding]:
    """Rule 7 — Kubernetes namespace with no NetworkPolicy → HIGH."""
    if resource.resource_type != "kubernetes_namespace":
        return None
    if not resource.properties.get("has_network_policy", False):
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="MISSING_NETWORK_POLICY",
            severity=Severity.HIGH,
            explanation=(
                "This Kubernetes namespace has no NetworkPolicy. "
                "All pods can communicate with each other with no restrictions."
            ),
            remediation=(
                "Create a default-deny NetworkPolicy for this namespace "
                "and add explicit allow rules for required pod-to-pod traffic."
            ),
            **_loc(resource),
        )
    return None


def _k8s_container_specs(properties: dict) -> list[dict]:
    """Return container dicts from Pod spec or Deployment template."""
    if "containers" in properties:
        return properties.get("containers") or []
    tmpl = properties.get("template") or {}
    pod_spec = tmpl.get("spec") or {}
    return pod_spec.get("containers") or []


def _container_security_context(container: dict) -> dict:
    return container.get("securityContext") or container.get("security_context") or {}


def check_privileged_container(resource: Resource) -> Optional[Finding]:
    """Rule 8 — Privileged container in Kubernetes → HIGH."""
    if resource.resource_type not in ("kubernetes_deployment", "kubernetes_pod"):
        return None
    containers = _k8s_container_specs(resource.properties)
    for container in containers:
        sc = _container_security_context(container)
        if sc.get("privileged") is True:
            return Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type="PRIVILEGED_CONTAINER",
                severity=Severity.HIGH,
                explanation=(
                    f"Container '{container.get('name', 'unknown')}' runs in privileged mode. "
                    "It has full access to the host kernel, bypassing container isolation."
                ),
                remediation=(
                    "Set securityContext.privileged to false. "
                    "Use specific capabilities (securityContext.capabilities.add) instead."
                ),
                **_loc(resource),
            )
    return None


# ── MEDIUM rules ───────────────────────────────────────────────────────────────

def check_unauthenticated_service(resource: Resource) -> Optional[Finding]:
    """Rule 9 — Service exposed without authentication → MEDIUM."""
    if resource.resource_type not in ("kubernetes_service", "aws_lb_listener"):
        return None
    props = resource.properties
    if (
        props.get("authentication") is None
        and props.get("auth_type", "NONE") == "NONE"
        and props.get("type") in ("LoadBalancer", "NodePort")
    ):
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="UNAUTHENTICATED_SERVICE",
            severity=Severity.MEDIUM,
            explanation=(
                "This service is publicly exposed with no authentication configured. "
                "Anyone who can reach the endpoint can access it."
            ),
            remediation=(
                "Add authentication (OAuth2, mTLS, or API keys) in front of "
                "this service, or restrict access using network policies."
            ),
            **_loc(resource),
        )
    return None


def _truthy_encryption_flag(val: Any) -> bool:
    """Match parser/HCL quirks: accept bool True or common string literals."""
    if val is True:
        return True
    if isinstance(val, str):
        return val.strip().lower() in {"true", "1", "yes", "on"}
    return False


def _explicitly_unencrypted_flag(val: Any) -> bool:
    if val is False:
        return True
    if isinstance(val, str):
        return val.strip().lower() in {"false", "0", "no", "off"}
    return False


def check_unencrypted_storage(resource: Resource) -> Optional[Finding]:
    """Rule 10 — Unencrypted storage or transit → MEDIUM."""
    storage_types = (
        "aws_ebs_volume",
        "aws_rds_instance",
        "aws_db_instance",
        "aws_s3_bucket",
        "aws_efs_file_system",
    )
    if resource.resource_type not in storage_types:
        return None
    props = resource.properties
    enc_raw = props.get("encrypted")
    stor_raw = props.get("storage_encrypted")
    if _explicitly_unencrypted_flag(enc_raw) or _explicitly_unencrypted_flag(stor_raw):
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="UNENCRYPTED_STORAGE",
            severity=Severity.MEDIUM,
            explanation=(
                "This storage resource is not encrypted at rest. "
                "Data is stored in plaintext and accessible if the underlying storage is compromised."
            ),
            remediation=(
                "Enable encryption by setting encrypted=true and specifying "
                "a kms_key_id using AWS KMS."
            ),
            **_loc(resource),
        )

    # Encrypted-at-rest indicators from IaC parsers (often strings).
    if _truthy_encryption_flag(enc_raw) or _truthy_encryption_flag(stor_raw):
        return None

    # Still ambiguous / omitted — treat as not meeting encryption requirement for this MVP rule.
    return Finding(
        resource_id=resource.resource_id,
        resource_type=resource.resource_type,
        finding_type="UNENCRYPTED_STORAGE",
        severity=Severity.MEDIUM,
        explanation=(
            "This storage resource is not encrypted at rest. "
            "Data is stored in plaintext and accessible if the underlying storage is compromised."
        ),
        remediation=(
            "Enable encryption by setting encrypted=true and specifying "
            "a kms_key_id using AWS KMS."
        ),
        **_loc(resource),
    )


# ── LOW rules ──────────────────────────────────────────────────────────────────

def check_missing_tags(resource: Resource) -> Optional[Finding]:
    """Rule 11 — Missing resource tags → LOW."""
    required_tags = {"environment", "owner", "project"}
    existing = {k.lower() for k in resource.tags.keys()}
    missing = required_tags - existing
    if missing:
        return Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="MISSING_TAGS",
            severity=Severity.LOW,
            explanation=(
                f"Resource is missing required tags: {', '.join(sorted(missing))}. "
                "Tags are essential for cost tracking, ownership, and incident response."
            ),
            remediation=(
                f"Add the following tags to this resource: {', '.join(sorted(missing))}."
            ),
            **_loc(resource),
        )
    return None


# ── Master list — all rules in one place ───────────────────────────────────────

ALL_RULES = [
    check_ssh_rdp_public,
    check_public_db_port,
    check_public_s3,
    check_all_ports_open,
    check_http_without_https,
    check_permissive_iam,
    check_missing_network_policy,
    check_privileged_container,
    check_unauthenticated_service,
    check_unencrypted_storage,
    check_missing_tags,
]


def run_all_rules(
    resource: Resource,
    graph_context: Optional[GraphContext] = None,
    resources_list: Optional[List[Resource]] = None,
    include_cross_resource: bool = True,
) -> list[Finding]:
    """
    Run every rule against a resource, return all findings that fired.
    
    Phases:
    - Phase 1 (v1.0): Single-resource deterministic rules (11 rules)
    - Phase 3 (v2.0): Cross-resource rules (5 rules) + Supply-chain rules (2 rules)
    
    Args:
        resource: Resource to check
        graph_context: Optional graph context with nodes/edges/blast_radius (for cross-resource rules)
        resources_list: Optional list of all resources (for cross-resource rules)
    """
    findings = []
    
    # Phase 1: Single-resource rules (always run)
    for rule_fn in ALL_RULES:
        result = rule_fn(resource)
        if result is not None:
            findings.append(result)
    
    # Phase 3: Cross-resource rules (if graph context provided)
    if include_cross_resource and graph_context and resources_list:
        cross_resource_findings = run_cross_resource_rules(resource, graph_context, resources_list)
        findings.extend(cross_resource_findings)
    
    # Phase 3: Supply-chain rules (always run, heuristic matching)
    supply_chain_findings = run_supply_chain_rules(resource)
    findings.extend(supply_chain_findings)
    
    return findings