from tests.contracts.parser_service_payload import sample_parser_payload
from services.api.main import _build_graph_resource


def test_parser_contract_has_v2_fields():
    payload = sample_parser_payload()
    assert "resources" in payload
    assert "module_sources" in payload
    assert isinstance(payload["resources"], list)
    assert isinstance(payload["module_sources"], list)


def test_parser_to_graph_contract_transform():
    payload = sample_parser_payload()
    graph_resource = _build_graph_resource(payload["resources"][0])
    assert "resource_id" in graph_resource
    assert "type" in graph_resource
    assert "provider" in graph_resource
    assert "rules" in graph_resource


def test_parser_to_risk_contract_transform():
    payload = sample_parser_payload()
    resource = payload["resources"][0]
    assert "resource_id" in resource
    assert "resource_type" in resource
    assert "provider" in resource
    assert "inbound_rules" in resource
    assert "outbound_rules" in resource
