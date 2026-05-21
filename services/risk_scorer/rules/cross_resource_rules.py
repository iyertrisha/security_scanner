"""
Cross-resource security rules (Phase 3) — detect compound attack paths.

Performance note:
When called from the scoring endpoint, rules are evaluated in bulk with a shared
context/index to avoid rebuilding graphs and resource lookups for every resource.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, List, Optional

import networkx as nx

from ..schemas import Resource, Finding, Severity, GraphContext, finding_location_kwargs as _loc


_SG_REF_RE = re.compile(r"aws_security_group\.([A-Za-z0-9_-]+)")


def _build_graph_from_context(graph_context: Optional[GraphContext]) -> nx.DiGraph:
    """Reconstruct a NetworkX DiGraph from D3-compatible context."""
    g = nx.DiGraph()
    if not graph_context:
        return g

    for node in graph_context.nodes:
        node_id = node.get("id")
        if node_id:
            g.add_node(node_id, type=node.get("type"), provider=node.get("provider"))

    for edge in graph_context.edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src and tgt:
            g.add_edge(src, tgt, relationship=edge.get("relationship"))

    return g


def _is_ec2_resource(resource: Resource) -> bool:
    return resource.resource_type in ("aws_ec2_instance", "aws_instance")


def _ec2_sg_ref_list(ec2_props: dict) -> list[str]:
    refs = list(ec2_props.get("security_groups") or [])
    refs.extend(ec2_props.get("vpc_security_group_ids") or [])
    out: list[str] = []
    for item in refs:
        text = str(item)
        out.append(text)
        for match in _SG_REF_RE.findall(text):
            out.append(f"aws_security_group.{match}")
    return out


def _sg_lists_overlap(a: list[str], b: list[str]) -> bool:
    for x in a:
        for y in b:
            if x == y or x in y or y in x:
                return True
    return False


def _ec2_references_sg(ec2_props: dict, sg_resource_id: str) -> bool:
    r"""Match Terraform references like ${aws_security_group.xxx.id} to resource_id aws_security_group.xxx."""
    refs = list(ec2_props.get("security_groups") or [])
    refs.extend(ec2_props.get("vpc_security_group_ids") or [])
    for r in refs:
        s = str(r)
        if sg_resource_id in s:
            return True
    return False


def _is_admin_iam(resource: Resource) -> bool:
    """Check if resource has admin/unrestricted IAM permissions."""
    if resource.resource_type == "aws_iam_role":
        # For IAM resources, check if policies include admin actions
        attached_policies = resource.properties.get("attached_policies", [])
        policy_text = resource.properties.get("policy_document", "")
        
        admin_keywords = ["AdministratorAccess", "*:*", "iam:*"]
        return any(keyword in str(attached_policies) or keyword in policy_text for keyword in admin_keywords)
    
    # For EC2, check if has admin IAM profile or policy
    iam_profile = str(resource.properties.get("iam_instance_profile", "") or "")
    if "admin" in iam_profile.lower():
        return True
    
    # Check properties for high-privilege policies
    policy = resource.properties.get("policy", "")
    if isinstance(policy, str) and "*" in policy and "Action" in policy and "Resource" in policy:
        return True
    
    return False


def _has_sensitive_data(resource: Resource) -> bool:
    """Check if resource likely contains sensitive data based on tags/properties."""
    # Always assume databases/storage can contain sensitive data
    if resource.resource_type in (
        "aws_rds_instance",
        "aws_db_instance",
        "aws_dynamodb_table",
        "aws_s3_bucket",
    ):
        return True
    
    # Check tags for sensitive data indicators
    tags_str = str(resource.tags).lower()
    sensitive_keywords = ["pii", "phi", "credit_card", "credit_cards", "ssn", "password", "secret", "confidential", "private", "sensitive"]
    for keyword in sensitive_keywords:
        if keyword in tags_str:
            return True
    
    # Check properties
    props_str = str(resource.properties).lower()
    for keyword in sensitive_keywords:
        if keyword in props_str:
            return True
    
    return False


def _is_database_resource(resource: Resource) -> bool:
    return resource.resource_type in (
        "aws_rds_instance",
        "aws_db_instance",
        "aws_dynamodb_table",
    )


def _safe_has_path(g: nx.DiGraph, source: str, target: str) -> bool:
    if not g.has_node(source) or not g.has_node(target):
        return False
    try:
        return nx.has_path(g, source, target)
    except Exception:
        return False


def _shortest_path_length(g: nx.DiGraph, source: str, target: str) -> int | None:
    if not g.has_node(source) or not g.has_node(target):
        return None
    try:
        return int(nx.shortest_path_length(g, source, target))
    except Exception:
        return None


class _CrossResourceContext:
    """Precomputed indexes for cross-resource rules (performance-focused)."""

    def __init__(self, graph_context: Optional[GraphContext], resources_list: List[Resource]):
        self.graph_context = graph_context
        self.resources_list = resources_list
        self.graph = _build_graph_from_context(graph_context)
        self.newly_exposed = set(graph_context.newly_exposed if graph_context else [])
        self.resource_by_id = {resource.resource_id: resource for resource in resources_list}

        self.ec2_resources = [resource for resource in resources_list if _is_ec2_resource(resource)]
        self.db_resources = [resource for resource in resources_list if _is_database_resource(resource)]

        self.ec2_sg_refs = {resource.resource_id: _ec2_sg_ref_list(resource.properties) for resource in self.ec2_resources}
        self.db_sg_refs = {resource.resource_id: _ec2_sg_ref_list(resource.properties) for resource in self.db_resources}

        self.sg_to_ec2_ids: dict[str, set[str]] = defaultdict(set)
        for ec2_id, refs in self.ec2_sg_refs.items():
            for ref in refs:
                self.sg_to_ec2_ids[ref].add(ec2_id)

        self.internet_exposed_nodes: set[str] = set()
        if self.graph.has_node("internet"):
            try:
                self.internet_exposed_nodes = set(nx.descendants(self.graph, "internet"))
            except Exception:
                self.internet_exposed_nodes = set()

    def node_is_internet_exposed(self, resource_id: str) -> bool:
        return resource_id in self.newly_exposed or resource_id in self.internet_exposed_nodes

    def resources_reachable_from(self, resource_id: str) -> set[str]:
        if not self.graph.has_node(resource_id):
            return set()
        try:
            return set(nx.descendants(self.graph, resource_id))
        except Exception:
            return set()


def check_privileged_ec2_to_sensitive_db(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> List[Finding]:
    """
    Rule C1 — EC2 with admin IAM can reach sensitive database → CRITICAL
    
    Attack path: Privileged EC2 instance is compromised → attacker gains
    admin credentials → can access sensitive database directly.
    """
    findings = []
    if not _is_ec2_resource(resource):
        return findings

    # Benchmark-aligned compound condition: admin-capable EC2
    if not _is_admin_iam(resource):
        return findings

    if not graph_context:
        return findings

    ctx = _CrossResourceContext(graph_context, resources_list)
    reachable_ids = ctx.resources_reachable_from(resource.resource_id)
    ec2_sgs = ctx.ec2_sg_refs.get(resource.resource_id, [])
    reachable_sensitive_dbs: list[str] = []

    for db_resource in ctx.db_resources:
        db_id = db_resource.resource_id
        # Detect relationship through graph path or shared SG attachment.
        has_graph_path = db_id in reachable_ids
        has_shared_sg = _sg_lists_overlap(ec2_sgs, ctx.db_sg_refs.get(db_id, []))
        if (has_graph_path or has_shared_sg) and _has_sensitive_data(db_resource):
            reachable_sensitive_dbs.append(db_id)

    if reachable_sensitive_dbs:
        findings.append(Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="PRIVILEGED_EC2_TO_SENSITIVE_DB",
            severity=Severity.CRITICAL,
            explanation=(
                f"This EC2 instance has admin IAM permissions and can reach "
                f"{len(reachable_sensitive_dbs)} sensitive database(s): {', '.join(reachable_sensitive_dbs[:3])}. "
                "If this EC2 is compromised, attackers can directly access sensitive data."
            ),
            remediation=(
                "Use least-privilege IAM: restrict to specific database/table permissions. "
                "Consider using database-level access control (Secrets Manager, RDS IAM auth). "
                "Monitor database access logs for suspicious queries."
            ),
            **_loc(resource),
        ))
    
    return findings


def check_internet_exposed_admin_ec2(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> List[Finding]:
    """
    Rule C0 — Internet-facing EC2 with admin IAM role → CRITICAL.

    Benchmark-aligned compound risk:
    internet exposure + administrative privilege on compute.
    """
    findings: list[Finding] = []
    if not _is_ec2_resource(resource):
        return findings
    if not graph_context:
        return findings
    if not _is_admin_iam(resource):
        return findings

    ctx = _CrossResourceContext(graph_context, resources_list)
    if not ctx.node_is_internet_exposed(resource.resource_id):
        return findings

    findings.append(
        Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="INTERNET_EXPOSED_ADMIN_EC2",
            severity=Severity.CRITICAL,
            explanation=(
                "This EC2 instance is internet-reachable and has administrative IAM privileges. "
                "Compromise of this host can lead to immediate high-impact cloud account actions."
            ),
            remediation=(
                "Remove public exposure (private subnet + restrictive security groups) and apply "
                "least-privilege IAM policies to the instance profile."
            ),
            **_loc(resource),
        )
    )
    return findings


def check_public_eni_chain_to_database(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource]
) -> List[Finding]:
    """
    Rule C2 — Public ENI → Private EC2 → Database (3-hop attack path) → HIGH
    
    Attack path: Internet → Public ENI → Private EC2 → Database.
    This represents a chained vulnerability.
    """
    findings = []
    if resource.resource_type not in (
        "aws_network_interface",
        "aws_security_group",
        "aws_ec2_instance",
        "aws_instance",
    ):
        return findings

    if not graph_context:
        return findings

    ctx = _CrossResourceContext(graph_context, resources_list)
    is_internet_exposed = ctx.node_is_internet_exposed(resource.resource_id)
    if not is_internet_exposed:
        return findings

    for db_resource in ctx.db_resources:
        db_id = db_resource.resource_id
        path_length = _shortest_path_length(ctx.graph, resource.resource_id, db_id)
        if path_length is None:
            continue
        if path_length >= 2:
            findings.append(Finding(
                resource_id=resource.resource_id,
                resource_type=resource.resource_type,
                finding_type="PUBLIC_CHAIN_TO_DATABASE",
                severity=Severity.HIGH,
                explanation=(
                    f"Internet-exposed resource can reach database '{db_id}' "
                    f"in {path_length} hops. Multi-step attack path detected."
                ),
                remediation=(
                    "Place databases in private subnets. "
                    "Use bastion hosts or VPN for access. "
                    "Restrict security group rules to only required sources."
                ),
                **_loc(resource),
            ))
            break

    return findings


def check_overpermissive_sg_chain(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> List[Finding]:
    """
    Rule C3 — Overpermissive Security Group Chain → HIGH
    
    SG allows all ports from internet → protects EC2 → reaches sensitive resources.
    Permission amplification creates exploitable path.
    """
    findings = []
    if resource.resource_type != "aws_security_group":
        return findings

    if not graph_context:
        return findings

    ctx = _CrossResourceContext(graph_context, resources_list)

    # Check if SG has rule allowing all ports from internet
    allows_all_ports = False
    for rule in resource.inbound_rules:
        if rule.cidr == "0.0.0.0/0" and (rule.port == "-1" or rule.port == "all" or rule.port == "0"):
            allows_all_ports = True
            break

    if not allows_all_ports:
        return findings

    # Find EC2s protected by this SG.
    protected_resources: set[str] = set()
    for ref, ec2_ids in ctx.sg_to_ec2_ids.items():
        if resource.resource_id == ref or resource.resource_id in ref or ref in resource.resource_id:
            protected_resources.update(ec2_ids)

    sensitive_reachable: list[str] = []
    for ec2_id in protected_resources:
        reachable_ids = ctx.resources_reachable_from(ec2_id)
        for db_resource in ctx.db_resources:
            if db_resource.resource_id in reachable_ids:
                sensitive_reachable.append(db_resource.resource_id)

    if sensitive_reachable:
        findings.append(Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="OVERPERMISSIVE_SG_CHAIN",
            severity=Severity.HIGH,
            explanation=(
                f"This security group allows all ports from internet and protects "
                f"{len(protected_resources)} resource(s) that can reach {len(sensitive_reachable)} sensitive resource(s). "
                "This creates an amplified attack surface."
            ),
            remediation=(
                "Restrict ingress rules to specific ports (22, 80, 443). "
                "Use NACLs for additional filtering. "
                "Implement WAF for HTTP/HTTPS endpoints."
            ),
            **_loc(resource),
        ))
    
    return findings


def check_cross_az_replication_exposure(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> List[Finding]:
    """
    Rule C4 — Cross-AZ Database Replication Exposure → CRITICAL
    
    DB replica exposed to internet in different AZ + can reach primary DB.
    Replication is bidirectional; compromise one = compromise both.
    """
    findings = []
    if resource.resource_type not in ("aws_rds_instance", "aws_db_instance"):
        return findings
    
    # Check if this is a replica
    is_replica = resource.properties.get("replicate_source_db", None) is not None
    if not is_replica:
        return findings
    
    if not graph_context:
        return findings

    ctx = _CrossResourceContext(graph_context, resources_list)
    is_exposed = ctx.node_is_internet_exposed(resource.resource_id)
    if not is_exposed:
        return findings

    reachable_ids = ctx.resources_reachable_from(resource.resource_id)
    source_db = resource.properties.get("replicate_source_db", "")
    
    if source_db in reachable_ids or source_db in resource.properties.get("replication_target_db", []):
        findings.append(Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="CROSS_AZ_REPLICATION_EXPOSURE",
            severity=Severity.CRITICAL,
            explanation=(
                f"Database replica is publicly exposed and has replication link to primary DB '{source_db}'. "
                "Replication connection allows bidirectional access to all data."
            ),
            remediation=(
                "Place replicas in private subnets only. "
                "Restrict replication to use encrypted, VPC-internal connections. "
                "Use encrypted inter-region replication with restricted security groups."
            ),
            **_loc(resource),
        ))
    
    return findings


def check_lateral_movement_via_shared_sg(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> List[Finding]:
    """
    Rule C5 — Lateral Movement via Shared Security Group → HIGH
    
    Multiple EC2s in same SG, one has vulnerability, others have sensitive data.
    Compromised EC2 can laterally move to others in same SG.
    """
    findings = []
    if not _is_ec2_resource(resource):
        return findings

    sgs = _ec2_sg_ref_list(resource.properties)
    if not sgs:
        return findings

    shared_sg_resources = []
    for res in resources_list:
        if res.resource_id != resource.resource_id and _is_ec2_resource(res):
            res_sgs = _ec2_sg_ref_list(res.properties)
            if _sg_lists_overlap(sgs, res_sgs):
                shared_sg_resources.append(res)
    
    high_value_targets = [
        res for res in shared_sg_resources
        if _has_sensitive_data(res) or _is_admin_iam(res)
    ]
    
    if high_value_targets:
        findings.append(Finding(
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            finding_type="LATERAL_MOVEMENT_VIA_SG",
            severity=Severity.HIGH,
            explanation=(
                f"This EC2 shares security group(s) with {len(shared_sg_resources)} other EC2(s), "
                f"including {len(high_value_targets)} with sensitive data or admin roles. "
                "Lateral movement between instances in same SG is possible."
            ),
            remediation=(
                "Use per-instance security groups or network policies. "
                "Implement host-based firewall rules restricting inter-instance communication. "
                "Use VPC Flow Logs to detect lateral movement attempts. "
                "Monitor EC2 instance health; isolate compromised instances immediately."
            ),
            **_loc(resource),
        ))
    
    return findings


# Master orchestrator
def run_cross_resource_rules(
    resource: Resource,
    graph_context: Optional[GraphContext],
    resources_list: List[Resource],
) -> list[Finding]:
    """Run all cross-resource rules, return all findings that fired."""
    findings: list[Finding] = []
    for rule_fn in (
        check_internet_exposed_admin_ec2,
        check_privileged_ec2_to_sensitive_db,
        check_public_eni_chain_to_database,
        check_overpermissive_sg_chain,
        check_cross_az_replication_exposure,
        check_lateral_movement_via_shared_sg,
    ):
        try:
            findings.extend(rule_fn(resource, graph_context, resources_list))
        except Exception:
            # Rule failures should not crash scoring.
            pass
    return findings


def run_cross_resource_rules_bulk(
    resources_list: List[Resource],
    graph_context: Optional[GraphContext],
) -> list[Finding]:
    """
    Performance-oriented cross-resource rule execution.

    Runs rule checks across all resources once per score request and deduplicates
    findings by (resource_id, finding_type).
    """
    if not graph_context or not resources_list:
        return []

    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    for resource in resources_list:
        for finding in run_cross_resource_rules(resource, graph_context, resources_list):
            key = (finding.resource_id, finding.finding_type)
            if key in seen:
                continue
            seen.add(key)
            findings.append(finding)
    return findings
