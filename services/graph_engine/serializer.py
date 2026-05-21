"""
Serializer — converts a NetworkX DiGraph into D3-compatible JSON.

The frontend (or any client) can't understand a Python NetworkX object,
so this module translates it into a plain dict with 'nodes', 'edges',
and 'metadata' keys.
"""

import networkx as nx


def serialize_graph(g: nx.DiGraph) -> dict:
    """
    Convert a NetworkX directed graph to a D3-compatible dict.

    Output format:
    {
      "nodes": [{"id": "vpc-1", "type": "vpc", "provider": "aws"}, ...],
      "edges": [{"source": "internet", "target": "sg-1", "relationship": "exposes"}, ...],
      "metadata": {"node_count": 5, "edge_count": 4}
    }
    """
    nodes = []
    for node_id, attrs in g.nodes(data=True):
        nodes.append({"id": node_id, **attrs})

    edges = []
    for src, tgt, attrs in g.edges(data=True):
        edges.append({"source": src, "target": tgt, **attrs})

    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": {
            "node_count": g.number_of_nodes(),
            "edge_count": g.number_of_edges(),
        },
    }
