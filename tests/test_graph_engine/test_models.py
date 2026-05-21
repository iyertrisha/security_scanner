"""
Tests for Step 1: Validate that Pydantic models and fixture data work together.

If these pass, we know:
  - The models are correctly defined
  - The fixture data matches the expected shape
  - We have a solid foundation for building graph logic on top
"""

from services.graph_engine.models import (
    Rule,
    Resource,
    GraphBuildRequest,
    GraphDiffRequest,
)
from services.graph_engine.fixtures import BASE_RESOURCES, HEAD_RESOURCES


def test_rule_model():
    """A Rule can be constructed directly from field values."""
    rule = Rule(port=22, protocol="tcp", cidr="0.0.0.0/0")
    assert rule.port == 22
    assert rule.protocol == "tcp"
    assert rule.cidr == "0.0.0.0/0"


def test_resource_model_parses_base_fixtures():
    """Every item in BASE_RESOURCES can be parsed into a Resource model."""
    for raw in BASE_RESOURCES:
        resource = Resource(**raw)
        assert resource.resource_id
        assert resource.type
        assert resource.provider


def test_resource_model_parses_head_fixtures():
    """Every item in HEAD_RESOURCES can be parsed into a Resource model."""
    for raw in HEAD_RESOURCES:
        resource = Resource(**raw)
        assert resource.resource_id
        assert resource.type
        assert resource.provider


def test_build_request_from_fixtures():
    """A GraphBuildRequest can be constructed from the base fixture data."""
    request = GraphBuildRequest(resources=BASE_RESOURCES)
    assert len(request.resources) == len(BASE_RESOURCES)
    # Each resource should be a proper Resource model instance
    for r in request.resources:
        assert isinstance(r, Resource)


def test_diff_request_from_fixtures():
    """A GraphDiffRequest can be constructed from base + head fixture data."""
    request = GraphDiffRequest(base=BASE_RESOURCES, head=HEAD_RESOURCES)
    assert len(request.base) == len(BASE_RESOURCES)
    assert len(request.head) == len(HEAD_RESOURCES)


def test_security_group_has_rules():
    """The security group in BASE_RESOURCES has rules attached to it."""
    sg_data = [r for r in BASE_RESOURCES if r["type"] == "security_group"][0]
    sg = Resource(**sg_data)
    assert len(sg.rules) == 1
    assert sg.rules[0].port == 22
    assert sg.rules[0].cidr == "0.0.0.0/0"


def test_ec2_instance_has_no_rules():
    """An EC2 instance has an empty rules list by default."""
    ec2_data = [r for r in BASE_RESOURCES if r["type"] == "ec2_instance"][0]
    ec2 = Resource(**ec2_data)
    assert ec2.rules == []
