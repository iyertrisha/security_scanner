"""
Tests for Step 6: Edge cases and input hardening.

Covers:
  - Unknown resource types (node created, no edges inferred)
  - Duplicate resource_ids (last-write-wins)
  - Single resource (no edges possible)
  - Multiple security groups with internet exposure
  - Security group with multiple rules (only one internet edge)
  - Validation errors via endpoint (missing fields, bad types)
"""

import pytest
from fastapi.testclient import TestClient

from services.graph_engine.main import app
from services.graph_engine.models import Resource
from services.graph_engine.builder import build_graph

client = TestClient(app)


# --- Unknown resource types ---

def test_unknown_type_becomes_node():
    """A resource with an unrecognized type should still become a node."""
    resources = [Resource(resource_id="x-1", type="load_balancer", provider="aws")]
    g = build_graph(resources)
    assert "x-1" in g.nodes
    assert g.nodes["x-1"]["type"] == "load_balancer"


def test_unknown_type_has_no_edges():
    """Unknown types don't match any edge rule, so no edges are inferred."""
    resources = [
        Resource(resource_id="x-1", type="load_balancer", provider="aws"),
        Resource(resource_id="ec2-1", type="ec2_instance", provider="aws"),
    ]
    g = build_graph(resources)
    assert g.number_of_edges() == 0


def test_unknown_type_mixed_with_known():
    """Unknown types coexist with known types; only known edges are created."""
    resources = [
        Resource(resource_id="vpc-1", type="vpc", provider="aws"),
        Resource(resource_id="subnet-1", type="subnet", provider="aws"),
        Resource(resource_id="lb-1", type="load_balancer", provider="aws"),
    ]
    g = build_graph(resources)
    assert g.number_of_nodes() == 3
    assert g.has_edge("vpc-1", "subnet-1")
    assert g.number_of_edges() == 1  # only vpc→subnet


# --- Duplicate resource_ids ---

def test_duplicate_ids_last_write_wins():
    """If two resources share the same ID, the last one's attributes win."""
    resources = [
        Resource(resource_id="r-1", type="vpc", provider="aws"),
        Resource(resource_id="r-1", type="subnet", provider="gcp"),
    ]
    g = build_graph(resources)
    assert g.number_of_nodes() == 1
    assert g.nodes["r-1"]["type"] == "subnet"
    assert g.nodes["r-1"]["provider"] == "gcp"


# --- Single resource ---

def test_single_resource_no_edges():
    """A graph with one resource should have one node and zero edges."""
    resources = [Resource(resource_id="ec2-1", type="ec2_instance", provider="aws")]
    g = build_graph(resources)
    assert g.number_of_nodes() == 1
    assert g.number_of_edges() == 0


# --- Multiple security groups with internet exposure ---

def test_multiple_sgs_with_internet():
    """Each internet-exposed SG gets its own edge from the internet node."""
    resources = [
        Resource(
            resource_id="sg-1",
            type="security_group",
            provider="aws",
            rules=[{"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"}],
        ),
        Resource(
            resource_id="sg-2",
            type="security_group",
            provider="aws",
            rules=[{"port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"}],
        ),
    ]
    g = build_graph(resources)
    assert "internet" in g.nodes
    assert g.has_edge("internet", "sg-1")
    assert g.has_edge("internet", "sg-2")


def test_sg_with_multiple_rules_one_internet_edge():
    """A SG with multiple rules (some 0.0.0.0/0) still gets only one internet edge."""
    resources = [
        Resource(
            resource_id="sg-1",
            type="security_group",
            provider="aws",
            rules=[
                {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"},
                {"port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"},
                {"port": 3306, "protocol": "tcp", "cidr": "10.0.0.0/16"},
            ],
        ),
    ]
    g = build_graph(resources)
    # Only one edge from internet to sg-1, not two
    internet_edges = [(u, v) for u, v in g.edges if u == "internet"]
    assert len(internet_edges) == 1


def test_sg_without_internet_rule_no_internet_node():
    """A SG with only private CIDRs should not create an internet node."""
    resources = [
        Resource(
            resource_id="sg-1",
            type="security_group",
            provider="aws",
            rules=[{"port": 22, "protocol": "tcp", "cidr": "10.0.0.0/16"}],
        ),
    ]
    g = build_graph(resources)
    assert "internet" not in g.nodes


# --- Endpoint validation errors ---

def test_build_endpoint_missing_resource_id():
    """A resource missing resource_id should trigger 422."""
    response = client.post(
        "/graph/build",
        json={"resources": [{"type": "vpc", "provider": "aws"}]},
    )
    assert response.status_code == 422


def test_build_endpoint_bad_rule_type():
    """A rule with port as a string should trigger 422."""
    response = client.post(
        "/graph/build",
        json={
            "resources": [
                {
                    "resource_id": "sg-1",
                    "type": "security_group",
                    "provider": "aws",
                    "rules": [{"port": "not-a-number", "protocol": "tcp", "cidr": "0.0.0.0/0"}],
                }
            ]
        },
    )
    assert response.status_code == 422


def test_diff_endpoint_missing_head():
    """Diff request missing 'head' should trigger 422."""
    response = client.post(
        "/graph/diff",
        json={"base": []},
    )
    assert response.status_code == 422


def test_build_endpoint_empty_body():
    """Completely empty JSON body should trigger 422."""
    response = client.post("/graph/build", json={})
    assert response.status_code == 422
