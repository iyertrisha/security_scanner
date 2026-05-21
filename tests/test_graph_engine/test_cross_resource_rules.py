"""
Tests for cross-resource security rules (Phase 3).
"""

import pytest
from services.risk_scorer.schemas import Resource, Rule, GraphContext, Severity
from services.risk_scorer.rules.cross_resource_rules import (
    check_privileged_ec2_to_sensitive_db,
    check_public_eni_chain_to_database,
    check_overpermissive_sg_chain,
    check_cross_az_replication_exposure,
    check_lateral_movement_via_shared_sg,
    run_cross_resource_rules,
)


@pytest.fixture
def graph_context_simple():
    """
    Simple graph:
    ec2-1 → rds-1 → backup-1
    """
    return GraphContext(
        nodes=[
            {"id": "ec2-1", "type": "aws_ec2_instance", "provider": "aws"},
            {"id": "rds-1", "type": "aws_rds_instance", "provider": "aws"},
            {"id": "backup-1", "type": "aws_backup", "provider": "aws"},
        ],
        edges=[
            {"source": "ec2-1", "target": "rds-1", "relationship": "accesses"},
            {"source": "rds-1", "target": "backup-1", "relationship": "backs_up"},
        ],
        newly_exposed=[],
        exposure_delta=0,
    )


@pytest.fixture
def graph_context_with_internet():
    """
    Graph with internet exposure:
    internet → sg-1 → ec2-1 → rds-1
    """
    return GraphContext(
        nodes=[
            {"id": "internet", "type": "internet", "provider": "global"},
            {"id": "sg-1", "type": "aws_security_group", "provider": "aws"},
            {"id": "ec2-1", "type": "aws_ec2_instance", "provider": "aws"},
            {"id": "rds-1", "type": "aws_rds_instance", "provider": "aws"},
        ],
        edges=[
            {"source": "internet", "target": "sg-1", "relationship": "exposes"},
            {"source": "sg-1", "target": "ec2-1", "relationship": "protects"},
            {"source": "ec2-1", "target": "rds-1", "relationship": "accesses"},
        ],
        newly_exposed=["sg-1"],
        exposure_delta=1,
    )


@pytest.fixture
def admin_ec2():
    """EC2 with admin IAM role."""
    return Resource(
        resource_id="ec2-1",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "admin-role",
            "security_groups": ["sg-1"],
        },
        tags={"name": "admin-ec2"},
    )


@pytest.fixture
def sensitive_rds():
    """RDS with sensitive data."""
    return Resource(
        resource_id="rds-1",
        resource_type="aws_rds_instance",
        provider="aws",
        properties={
            "engine": "postgres",
            "publicly_accessible": False,
        },
        tags={"data-classification": "PII", "pii_data": "credit_cards"},
    )


@pytest.fixture
def overpermissive_sg():
    """Security group allowing all ports from internet."""
    return Resource(
        resource_id="sg-1",
        resource_type="aws_security_group",
        provider="aws",
        properties={
            "description": "Allow all inbound",
            "security_groups": ["sg-1"],
        },
        inbound_rules=[
            Rule(port="0", protocol="all", cidr="0.0.0.0/0"),  # All ports
        ],
    )


class TestPrivilegedEC2ToSensitiveDB:
    """Tests for C1 rule."""

    def test_admin_ec2_reaching_sensitive_db(self, admin_ec2, sensitive_rds, graph_context_simple):
        """Should flag when admin EC2 can reach sensitive database."""
        findings = check_privileged_ec2_to_sensitive_db(admin_ec2, graph_context_simple, [admin_ec2, sensitive_rds])
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.CRITICAL
        assert "PRIVILEGED_EC2_TO_SENSITIVE_DB" in findings[0].finding_type

    def test_non_admin_ec2_no_finding(self):
        """Non-admin EC2 should not trigger this rule."""
        ec2 = Resource(
            resource_id="ec2-2",
            resource_type="aws_ec2_instance",
            provider="aws",
            properties={"security_groups": ["sg-1"]},
        )
        findings = check_privileged_ec2_to_sensitive_db(ec2, None, [ec2])
        assert len(findings) == 0

    def test_no_graph_context(self, admin_ec2):
        """With no graph context, should return no findings."""
        findings = check_privileged_ec2_to_sensitive_db(admin_ec2, None, [admin_ec2])
        assert len(findings) == 0

    def test_non_ec2_resource(self):
        """Only EC2 instances should be checked."""
        rds = Resource(
            resource_id="rds-1",
            resource_type="aws_rds_instance",
            provider="aws",
        )
        findings = check_privileged_ec2_to_sensitive_db(rds, None, [rds])
        assert len(findings) == 0


class TestPublicENIChainToDatabase:
    """Tests for C2 rule."""

    def test_internet_exposed_to_db_chain(self, graph_context_with_internet):
        """Should flag internet-exposed resource that chains to database."""
        sg = Resource(
            resource_id="sg-1",
            resource_type="aws_security_group",
            provider="aws",
        )
        rds = Resource(
            resource_id="rds-1",
            resource_type="aws_rds_instance",
            provider="aws",
        )
        
        findings = check_public_eni_chain_to_database(sg, graph_context_with_internet, [sg, rds])
        
        # Should detect the chain attack path
        assert any("PUBLIC_CHAIN_TO_DATABASE" in f.finding_type for f in findings)

    def test_private_resource_no_finding(self, graph_context_simple):
        """Private (non-exposed) resources should not trigger."""
        ec2 = Resource(
            resource_id="ec2-1",
            resource_type="aws_ec2_instance",
            provider="aws",
        )
        findings = check_public_eni_chain_to_database(ec2, graph_context_simple, [ec2])
        assert len(findings) == 0


class TestOverpermissiveSGChain:
    """Tests for C3 rule."""

    def test_sg_allows_all_ports_to_sensitive(self, overpermissive_sg, sensitive_rds):
        """Should flag overpermissive SG that protects resources reaching sensitive data."""
        ec2 = Resource(
            resource_id="ec2-1",
            resource_type="aws_ec2_instance",
            provider="aws",
            properties={"security_groups": ["sg-1"]},
        )
        
        graph = GraphContext(
            nodes=[
                {"id": "sg-1", "type": "aws_security_group"},
                {"id": "ec2-1", "type": "aws_ec2_instance"},
                {"id": "rds-1", "type": "aws_rds_instance"},
            ],
            edges=[
                {"source": "sg-1", "target": "ec2-1", "relationship": "protects"},
                {"source": "ec2-1", "target": "rds-1", "relationship": "accesses"},
            ],
        )
        
        findings = check_overpermissive_sg_chain(overpermissive_sg, graph, [overpermissive_sg, ec2, sensitive_rds])
        
        assert any("OVERPERMISSIVE_SG_CHAIN" in f.finding_type for f in findings)

    def test_restrictive_sg_no_finding(self):
        """Restrictive security group should not trigger."""
        sg = Resource(
            resource_id="sg-1",
            resource_type="aws_security_group",
            provider="aws",
            inbound_rules=[
                Rule(port="443", protocol="tcp", cidr="10.0.0.0/8"),  # Restricted
            ],
        )
        findings = check_overpermissive_sg_chain(sg, None, [sg])
        assert len(findings) == 0


class TestCrossAZReplicationExposure:
    """Tests for C4 rule."""

    def test_exposed_rds_replica_with_replication_link(self):
        """Should flag exposed RDS replica with replication link to primary."""
        replica = Resource(
            resource_id="rds-replica",
            resource_type="aws_rds_instance",
            provider="aws",
            properties={
                "replicate_source_db": "rds-primary",
                "replication_target_db": ["rds-primary"],
            },
        )
        
        graph = GraphContext(
            nodes=[
                {"id": "rds-replica", "type": "aws_rds_instance"},
                {"id": "rds-primary", "type": "aws_rds_instance"},
            ],
            edges=[
                {"source": "rds-replica", "target": "rds-primary", "relationship": "replicates_to"},
            ],
            newly_exposed=["rds-replica"],
        )
        
        findings = check_cross_az_replication_exposure(replica, graph, [replica])
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.CRITICAL
        assert "CROSS_AZ_REPLICATION_EXPOSURE" in findings[0].finding_type

    def test_non_replica_no_finding(self):
        """Non-replica RDS should not trigger."""
        primary = Resource(
            resource_id="rds-primary",
            resource_type="aws_rds_instance",
            provider="aws",
            properties={},
        )
        findings = check_cross_az_replication_exposure(primary, None, [primary])
        assert len(findings) == 0


class TestLateralMovementViaSG:
    """Tests for C5 rule."""

    def test_multiple_ec2s_in_same_sg_with_sensitive_target(self):
        """Should flag when multiple EC2s in same SG with one containing sensitive data."""
        ec2_1 = Resource(
            resource_id="ec2-1",
            resource_type="aws_ec2_instance",
            provider="aws",
            properties={"security_groups": ["sg-1"]},
        )
        
        ec2_2 = Resource(
            resource_id="ec2-2",
            resource_type="aws_ec2_instance",
            provider="aws",
            properties={"security_groups": ["sg-1"]},
            tags={"data_type": "PII"},  # Sensitive data
        )
        
        findings = check_lateral_movement_via_shared_sg(ec2_1, None, [ec2_1, ec2_2])
        
        assert len(findings) > 0
        assert findings[0].severity == Severity.HIGH
        assert "LATERAL_MOVEMENT_VIA_SG" in findings[0].finding_type

    def test_single_ec2_no_finding(self):
        """Single EC2 in group should not trigger."""
        ec2 = Resource(
            resource_id="ec2-1",
            resource_type="aws_ec2_instance",
            provider="aws",
            properties={"security_groups": ["sg-1"]},
        )
        
        findings = check_lateral_movement_via_shared_sg(ec2, None, [ec2])
        assert len(findings) == 0


class TestRunCrossResourceRules:
    """Integration tests for orchestrator."""

    def test_runs_all_applicable_rules(self, admin_ec2):
        """Orchestrator should run all rule functions."""
        findings = run_cross_resource_rules(admin_ec2, None, [admin_ec2])
        
        # All rules should complete without error
        assert isinstance(findings, list)

    def test_handles_missing_resources_gracefully(self):
        """Should handle missing resources without crashing."""
        ec2 = Resource(
            resource_id="ec2-1",
            resource_type="aws_ec2_instance",
            provider="aws",
        )
        
        findings = run_cross_resource_rules(ec2, None, [])
        
        # Should not crash and return list
        assert isinstance(findings, list)
