"""
Tests for Steps 3 & 5: Serializer + POST /graph/build + POST /graph/diff endpoints.

Verifies:
  - serialize_graph() produces the correct D3-compatible dict
  - POST /graph/build returns 200 with correct JSON shape
  - POST /graph/diff returns correct added/removed nodes and edges
  - Node/edge counts match expectations
"""

from fastapi.testclient import TestClient

from services.graph_engine.main import app
from services.graph_engine.models import Resource
from services.graph_engine.builder import build_graph
from services.graph_engine.serializer import serialize_graph
from services.graph_engine.fixtures import BASE_RESOURCES, HEAD_RESOURCES

client = TestClient(app)


# --- Serializer unit tests ---

def test_serialize_graph_has_required_keys():
    """Serialized output must have 'nodes', 'edges', and 'metadata'."""
    resources = [Resource(**r) for r in BASE_RESOURCES]
    g = build_graph(resources)
    result = serialize_graph(g)
    assert "nodes" in result
    assert "edges" in result
    assert "metadata" in result


def test_serialize_graph_node_format():
    """Each node must have at least an 'id' key."""
    resources = [Resource(**r) for r in BASE_RESOURCES]
    g = build_graph(resources)
    result = serialize_graph(g)
    for node in result["nodes"]:
        assert "id" in node
        assert "type" in node


def test_serialize_graph_edge_format():
    """Each edge must have 'source', 'target', 'relationship', and enriched attrs."""
    resources = [Resource(**r) for r in BASE_RESOURCES]
    g = build_graph(resources)
    result = serialize_graph(g)
    for edge in result["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "relationship" in edge
        assert "direction" in edge
        assert "exposure_type" in edge


def test_serialize_graph_metadata_counts():
    """Metadata should report correct node and edge counts."""
    resources = [Resource(**r) for r in BASE_RESOURCES]
    g = build_graph(resources)
    result = serialize_graph(g)
    assert result["metadata"]["node_count"] == 5
    assert result["metadata"]["edge_count"] == 4


# --- Endpoint tests ---

def test_graph_build_endpoint_returns_200():
    """POST /graph/build with valid data should return 200."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    assert response.status_code == 200


def test_graph_build_endpoint_response_shape():
    """Response must have nodes, edges, metadata."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    assert "nodes" in data
    assert "edges" in data
    assert "metadata" in data


def test_graph_build_endpoint_node_count():
    """BASE_RESOURCES should produce 5 nodes (4 resources + internet)."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    assert len(data["nodes"]) == 5
    assert data["metadata"]["node_count"] == 5


def test_graph_build_endpoint_edge_count():
    """BASE_RESOURCES should produce 4 edges."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    assert len(data["edges"]) == 4
    assert data["metadata"]["edge_count"] == 4


def test_graph_build_endpoint_head_no_internet():
    """HEAD_RESOURCES has no 0.0.0.0/0 rule, so no internet node."""
    response = client.post("/graph/build", json={"resources": HEAD_RESOURCES})
    data = response.json()
    node_ids = [n["id"] for n in data["nodes"]]
    assert "internet" not in node_ids


def test_graph_build_endpoint_empty_resources():
    """An empty resource list should return an empty graph, not an error."""
    response = client.post("/graph/build", json={"resources": []})
    assert response.status_code == 200
    data = response.json()
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["metadata"]["node_count"] == 0


def test_graph_build_endpoint_invalid_body():
    """Missing 'resources' key should return 422 validation error."""
    response = client.post("/graph/build", json={"bad_key": []})
    assert response.status_code == 422


# --- POST /graph/diff endpoint tests ---

def test_graph_diff_endpoint_returns_200():
    """POST /graph/diff with valid data should return 200."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    assert response.status_code == 200


def test_graph_diff_endpoint_response_shape():
    """Response must have added_nodes, removed_nodes, added_edges, removed_edges."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert "added_nodes" in data
    assert "removed_nodes" in data
    assert "added_edges" in data
    assert "removed_edges" in data


def test_graph_diff_endpoint_added_nodes():
    """ec2-2 should appear in added_nodes."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert "ec2-2" in data["added_nodes"]


def test_graph_diff_endpoint_removed_nodes():
    """'internet' should appear in removed_nodes."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert "internet" in data["removed_nodes"]


def test_graph_diff_endpoint_added_edges():
    """New edges to ec2-2 should appear."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    sources_targets = [(e["source"], e["target"]) for e in data["added_edges"]]
    assert ("sg-1", "ec2-2") in sources_targets
    assert ("subnet-1", "ec2-2") in sources_targets


def test_graph_diff_endpoint_removed_edges():
    """internet → sg-1 edge should appear in removed_edges."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    sources_targets = [(e["source"], e["target"]) for e in data["removed_edges"]]
    assert ("internet", "sg-1") in sources_targets


def test_graph_diff_endpoint_identical_inputs():
    """Same base and head should return no changes."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": BASE_RESOURCES},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["added_nodes"] == []
    assert data["removed_nodes"] == []
    assert data["added_edges"] == []
    assert data["removed_edges"] == []


def test_graph_diff_endpoint_empty_inputs():
    """Empty base and head should return no changes."""
    response = client.post(
        "/graph/diff",
        json={"base": [], "head": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["added_nodes"] == []
    assert data["removed_nodes"] == []


def test_graph_diff_endpoint_invalid_body():
    """Missing required keys should return 422."""
    response = client.post("/graph/diff", json={"base": BASE_RESOURCES})
    assert response.status_code == 422


# --- Enriched edge attribute tests (via API) ---

def test_graph_build_internet_edge_has_port():
    """The internet→sg edge should carry port and protocol in API response."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    internet_edges = [e for e in data["edges"] if e["source"] == "internet"]
    assert len(internet_edges) == 1
    edge = internet_edges[0]
    assert edge["port"] == 22
    assert edge["protocol"] == "tcp"


def test_graph_build_internet_edge_exposure():
    """Internet edges should have direction=inbound and exposure_type=public."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    internet_edges = [e for e in data["edges"] if e["source"] == "internet"]
    edge = internet_edges[0]
    assert edge["direction"] == "inbound"
    assert edge["exposure_type"] == "public"


def test_graph_build_type_pair_edge_is_private():
    """Non-internet edges should have exposure_type=private."""
    response = client.post("/graph/build", json={"resources": BASE_RESOURCES})
    data = response.json()
    non_internet_edges = [e for e in data["edges"] if e["source"] != "internet"]
    for edge in non_internet_edges:
        assert edge["exposure_type"] == "private"
        assert edge["direction"] == "inbound"


# --- Enhanced diff response tests (via API) ---

def test_graph_diff_endpoint_has_enhanced_fields():
    """Diff response should include modified_nodes, newly_exposed, etc."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert "modified_nodes" in data
    assert "newly_exposed" in data
    assert "no_longer_exposed" in data
    assert "exposure_delta" in data


def test_graph_diff_endpoint_no_longer_exposed():
    """sg-1 should be no_longer_exposed (base has internet→sg-1, head does not)."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert "sg-1" in data["no_longer_exposed"]


def test_graph_diff_endpoint_exposure_delta_negative():
    """Exposure delta should be -1 (lost one public edge, gained none)."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": HEAD_RESOURCES},
    )
    data = response.json()
    assert data["exposure_delta"] == -1


def test_graph_diff_identical_has_zero_exposure_delta():
    """Identical inputs should have exposure_delta=0."""
    response = client.post(
        "/graph/diff",
        json={"base": BASE_RESOURCES, "head": BASE_RESOURCES},
    )
    data = response.json()
    assert data["exposure_delta"] == 0
    assert data["modified_nodes"] == []
    assert data["newly_exposed"] == []
    assert data["no_longer_exposed"] == []
