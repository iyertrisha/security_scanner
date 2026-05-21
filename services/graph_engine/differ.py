"""
Graph differ — compares two NetworkX DiGraphs and reports what changed.

Uses simple set math:
  - added   = in head but not in base
  - removed = in base but not in head
  - modified = same node ID but attributes changed
  - newly_exposed / no_longer_exposed = internet edge changes
  - exposure_delta = net change in public edges
"""

import networkx as nx


def _compare_node_attrs(
    base_attrs: dict,
    head_attrs: dict,
    ignored_fields: set = None,
) -> bool:
    """
    Compare two node attribute dicts, excluding certain computed fields.
    
    Args:
        base_attrs: Attributes from base graph node
        head_attrs: Attributes from head graph node
        ignored_fields: Set of attribute keys to exclude from comparison
    
    Returns:
        bool: True if attributes differ (excluding ignored fields)
    """
    if ignored_fields is None:
        ignored_fields = set()
    
    base_filtered = {k: v for k, v in base_attrs.items() if k not in ignored_fields}
    head_filtered = {k: v for k, v in head_attrs.items() if k not in ignored_fields}
    
    return base_filtered != head_filtered


def diff_graphs(base: nx.DiGraph, head: nx.DiGraph) -> dict:
    """
    Compare a base graph and a head graph.

    Returns a dict with:
      - added_nodes:       resource IDs new in head
      - removed_nodes:     resource IDs deleted from base
      - added_edges:       edge dicts new in head
      - removed_edges:     edge dicts gone from base
      - modified_nodes:    resource IDs present in both but with changed attributes
      - newly_exposed:     resources that gained an internet → X edge
      - no_longer_exposed: resources that lost an internet → X edge
      - exposure_delta:    count of public edges added minus removed
    """
    base_node_ids = set(base.nodes)
    head_node_ids = set(head.nodes)

    added_nodes = sorted(head_node_ids - base_node_ids)
    removed_nodes = sorted(base_node_ids - head_node_ids)

    # --- Modified nodes (same ID, different attributes) ---
    # Note: exclude computed fields like blast_radius from comparison
    # These are recomputed on each build and shouldn't trigger modifications
    IGNORED_ATTRS = {"blast_radius"}
    
    common_nodes = base_node_ids & head_node_ids
    modified_nodes = sorted(
        nid for nid in common_nodes
        if _compare_node_attrs(base.nodes[nid], head.nodes[nid], IGNORED_ATTRS)
    )

    # --- Edge diffs ---
    base_edge_set = set(base.edges)
    head_edge_set = set(head.edges)

    added_edge_tuples = sorted(head_edge_set - base_edge_set)
    removed_edge_tuples = sorted(base_edge_set - head_edge_set)

    added_edges = [
        {
            "source": src,
            "target": tgt,
            **{k: v for k, v in head.edges[src, tgt].items()},
        }
        for src, tgt in added_edge_tuples
    ]

    removed_edges = [
        {
            "source": src,
            "target": tgt,
            **{k: v for k, v in base.edges[src, tgt].items()},
        }
        for src, tgt in removed_edge_tuples
    ]

    # --- Internet exposure detection ---
    base_internet_targets = {
        tgt for src, tgt in base.edges if src == "internet"
    }
    head_internet_targets = {
        tgt for src, tgt in head.edges if src == "internet"
    }

    newly_exposed = sorted(head_internet_targets - base_internet_targets)
    no_longer_exposed = sorted(base_internet_targets - head_internet_targets)

    # --- Exposure delta (net change in public edges) ---
    base_public = sum(
        1 for _, _, d in base.edges(data=True)
        if d.get("exposure_type") == "public"
    )
    head_public = sum(
        1 for _, _, d in head.edges(data=True)
        if d.get("exposure_type") == "public"
    )
    exposure_delta = head_public - base_public

    return {
        "added_nodes": added_nodes,
        "removed_nodes": removed_nodes,
        "added_edges": added_edges,
        "removed_edges": removed_edges,
        "modified_nodes": modified_nodes,
        "newly_exposed": newly_exposed,
        "no_longer_exposed": no_longer_exposed,
        "exposure_delta": exposure_delta,
    }
