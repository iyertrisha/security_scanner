"""
Blast radius computation — find all nodes reachable from a given node.

The blast radius represents the "damage radius" if a resource is compromised.
It answers: "If this node is hacked, how many downstream resources can be reached?"

Algorithm: BFS (Breadth-First Search) traversal of outbound edges.
"""

import networkx as nx
from typing import Dict, Set


def compute_blast_radius(graph: nx.DiGraph, start_node: str) -> dict:
    """
    Compute blast radius from a given node via BFS.
    
    Finds all nodes reachable via directed outbound edges.
    Excludes the "internet" node from blast radius.
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
        start_node (str): Resource ID to compute blast radius for
    
    Returns:
        dict: {
            "count": int (number of reachable nodes),
            "resources": [sorted list of reachable resource IDs]
        }
        
    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edges_from([("ec2", "rds"), ("ec2", "s3"), ("rds", "backup")])
        >>> compute_blast_radius(graph, "ec2")
        {"count": 3, "resources": ["backup", "rds", "s3"]}
    """
    # Validate node exists
    if start_node not in graph.nodes:
        return {"count": 0, "resources": []}
    
    # BFS to find all nodes reachable from start_node
    reachable: Set[str] = set()
    visited: Set[str] = set()
    queue: list[str] = [start_node]
    
    while queue:
        node = queue.pop(0)
        
        # Skip if already visited (prevents infinite loops in cyclic graphs)
        if node in visited:
            continue
        
        visited.add(node)
        
        # Add all successor nodes (outbound edges)
        for successor in graph.successors(node):
            # Exclude "internet" node from blast radius calculation
            if successor != "internet" and successor not in visited:
                reachable.add(successor)
                queue.append(successor)
    
    return {
        "count": len(reachable),
        "resources": sorted(list(reachable))
    }


def compute_all_blast_radius(graph: nx.DiGraph) -> Dict[str, dict]:
    """
    Compute blast radius for all resource nodes in the graph.
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
    
    Returns:
        dict: Mapping of resource_id → blast_radius dict
        {
            "vpc-1": {"count": 5, "resources": ["subnet-1", "ec2-1", "rds-1", ...]},
            "subnet-1": {"count": 3, "resources": ["ec2-1", "rds-1", ...]},
            ...
        }
    """
    blast_radius_map: Dict[str, dict] = {}
    
    for node in graph.nodes():
        # Skip internet node - it's not a resource
        if node != "internet":
            blast_radius_map[node] = compute_blast_radius(graph, node)
    
    return blast_radius_map


def get_blast_radius(blast_radius_map: Dict[str, dict], node_id: str) -> dict:
    """
    Retrieve blast radius for a specific node from precomputed map.
    
    Args:
        blast_radius_map (dict): Precomputed blast radius map
        node_id (str): Resource ID to look up
    
    Returns:
        dict: Blast radius or {"count": 0, "resources": []} if not found
    """
    return blast_radius_map.get(node_id, {"count": 0, "resources": []})
