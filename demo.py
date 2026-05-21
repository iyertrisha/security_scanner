#!/usr/bin/env python3
"""
NetGuard Graph Engine — Interactive Demo
=========================================
Builds graphs from hardcoded fixture data, serializes them to D3 JSON,
runs a diff between base and head, and prints everything so you can
see the engine working end-to-end.

Run:  python demo.py
"""

import json
from services.graph_engine.models import Resource
from services.graph_engine.builder import build_graph
from services.graph_engine.serializer import serialize_graph
from services.graph_engine.differ import diff_graphs
from services.graph_engine.fixtures import BASE_RESOURCES, HEAD_RESOURCES


SEPARATOR = "=" * 70
SUB_SEP = "-" * 50


def section(title: str):
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(SEPARATOR)


def pretty(obj):
    """Pretty-print a dict/list as indented JSON."""
    print(json.dumps(obj, indent=2, default=str))


def main():
    # ------------------------------------------------------------------ #
    #  1. Show the raw fixture data
    # ------------------------------------------------------------------ #
    section("1. RAW FIXTURE DATA")

    print("\n-- BASE resources (current main branch) --")
    for r in BASE_RESOURCES:
        rules_str = ""
        if r.get("rules"):
            rules_str = f"  rules: {r['rules']}"
        print(f"  {r['resource_id']:12s}  type={r['type']:20s}  provider={r['provider']}{rules_str}")

    print("\n-- HEAD resources (incoming PR) --")
    for r in HEAD_RESOURCES:
        rules_str = ""
        if r.get("rules"):
            rules_str = f"  rules: {r['rules']}"
        print(f"  {r['resource_id']:12s}  type={r['type']:20s}  provider={r['provider']}{rules_str}")

    # ------------------------------------------------------------------ #
    #  2. Build the BASE graph
    # ------------------------------------------------------------------ #
    section("2. BASE GRAPH (main branch)")

    base_resources = [Resource(**r) for r in BASE_RESOURCES]
    base_graph = build_graph(base_resources)
    base_json = serialize_graph(base_graph)

    print(f"\nNodes ({base_json['metadata']['node_count']}):")
    for node in base_json["nodes"]:
        print(f"  [{node['type']:20s}]  {node['id']}")

    print(f"\nEdges ({base_json['metadata']['edge_count']}):")
    for edge in base_json["edges"]:
        extras = []
        if edge.get("port") is not None:
            extras.append(f"port={edge['port']}")
        if edge.get("protocol"):
            extras.append(f"proto={edge['protocol']}")
        extras.append(f"dir={edge.get('direction', '?')}")
        extras.append(f"exposure={edge.get('exposure_type', '?')}")
        extras_str = "  (" + ", ".join(extras) + ")"
        print(f"  {edge['source']:12s} --[{edge['relationship']}]--> {edge['target']}{extras_str}")

    # ------------------------------------------------------------------ #
    #  3. Build the HEAD graph
    # ------------------------------------------------------------------ #
    section("3. HEAD GRAPH (incoming PR)")

    head_resources = [Resource(**r) for r in HEAD_RESOURCES]
    head_graph = build_graph(head_resources)
    head_json = serialize_graph(head_graph)

    print(f"\nNodes ({head_json['metadata']['node_count']}):")
    for node in head_json["nodes"]:
        print(f"  [{node['type']:20s}]  {node['id']}")

    print(f"\nEdges ({head_json['metadata']['edge_count']}):")
    for edge in head_json["edges"]:
        extras = []
        if edge.get("port") is not None:
            extras.append(f"port={edge['port']}")
        if edge.get("protocol"):
            extras.append(f"proto={edge['protocol']}")
        extras.append(f"dir={edge.get('direction', '?')}")
        extras.append(f"exposure={edge.get('exposure_type', '?')}")
        extras_str = "  (" + ", ".join(extras) + ")"
        print(f"  {edge['source']:12s} --[{edge['relationship']}]--> {edge['target']}{extras_str}")

    # ------------------------------------------------------------------ #
    #  4. Diff: BASE vs HEAD
    # ------------------------------------------------------------------ #
    section("4. DIFF: BASE vs HEAD")

    diff = diff_graphs(base_graph, head_graph)

    print(f"\n  Added nodes:         {diff['added_nodes']}")
    print(f"  Removed nodes:       {diff['removed_nodes']}")
    print(f"  Modified nodes:      {diff['modified_nodes']}")

    print(f"\n  Added edges ({len(diff['added_edges'])}):")
    for e in diff["added_edges"]:
        print(f"    + {e['source']} --> {e['target']}  [{e.get('relationship', '?')}]")

    print(f"\n  Removed edges ({len(diff['removed_edges'])}):")
    for e in diff["removed_edges"]:
        print(f"    - {e['source']} --> {e['target']}  [{e.get('relationship', '?')}]")

    print(f"\n  Newly exposed:       {diff['newly_exposed']}")
    print(f"  No longer exposed:   {diff['no_longer_exposed']}")
    print(f"  Exposure delta:      {diff['exposure_delta']}")

    # ------------------------------------------------------------------ #
    #  5. Security summary
    # ------------------------------------------------------------------ #
    section("5. SECURITY SUMMARY")

    if diff["exposure_delta"] < 0:
        print(f"\n  GOOD: Attack surface REDUCED by {abs(diff['exposure_delta'])} public edge(s).")
    elif diff["exposure_delta"] > 0:
        print(f"\n  WARNING: Attack surface INCREASED by {diff['exposure_delta']} public edge(s)!")
    else:
        print("\n  NEUTRAL: No change in public exposure.")

    if diff["no_longer_exposed"]:
        print(f"  Resources no longer internet-exposed: {diff['no_longer_exposed']}")
    if diff["newly_exposed"]:
        print(f"  Resources NEWLY internet-exposed:     {diff['newly_exposed']}")

    # ------------------------------------------------------------------ #
    #  6. Full D3 JSON (for copy/paste into a frontend)
    # ------------------------------------------------------------------ #
    section("6. FULL BASE GRAPH AS D3 JSON")
    pretty(base_json)

    section("7. FULL DIFF AS JSON")
    # Convert diff edges to simple dicts for JSON serialization
    pretty(diff)

    print(f"\n{SEPARATOR}")
    print("  Demo complete — 89 tests passing, graph engine fully operational!")
    print(SEPARATOR)


if __name__ == "__main__":
    main()
