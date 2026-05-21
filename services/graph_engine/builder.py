"""
Graph builder — converts a list of Resource objects into a NetworkX directed graph.

Edge rules (hard-coded for now):
  - vpc → subnet              (containment)
  - subnet → ec2_instance     (placement)
  - security_group → ec2_instance  (attachment)
  - internet → security_group (when any rule has cidr 0.0.0.0/0)
"""

import networkx as nx

from services.graph_engine.models import Resource
from services.graph_engine.blast_radius import compute_all_blast_radius


# Maps: (source_type, target_type) → relationship label
EDGE_RULES: dict[tuple[str, str], str] = {
    ("vpc", "subnet"): "contains",
    ("subnet", "ec2_instance"): "places",
    ("security_group", "ec2_instance"): "protects",
}

INTERNET_CIDR = "0.0.0.0/0"


def build_graph(resources: list[Resource]) -> nx.DiGraph:
    """
    Build a directed graph from normalized resources.

    1. Add every resource as a node.
    2. If a security group has a rule with cidr 0.0.0.0/0,
       create an 'internet' node and an edge internet → that security group.
    3. Apply EDGE_RULES to connect resources by type.
    4. Compute blast radius for all nodes.
    """
    g = nx.DiGraph()

    # --- Step 1: Add nodes ---
    for r in resources:
        g.add_node(
            r.resource_id,
            type=r.type,
            provider=r.provider,
        )

    # --- Step 2: Internet exposure ---
    for r in resources:
        if r.type == "security_group":
            for rule in r.rules:
                if rule.cidr == INTERNET_CIDR:
                    # Add the internet node (only once, add_node is idempotent)
                    if "internet" not in g:
                        g.add_node("internet", type="internet", provider="global")
                    g.add_edge(
                        "internet",
                        r.resource_id,
                        relationship="exposes",
                        port=rule.port,
                        protocol=rule.protocol,
                        direction="inbound",
                        exposure_type="public",
                    )
                    break  # one internet edge per security group is enough

    # --- Step 3: Infer edges from type pairs ---
    # Build a lookup: type → list of resource_ids
    type_index: dict[str, list[str]] = {}
    for r in resources:
        type_index.setdefault(r.type, []).append(r.resource_id)

    for (src_type, tgt_type), relationship in EDGE_RULES.items():
        for src_id in type_index.get(src_type, []):
            for tgt_id in type_index.get(tgt_type, []):
                g.add_edge(
                    src_id,
                    tgt_id,
                    relationship=relationship,
                    direction="inbound",
                    exposure_type="private",
                )

    # --- Step 4: Compute blast radius for all nodes ---
    blast_radius_map = compute_all_blast_radius(g)
    
    # Attach blast radius data to each node as an attribute
    for node_id, blast_data in blast_radius_map.items():
        if node_id in g.nodes:
            g.nodes[node_id]["blast_radius"] = blast_data

    return g
