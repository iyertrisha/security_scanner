"""
Tests for Step 4: Graph diff logic.

Uses BASE_RESOURCES and HEAD_RESOURCES fixtures to verify that
diff_graphs() correctly detects:
  - added nodes (ec2-2 added in HEAD)
  - removed nodes (internet gone in HEAD because CIDR changed)
  - added edges (new connections to ec2-2)
  - removed edges (internet → sg-1 gone)
"""

from services.graph_engine.builder import build_graph
from services.graph_engine.differ import diff_graphs
from services.graph_engine.models import Resource
from services.graph_engine.fixtures import BASE_RESOURCES, HEAD_RESOURCES


def _make_graphs():
    """Helper: build base and head graphs from fixtures."""
    base = build_graph([Resource(**r) for r in BASE_RESOURCES])
    head = build_graph([Resource(**r) for r in HEAD_RESOURCES])
    return base, head


# --- Added nodes ---

def test_diff_added_nodes():
    """ec2-2 was added in HEAD."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert "ec2-2" in result["added_nodes"]


def test_diff_added_nodes_count():
    """Only one node was added."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert len(result["added_nodes"]) == 1


# --- Removed nodes ---

def test_diff_removed_nodes():
    """'internet' node was removed (CIDR changed from 0.0.0.0/0)."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert "internet" in result["removed_nodes"]


def test_diff_removed_nodes_count():
    """Only one node was removed."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert len(result["removed_nodes"]) == 1


# --- Added edges ---

def test_diff_added_edges_contain_sg_to_ec2_2():
    """sg-1 → ec2-2 is a new edge in HEAD."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    sources_targets = [(e["source"], e["target"]) for e in result["added_edges"]]
    assert ("sg-1", "ec2-2") in sources_targets


def test_diff_added_edges_contain_subnet_to_ec2_2():
    """subnet-1 → ec2-2 is a new edge in HEAD."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    sources_targets = [(e["source"], e["target"]) for e in result["added_edges"]]
    assert ("subnet-1", "ec2-2") in sources_targets


def test_diff_added_edges_count():
    """Two new edges: sg-1→ec2-2 and subnet-1→ec2-2."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert len(result["added_edges"]) == 2


# --- Removed edges ---

def test_diff_removed_edges_contain_internet_to_sg():
    """internet → sg-1 edge was removed."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    sources_targets = [(e["source"], e["target"]) for e in result["removed_edges"]]
    assert ("internet", "sg-1") in sources_targets


def test_diff_removed_edges_have_relationship():
    """Removed edges should include the relationship label."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    for edge in result["removed_edges"]:
        assert "relationship" in edge


def test_diff_removed_edges_count():
    """One edge removed: internet→sg-1."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert len(result["removed_edges"]) == 1


# --- Identical graphs ---

def test_diff_identical_graphs_returns_empty():
    """Diffing a graph against itself should produce no changes."""
    base = build_graph([Resource(**r) for r in BASE_RESOURCES])
    result = diff_graphs(base, base)
    assert result["added_nodes"] == []
    assert result["removed_nodes"] == []
    assert result["added_edges"] == []
    assert result["removed_edges"] == []


# --- Empty graphs ---

def test_diff_empty_graphs():
    """Diffing two empty graphs should produce no changes."""
    import networkx as nx
    empty = nx.DiGraph()
    result = diff_graphs(empty, empty)
    assert result["added_nodes"] == []
    assert result["removed_nodes"] == []


# --- Modified nodes ---

def test_diff_no_modified_nodes_in_fixtures():
    """Node attributes (type, provider) don't change in our fixtures."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    # sg-1 exists in both but node-level attrs (type, provider) are the same
    assert result["modified_nodes"] == []


def test_diff_detects_modified_node():
    """If a node's attributes change, it should appear in modified_nodes."""
    import networkx as nx
    base = nx.DiGraph()
    base.add_node("r-1", type="vpc", provider="aws")
    head = nx.DiGraph()
    head.add_node("r-1", type="vpc", provider="gcp")  # provider changed
    result = diff_graphs(base, head)
    assert "r-1" in result["modified_nodes"]


# --- Exposure detection ---

def test_diff_no_longer_exposed():
    """sg-1 was internet-exposed in base but not in head."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert "sg-1" in result["no_longer_exposed"]


def test_diff_newly_exposed_empty():
    """No resource became newly internet-exposed in HEAD."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert result["newly_exposed"] == []


def test_diff_exposure_delta_negative():
    """Exposure decreased: one public edge removed, none added."""
    base, head = _make_graphs()
    result = diff_graphs(base, head)
    assert result["exposure_delta"] == -1


def test_diff_exposure_delta_positive():
    """When a public edge is added, exposure_delta should be positive."""
    # Reverse: head is the one with internet exposure
    base, head = _make_graphs()
    result = diff_graphs(head, base)  # swap!
    assert result["exposure_delta"] == 1
    assert "sg-1" in result["newly_exposed"]
