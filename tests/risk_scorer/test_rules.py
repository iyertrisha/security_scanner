"""
Unit tests for all 11 deterministic security rules.
Each rule has:
  - one test where it FIRES (dangerous config)
  - one test where it does NOT fire (safe config)
"""
import pytest
from services.risk_scorer.schemas import Resource, Severity
from services.risk_scorer.rules.rules import (
    check_ssh_rdp_public,
    check_public_db_port,
    check_public_s3,
    check_all_ports_open,
    check_http_without_https,
    check_permissive_iam,
    check_missing_network_policy,
    check_privileged_container,
    check_unauthenticated_service,
    check_unencrypted_storage,
    check_missing_tags,
)


def make_resource(**kwargs) -> Resource:
    defaults = dict(
        resource_id="test.resource",
        resource_type="aws_security_group",
        provider="aws",
        properties={},
        inbound_rules=[],
        outbound_rules=[],
        tags={"environment": "test", "owner": "mohit", "project": "netguard"},
    )
    defaults.update(kwargs)
    return Resource(**defaults)


def make_rule(port, cidr="0.0.0.0/0", protocol="tcp"):
    return {"port": str(port), "protocol": protocol, "cidr": cidr}


def test_ssh_public_fires():
    r = make_resource(inbound_rules=[make_rule(22)])
    finding = check_ssh_rdp_public(r)
    assert finding is not None
    assert finding.severity == Severity.CRITICAL
    assert finding.finding_type == "SSH_EXPOSED_TO_PUBLIC"


def test_rdp_public_fires():
    r = make_resource(inbound_rules=[make_rule(3389)])
    finding = check_ssh_rdp_public(r)
    assert finding is not None
    assert finding.finding_type == "RDP_EXPOSED_TO_PUBLIC"


def test_ssh_private_cidr_no_fire():
    r = make_resource(inbound_rules=[make_rule(22, cidr="10.0.0.0/8")])
    assert check_ssh_rdp_public(r) is None


def test_postgres_public_fires():
    r = make_resource(inbound_rules=[make_rule(5432)])
    finding = check_public_db_port(r)
    assert finding is not None
    assert finding.severity == Severity.CRITICAL


def test_mysql_public_fires():
    r = make_resource(inbound_rules=[make_rule(3306)])
    assert check_public_db_port(r) is not None


def test_db_private_no_fire():
    r = make_resource(inbound_rules=[make_rule(5432, cidr="10.0.0.0/8")])
    assert check_public_db_port(r) is None


def test_s3_public_acl_fires():
    r = make_resource(resource_type="aws_s3_bucket", properties={"acl": "public-read"})
    finding = check_public_s3(r)
    assert finding is not None
    assert finding.severity == Severity.CRITICAL


def test_s3_private_no_fire():
    r = make_resource(resource_type="aws_s3_bucket", properties={"acl": "private", "block_public_acls": True})
    assert check_public_s3(r) is None


def test_non_s3_no_fire():
    r = make_resource(resource_type="aws_security_group", properties={"acl": "public-read"})
    assert check_public_s3(r) is None


def test_all_ports_fires():
    r = make_resource(inbound_rules=[make_rule(0)])
    finding = check_all_ports_open(r)
    assert finding is not None
    assert finding.severity == Severity.CRITICAL


def test_specific_port_no_fire():
    r = make_resource(inbound_rules=[make_rule(443)])
    assert check_all_ports_open(r) is None


def test_http_only_fires():
    r = make_resource(inbound_rules=[make_rule(80)])
    finding = check_http_without_https(r)
    assert finding is not None
    assert finding.severity == Severity.HIGH


def test_http_and_https_no_fire():
    r = make_resource(inbound_rules=[make_rule(80), make_rule(443)])
    assert check_http_without_https(r) is None


def test_https_only_no_fire():
    r = make_resource(inbound_rules=[make_rule(443)])
    assert check_http_without_https(r) is None


def test_iam_wildcard_fires():
    r = make_resource(
        resource_type="aws_iam_role_policy",
        properties={"statement": [{"actions": ["*"], "resources": ["*"]}]},
    )
    finding = check_permissive_iam(r)
    assert finding is not None
    assert finding.severity == Severity.HIGH


def test_iam_specific_no_fire():
    r = make_resource(
        resource_type="aws_iam_role_policy",
        properties={"statement": [{"actions": ["s3:GetObject"], "resources": ["arn:aws:s3:::my-bucket/*"]}]},
    )
    assert check_permissive_iam(r) is None


def test_non_iam_no_fire():
    r = make_resource(resource_type="aws_security_group")
    assert check_permissive_iam(r) is None


def test_missing_network_policy_fires():
    r = make_resource(resource_type="kubernetes_namespace", properties={"has_network_policy": False})
    finding = check_missing_network_policy(r)
    assert finding is not None
    assert finding.severity == Severity.HIGH


def test_has_network_policy_no_fire():
    r = make_resource(resource_type="kubernetes_namespace", properties={"has_network_policy": True})
    assert check_missing_network_policy(r) is None


def test_privileged_container_fires():
    r = make_resource(
        resource_type="kubernetes_deployment",
        properties={"containers": [{"name": "app", "security_context": {"privileged": True}}]},
    )
    finding = check_privileged_container(r)
    assert finding is not None
    assert finding.severity == Severity.HIGH


def test_non_privileged_no_fire():
    r = make_resource(
        resource_type="kubernetes_deployment",
        properties={"containers": [{"name": "app", "security_context": {"privileged": False}}]},
    )
    assert check_privileged_container(r) is None


def test_unauthenticated_service_fires():
    r = make_resource(
        resource_type="kubernetes_service",
        properties={"type": "LoadBalancer", "auth_type": "NONE"},
    )
    finding = check_unauthenticated_service(r)
    assert finding is not None
    assert finding.severity == Severity.MEDIUM


def test_authenticated_service_no_fire():
    r = make_resource(
        resource_type="kubernetes_service",
        properties={"type": "LoadBalancer", "auth_type": "OAuth2"},
    )
    assert check_unauthenticated_service(r) is None


def test_unencrypted_ebs_fires():
    r = make_resource(resource_type="aws_ebs_volume", properties={"encrypted": False})
    finding = check_unencrypted_storage(r)
    assert finding is not None
    assert finding.severity == Severity.MEDIUM


def test_encrypted_ebs_no_fire():
    r = make_resource(
        resource_type="aws_ebs_volume",
        properties={"encrypted": True, "kms_key_id": "arn:aws:kms:us-east-1:123:key/abc"},
    )
    assert check_unencrypted_storage(r) is None


def test_encrypted_ebs_string_true_without_kms_no_fire():
    r = make_resource(resource_type="aws_ebs_volume", properties={"encrypted": "true"})
    assert check_unencrypted_storage(r) is None


def test_missing_tags_fires():
    r = make_resource(tags={})
    finding = check_missing_tags(r)
    assert finding is not None
    assert finding.severity == Severity.LOW


def test_partial_tags_fires():
    r = make_resource(tags={"environment": "prod"})
    finding = check_missing_tags(r)
    assert finding is not None


def test_all_tags_present_no_fire():
    r = make_resource(tags={"environment": "prod", "owner": "mohit", "project": "netguard"})
    assert check_missing_tags(r) is None
