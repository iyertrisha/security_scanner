"""
Tests for subgraph extraction.
"""

import pytest
import networkx as nx

from services.graph_engine.subgraph import (
    extract_subgraph,
    get_immediate_neighbors,
    count_hops_between,
    get_reachable_within_hops,
)


@pytest.fixture
def sample_graph():
    """
    Sample graph structure:
    
    internet → sg-1
               ↓ (protects)
               ec2-1 → rds-1 → backup-1
               ↓ (accesses)
               s3-1
    """
    g = nx.DiGraph()
    g.add_edge("internet", "sg-1", relationship="exposes")
    g.add_edge("sg-1", "ec2-1", relationship="protects")
    g.add_edge("ec2-1", "rds-1", relationship="accesses")
    g.add_edge("rds-1", "backup-1", relationship="backs_up")
    g.add_edge("ec2-1", "s3-1", relationship="accesses")
    
    for node in g.nodes():
        g.nodes[node]["type"] = "resource"
    
    return g


@pytest.fixture
def branching_graph():
    """
    Branching graph:
    
         vpc-1
           ↓ (contains)
        subnet-1
         ↙   ↘
      ec2-1  ec2-2
       ↓       ↓
     rds-1    s3-1
    """
    g = nx.DiGraph()
    g.add_edge("vpc-1", "subnet-1", relationship="contains")
    g.add_edge("subnet-1", "ec2-1", relationship="places")
    g.add_edge("subnet-1", "ec2-2", relationship="places")
    g.add_edge("ec2-1", "rds-1", relationship="accesses")
    g.add_edge("ec2-2", "s3-1", relationship="accesses")
    
    for node in g.nodes():
        g.nodes[node]["type"] = "resource"
    
    return g


class TestExtractSubgraph:
    """Tests for extract_subgraph function."""

    def test_2hop_subgraph_from_middle(self, sample_graph):
        """Extract 2-hop neighborhood around ec2-1."""
        subgraph, nodes = extract_subgraph(sample_graph, "ec2-1", hops=2)
        
        # ec2-1 itself
        # Predecessors: sg-1, internet (1 hop)
        # Successors: rds-1, s3-1 (1 hop)
        # 2-hop successors: backup-1 (from rds-1)
        # Internet node should be excluded
        assert "ec2-1" in nodes
        assert "sg-1" in nodes
        assert "rds-1" in nodes
        assert "s3-1" in nodes
        assert "backup-1" in nodes
        assert "internet" not in nodes

    def test_1hop_subgraph(self, sample_graph):
        """Extract 1-hop neighborhood."""
        subgraph, nodes = extract_subgraph(sample_graph, "ec2-1", hops=1)
        
        # ec2-1 itself
        # 1-hop predecessors: sg-1
        # 1-hop successors: rds-1, s3-1
        assert "ec2-1" in nodes
        assert "sg-1" in nodes
        assert "rds-1" in nodes
        assert "s3-1" in nodes
        # 2-hop successors should not be included
        assert "backup-1" not in nodes
        assert "internet" not in nodes

    def test_zero_hops(self, sample_graph):
        """Zero hops should return only the center node."""
        subgraph, nodes = extract_subgraph(sample_graph, "ec2-1", hops=0)
        
        assert nodes == {"ec2-1"}
        assert len(subgraph.nodes()) == 1

    def test_subgraph_preserves_edges(self, sample_graph):
        """Extracted subgraph should preserve edges between included nodes."""
        subgraph, nodes = extract_subgraph(sample_graph, "ec2-1", hops=1)
        
        # Check that key edges exist in subgraph
        assert subgraph.has_edge("ec2-1", "rds-1")
        assert subgraph.has_edge("ec2-1", "s3-1")
        assert subgraph.has_edge("sg-1", "ec2-1")

    def test_nonexistent_center_node(self, sample_graph):
        """Subgraph of nonexistent node should be empty."""
        subgraph, nodes = extract_subgraph(sample_graph, "nonexistent", hops=2)
        
        assert len(nodes) == 0
        assert subgraph.number_of_nodes() == 0

    def test_subgraph_is_copy(self, sample_graph):
        """Extracted subgraph should be a copy, not a view."""
        subgraph, _ = extract_subgraph(sample_graph, "ec2-1", hops=1)
        
        # Modify subgraph
        subgraph.add_node("new_node")
        
        # Original should be unchanged
        assert "new_node" not in sample_graph.nodes()


class TestGetImmediateNeighbors:
    """Tests for get_immediate_neighbors function."""

    def test_neighbors_with_both_directions(self, sample_graph):
        """Get both predecessors and successors."""
        result = get_immediate_neighbors(sample_graph, "ec2-1")
        
        assert "sg-1" in result["predecessors"]
        assert set(result["successors"]) == {"rds-1", "s3-1"}

    def test_neighbors_internet_excluded(self, sample_graph):
        """Internet node should not appear in neighbors."""
        result = get_immediate_neighbors(sample_graph, "sg-1")
        
        assert "internet" not in result["predecessors"]
        assert "internet" not in result["successors"]

    def test_leaf_node_neighbors(self, sample_graph):
        """Leaf node has only predecessors, no successors."""
        result = get_immediate_neighbors(sample_graph, "backup-1")
        
        assert len(result["successors"]) == 0
        assert "rds-1" in result["predecessors"]

    def test_root_node_neighbors(self, sample_graph):
        """Root node (after excluding internet) might have only successors."""
        result = get_immediate_neighbors(sample_graph, "sg-1")
        
        assert "internet" not in result["predecessors"]
        assert "ec2-1" in result["successors"]

    def test_nonexistent_node(self, sample_graph):
        """Neighbors of nonexistent node should be empty."""
        result = get_immediate_neighbors(sample_graph, "nonexistent")
        
        assert result["predecessors"] == []
        assert result["successors"] == []

    def test_neighbors_sorted(self, branching_graph):
        """Neighbors should be sorted."""
        result = get_immediate_neighbors(branching_graph, "subnet-1")
        
        assert result["successors"] == sorted(result["successors"])


class TestCountHopsBetween:
    """Tests for count_hops_between function."""

    def test_direct_connection(self, sample_graph):
        """Directly connected nodes have 1 hop between them."""
        assert count_hops_between(sample_graph, "ec2-1", "rds-1") == 1

    def test_two_hops(self, sample_graph):
        """Two-edge paths have 2 hops."""
        assert count_hops_between(sample_graph, "ec2-1", "backup-1") == 2

    def test_longer_path(self, sample_graph):
        """Longer paths count correctly."""
        assert count_hops_between(sample_graph, "sg-1", "backup-1") == 3

    def test_no_path(self, sample_graph):
        """Unconnected nodes return -1."""
        assert count_hops_between(sample_graph, "backup-1", "s3-1") == -1

    def test_self_loops(self, sample_graph):
        """Same node to itself is 0 hops."""
        assert count_hops_between(sample_graph, "ec2-1", "ec2-1") == 0

    def test_nonexistent_source(self, sample_graph):
        """Nonexistent source returns -1."""
        assert count_hops_between(sample_graph, "nonexistent", "ec2-1") == -1

    def test_nonexistent_target(self, sample_graph):
        """Nonexistent target returns -1."""
        assert count_hops_between(sample_graph, "ec2-1", "nonexistent") == -1


class TestGetReachableWithinHops:
    """Tests for get_reachable_within_hops function."""

    def test_reachable_within_2_hops(self, sample_graph):
        """Nodes within 2 hops should be reachable."""
        reachable = get_reachable_within_hops(sample_graph, "ec2-1", 2)
        
        assert "rds-1" in reachable
        assert "s3-1" in reachable
        assert "backup-1" in reachable
        assert "sg-1" not in reachable  # upstream
        assert "ec2-1" not in reachable  # itself

    def test_reachable_within_1_hop(self, sample_graph):
        """Only immediate successors within 1 hop."""
        reachable = get_reachable_within_hops(sample_graph, "ec2-1", 1)
        
        assert "rds-1" in reachable
        assert "s3-1" in reachable
        assert "backup-1" not in reachable

    def test_reachable_zero_hops(self, sample_graph):
        """Zero hops should give empty set."""
        reachable = get_reachable_within_hops(sample_graph, "ec2-1", 0)
        assert len(reachable) == 0

    def test_internet_excluded(self, sample_graph):
        """Internet node should never be reachable."""
        reachable = get_reachable_within_hops(sample_graph, "internet", 3)
        assert "internet" not in reachable

    def test_nonexistent_start_node(self, sample_graph):
        """Starting from nonexistent node returns empty."""
        reachable = get_reachable_within_hops(sample_graph, "nonexistent", 2)
        assert len(reachable) == 0

    def test_leaf_node_reachable(self, sample_graph):
        """From leaf node, nothing is reachable."""
        reachable = get_reachable_within_hops(sample_graph, "backup-1", 3)
        assert len(reachable) == 0


class TestSubgraphIntegration:
    """Integration tests combining multiple subgraph operations."""

    def test_neighbors_and_hops_consistency(self, sample_graph):
        """1-hop neighbors should match 1-hop reachable."""
        neighbors = get_immediate_neighbors(sample_graph, "ec2-1")
        reachable = get_reachable_within_hops(sample_graph, "ec2-1", 1)
        
        assert set(neighbors["successors"]) == reachable

    def test_full_subgraph_extraction_workflow(self, branching_graph):
        """Full workflow: extract subgraph, get neighbors, count hops."""
        # Extract 2-hop subgraph around ec2-1
        subgraph, nodes = extract_subgraph(branching_graph, "ec2-1", hops=2)
        
        # Get immediate neighbors within subgraph
        neighbors = get_immediate_neighbors(subgraph, "ec2-1")
        
        # Count hops from ec2-1 to rds-1
        hops = count_hops_between(subgraph, "ec2-1", "rds-1")
        
        assert "rds-1" in neighbors["successors"]
        assert hops == 1
