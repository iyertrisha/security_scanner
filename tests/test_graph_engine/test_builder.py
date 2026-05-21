"""
Tests for Step 2: Graph builder logic.

Verifies that build_graph() correctly:
  - Creates nodes for every resource
  - Adds an 'internet' node when cidr is 0.0.0.0/0
  - Connects resources with the right edges based on type rules
  - Does NOT add an internet node when no rule has 0.0.0.0/0
"""

from services.graph_engine.builder import build_graph
from services.graph_engine.models import Resource
from services.graph_engine.fixtures import BASE_RESOURCES, HEAD_RESOURCES


def _build_from_raw(raw_list: list[dict]):
    """Helper: convert raw dicts → Resource models → graph."""
    resources = [Resource(**r) for r in raw_list]
    return build_graph(resources)


# --- Node tests ---

def test_base_graph_has_correct_node_count():
    """BASE has 4 resources + 1 internet node = 5 nodes."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.number_of_nodes() == 5


def test_base_graph_has_internet_node():
    """BASE has a security group with 0.0.0.0/0, so 'internet' node must exist."""
    g = _build_from_raw(BASE_RESOURCES)
    assert "internet" in g.nodes


def test_head_graph_has_no_internet_node():
    """HEAD changed CIDR to 10.0.0.0/16, so no internet node should exist."""
    g = _build_from_raw(HEAD_RESOURCES)
    assert "internet" not in g.nodes


def test_head_graph_has_correct_node_count():
    """HEAD has 5 resources (added ec2-2), no internet node = 5 nodes."""
    g = _build_from_raw(HEAD_RESOURCES)
    assert g.number_of_nodes() == 5


# --- Edge tests ---

def test_base_graph_has_internet_to_sg_edge():
    """internet → sg-1 edge should exist in BASE."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.has_edge("internet", "sg-1")
    assert g.edges["internet", "sg-1"]["relationship"] == "exposes"


def test_base_graph_has_sg_to_ec2_edge():
    """sg-1 → ec2-1 (protects) should exist."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.has_edge("sg-1", "ec2-1")
    assert g.edges["sg-1", "ec2-1"]["relationship"] == "protects"


def test_base_graph_has_vpc_to_subnet_edge():
    """vpc-1 → subnet-1 (contains) should exist."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.has_edge("vpc-1", "subnet-1")
    assert g.edges["vpc-1", "subnet-1"]["relationship"] == "contains"


def test_base_graph_has_subnet_to_ec2_edge():
    """subnet-1 → ec2-1 (places) should exist."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.has_edge("subnet-1", "ec2-1")
    assert g.edges["subnet-1", "ec2-1"]["relationship"] == "places"


def test_base_graph_edge_count():
    """BASE should have 4 edges: internet→sg, vpc→subnet, subnet→ec2, sg→ec2."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.number_of_edges() == 4


def test_head_graph_has_sg_to_both_ec2_edges():
    """HEAD has ec2-1 and ec2-2, so sg-1 should connect to both."""
    g = _build_from_raw(HEAD_RESOURCES)
    assert g.has_edge("sg-1", "ec2-1")
    assert g.has_edge("sg-1", "ec2-2")


# --- Node attribute tests ---

def test_node_attributes_are_set():
    """Each resource node should carry type and provider attributes."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.nodes["ec2-1"]["type"] == "ec2_instance"
    assert g.nodes["ec2-1"]["provider"] == "aws"
    assert g.nodes["internet"]["type"] == "internet"


# --- Enriched edge attribute tests ---

def test_internet_edge_has_port_and_protocol():
    """internet → sg-1 edge should carry port=22 and protocol=tcp."""
    g = _build_from_raw(BASE_RESOURCES)
    edge = g.edges["internet", "sg-1"]
    assert edge["port"] == 22
    assert edge["protocol"] == "tcp"


def test_internet_edge_has_direction_and_exposure():
    """internet → sg-1 edge should be inbound and public."""
    g = _build_from_raw(BASE_RESOURCES)
    edge = g.edges["internet", "sg-1"]
    assert edge["direction"] == "inbound"
    assert edge["exposure_type"] == "public"


def test_type_pair_edges_are_private():
    """Non-internet edges should be private by default."""
    g = _build_from_raw(BASE_RESOURCES)
    assert g.edges["vpc-1", "subnet-1"]["exposure_type"] == "private"
    assert g.edges["sg-1", "ec2-1"]["exposure_type"] == "private"
    assert g.edges["subnet-1", "ec2-1"]["exposure_type"] == "private"
