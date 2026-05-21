"""
Subgraph extraction — isolate the 2-hop neighborhood around a node.

The 2-hop neighborhood includes:
- The node itself
- 1-hop neighbors (direct predecessors/successors)
- 2-hop neighbors (neighbors of neighbors)

This provides context for risk scoring and visualization.
"""

import networkx as nx
from typing import Set


def extract_subgraph(graph: nx.DiGraph, center_node: str, hops: int = 2) -> tuple:
    """
    Extract an ego-graph (neighborhood subgraph) around a given node.
    
    The ego-graph includes:
    - The center node
    - All predecessors within `hops` distance (incoming edges)
    - All successors within `hops` distance (outgoing edges)
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
        center_node (str): The center resource ID
        hops (int): Number of hops (default: 2)
    
    Returns:
        tuple: (subgraph_copy, nodes_in_subgraph)
            subgraph_copy (nx.DiGraph): The extracted ego-graph
            nodes_in_subgraph (Set[str]): Set of node IDs in the subgraph
    
    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edges_from([("vpc", "subnet"), ("subnet", "ec2"), ("ec2", "rds"), ("rds", "backup")])
        >>> subgraph, nodes = extract_subgraph(graph, "ec2", hops=2)
        >>> list(nodes)
        ['vpc', 'subnet', 'ec2', 'rds', 'backup']
    """
    # Validate node exists
    if center_node not in graph.nodes:
        return nx.DiGraph(), set()
    
    # Collect nodes within hop distance
    nodes_in_subgraph: Set[str] = {center_node}
    current_layer: Set[str] = {center_node}
    
    for _ in range(hops):
        next_layer: Set[str] = set()
        
        for node in current_layer:
            # Add predecessors (incoming edges)
            for predecessor in graph.predecessors(node):
                if predecessor != "internet":  # Exclude internet node
                    next_layer.add(predecessor)
            
            # Add successors (outgoing edges)
            for successor in graph.successors(node):
                if successor != "internet":  # Exclude internet node
                    next_layer.add(successor)
        
        # Add next layer to subgraph nodes
        nodes_in_subgraph.update(next_layer)
        current_layer = next_layer
    
    # Extract induced subgraph containing these nodes
    subgraph_copy = graph.subgraph(nodes_in_subgraph).copy()
    
    return subgraph_copy, nodes_in_subgraph


def get_immediate_neighbors(graph: nx.DiGraph, node_id: str) -> dict:
    """
    Get immediate predecessors and successors (1-hop neighbors).
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
        node_id (str): Resource ID to get neighbors for
    
    Returns:
        dict: {
            "predecessors": [list of incoming nodes (excluding "internet")],
            "successors": [list of outgoing nodes (excluding "internet")]
        }
    """
    if node_id not in graph.nodes:
        return {"predecessors": [], "successors": []}
    
    predecessors = [
        p for p in graph.predecessors(node_id) if p != "internet"
    ]
    successors = [
        s for s in graph.successors(node_id) if s != "internet"
    ]
    
    return {
        "predecessors": sorted(predecessors),
        "successors": sorted(successors)
    }


def count_hops_between(graph: nx.DiGraph, source: str, target: str) -> int:
    """
    Count the number of hops (edges) in the shortest path between two nodes.
    
    Used to determine if nodes are within 2-hop distance for cross-resource rules.
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
        source (str): Starting resource ID
        target (str): Destination resource ID
    
    Returns:
        int: Number of hops; -1 if no path exists
    
    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edges_from([("vpc", "subnet"), ("subnet", "ec2"), ("ec2", "rds")])
        >>> count_hops_between(graph, "subnet", "rds")
        2
    """
    # Check if both nodes exist
    if source not in graph.nodes or target not in graph.nodes:
        return -1
    
    # Find shortest path
    try:
        path = nx.shortest_path(graph, source, target)
        # Number of hops = number of edges = len(path) - 1
        return len(path) - 1
    except nx.NetworkXNoPath:
        # No path exists
        return -1


def get_reachable_within_hops(
    graph: nx.DiGraph, node_id: str, max_hops: int
) -> Set[str]:
    """
    Find all nodes reachable from a node within a maximum number of hops.
    
    Args:
        graph (nx.DiGraph): The NetworkX directed graph
        node_id (str): Starting resource ID
        max_hops (int): Maximum number of hops to traverse
    
    Returns:
        Set[str]: Set of reachable node IDs (excluding the start node and "internet")
    
    Example:
        >>> graph = nx.DiGraph()
        >>> graph.add_edges_from([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")])
        >>> get_reachable_within_hops(graph, "a", 2)
        {'b', 'c'}
    """
    if node_id not in graph.nodes:
        return set()
    
    reachable: Set[str] = set()
    visited: Set[str] = {node_id}
    queue: list[tuple[str, int]] = [(node_id, 0)]
    
    while queue:
        current_node, current_hops = queue.pop(0)
        
        if current_hops >= max_hops:
            continue
        
        for successor in graph.successors(current_node):
            if successor not in visited and successor != "internet":
                reachable.add(successor)
                visited.add(successor)
                queue.append((successor, current_hops + 1))
    
    return reachable
