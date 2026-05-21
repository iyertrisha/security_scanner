"""
Tests for blast radius computation.
"""

import pytest
import networkx as nx

from services.graph_engine.blast_radius import (
    compute_blast_radius,
    compute_all_blast_radius,
    get_blast_radius,
)


@pytest.fixture
def simple_graph():
    """
    Simple linear graph:
    internet → sg-1 → ec2-1 → rds-1 → backup-1
    """
    g = nx.DiGraph()
    g.add_edge("internet", "sg-1", relationship="exposes")
    g.add_edge("sg-1", "ec2-1", relationship="protects")
    g.add_edge("ec2-1", "rds-1", relationship="accesses")
    g.add_edge("rds-1", "backup-1", relationship="writes")
    
    for node in g.nodes():
        g.nodes[node]["type"] = "resource"
    
    return g


@pytest.fixture
def branching_graph():
    """
    Branching graph:
           ec2-1 → rds-1
          /         
vpc-1 → subnet-1 
          \
           ec2-2 → s3-1
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


@pytest.fixture
def cyclic_graph():
    """
    Cyclic graph to test handling of cycles:
    ec2-1 → rds-1 → backup-1 → ec2-1 (cycle)
    """
    g = nx.DiGraph()
    g.add_edge("ec2-1", "rds-1", relationship="writes")
    g.add_edge("rds-1", "backup-1", relationship="backs_up")
    g.add_edge("backup-1", "ec2-1", relationship="restores")
    
    for node in g.nodes():
        g.nodes[node]["type"] = "resource"
    
    return g


class TestComputeBlastRadius:
    """Tests for compute_blast_radius function."""

    def test_linear_graph(self, simple_graph):
        """In linear graph, blast radius grows downstream."""
        # From internet: can reach all downstream nodes except internet itself
        result = compute_blast_radius(simple_graph, "internet")
        assert result["count"] == 4
        assert set(result["resources"]) == {"sg-1", "ec2-1", "rds-1", "backup-1"}

    def test_blast_radius_from_middle(self, simple_graph):
        """Blast radius from middle node includes only downstream."""
        result = compute_blast_radius(simple_graph, "ec2-1")
        assert result["count"] == 2
        assert set(result["resources"]) == {"rds-1", "backup-1"}

    def test_blast_radius_from_leaf(self, simple_graph):
        """Blast radius from leaf node is 0."""
        result = compute_blast_radius(simple_graph, "backup-1")
        assert result["count"] == 0
        assert result["resources"] == []

    def test_branching_blast_radius(self, branching_graph):
        """Blast radius includes all reachable branches."""
        result = compute_blast_radius(branching_graph, "subnet-1")
        assert result["count"] == 4
        assert set(result["resources"]) == {"ec2-1", "ec2-2", "rds-1", "s3-1"}

    def test_blast_radius_nonexistent_node(self, simple_graph):
        """Blast radius for nonexistent node returns 0."""
        result = compute_blast_radius(simple_graph, "nonexistent")
        assert result["count"] == 0
        assert result["resources"] == []

    def test_cyclic_graph_blast_radius(self, cyclic_graph):
        """Cyclic graph is properly handled (no infinite loop)."""
        result = compute_blast_radius(cyclic_graph, "ec2-1")
        # From ec2-1: rds-1, backup-1
        # But due to cycle, can also reach ec2-1 again (visited prevents reread)
        assert result["count"] == 2
        assert set(result["resources"]) == {"rds-1", "backup-1"}

    def test_internet_excluded_from_blast_radius(self, simple_graph):
        """Internet node should never be included as reachable."""
        for node in simple_graph.nodes():
            result = compute_blast_radius(simple_graph, node)
            assert "internet" not in result["resources"]


class TestComputeAllBlastRadius:
    """Tests for compute_all_blast_radius function."""

    def test_all_nodes_covered(self, branching_graph):
        """All resource nodes (not internet) should have entries."""
        result = compute_all_blast_radius(branching_graph)
        
        expected_nodes = {"vpc-1", "subnet-1", "ec2-1", "ec2-2", "rds-1", "s3-1"}
        assert set(result.keys()) == expected_nodes

    def test_internet_excluded_from_keys(self, simple_graph):
        """Internet node should not be in the blast radius map."""
        result = compute_all_blast_radius(simple_graph)
        assert "internet" not in result

    def test_blast_radius_values_structure(self, branching_graph):
        """Each blast radius value should have count and resources."""
        result = compute_all_blast_radius(branching_graph)
        
        for node_id, br_data in result.items():
            assert "count" in br_data
            assert "resources" in br_data
            assert isinstance(br_data["count"], int)
            assert isinstance(br_data["resources"], list)

    def test_empty_graph(self):
        """Empty graph produces empty map."""
        g = nx.DiGraph()
        result = compute_all_blast_radius(g)
        assert result == {}


class TestGetBlastRadius:
    """Tests for get_blast_radius utility function."""

    def test_existing_node(self, simple_graph):
        """Retrieving blast radius for existing node."""
        br_map = compute_all_blast_radius(simple_graph)
        result = get_blast_radius(br_map, "ec2-1")
        
        assert result["count"] == 2
        assert set(result["resources"]) == {"rds-1", "backup-1"}

    def test_nonexistent_node(self, simple_graph):
        """Retrieving blast radius for nonexistent node returns empty."""
        br_map = compute_all_blast_radius(simple_graph)
        result = get_blast_radius(br_map, "nonexistent")
        
        assert result == {"count": 0, "resources": []}


class TestBlastRadiusIntegration:
    """Integration tests combining multiple components."""

    def test_blast_radius_consistency(self):
        """Blast radius map matches individual computations."""
        g = nx.DiGraph()
        g.add_edges_from([
            ("a", "b"),
            ("b", "c"),
            ("b", "d"),
            ("c", "e"),
        ])
        
        br_map = compute_all_blast_radius(g)
        
        # Verify that map results match individual computations
        for node in g.nodes():
            assert br_map[node] == compute_blast_radius(g, node)

    def test_sorted_resources(self):
        """Resources in blast radius are always sorted."""
        g = nx.DiGraph()
        g.add_edges_from([
            ("z", "y"),
            ("z", "a"),
            ("z", "m"),
        ])
        
        result = compute_blast_radius(g, "z")
        
        assert result["resources"] == sorted(result["resources"])
