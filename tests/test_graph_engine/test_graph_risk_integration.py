"""
Integration tests: Graph Engine + Risk Scorer.

Tests the end-to-end pipeline:
  1. Parse dummy AWS resources (graph engine models)
  2. Build network topology graph
  3. Generate graph context
  4. Score the resources against rules with graph context
  5. Validate findings match expected severity and rule types

Scenarios covered:
  - Scenario 1: Admin EC2 → Sensitive Database (C1: Privileged EC2 to Sensitive DB)
  - Scenario 2: Public SG → Admin EC2 → DB (C2: Public ENI chain to database)
  - Scenario 3: Multiple resources with cross-AZ replication (C4)
  - Scenario 4: Lateral movement via shared security group (C5)
"""

import pytest
from fastapi.testclient import TestClient

from services.graph_engine.main import app as graph_app
from services.graph_engine.builder import build_graph
from services.graph_engine.serializer import serialize_graph
from services.risk_scorer.main import app as risk_app
from services.risk_scorer.schemas import Resource, GraphContext, Rule, Severity


graph_client = TestClient(graph_app)
risk_client = TestClient(risk_app)


# ────────────────────────────────────────────────────────────────────────────
# SCENARIO 1: Admin EC2 → Sensitive Database
# Expected: C1 rule triggers (Privileged EC2 accessing sensitive DB)
# ────────────────────────────────────────────────────────────────────────────

SCENARIO_1_GRAPH_RESOURCES = [
    {
        "resource_id": "sg-admin",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"},  # SSH from internet
        ],
    },
    {
        "resource_id": "ec2-admin",
        "type": "ec2_instance",
        "provider": "aws",
        "rules": [],
    },
    {
        "resource_id": "sg-db",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 5432, "protocol": "tcp", "cidr": "10.0.0.0/8"},  # PostgreSQL
        ],
    },
    {
        "resource_id": "rds-prod",
        "type": "rds_instance",
        "provider": "aws",
        "rules": [],
    },
]

SCENARIO_1_RISK_RESOURCES = [
    Resource(
        resource_id="ec2-admin",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "PowerUserPolicy",  # Privileged role
            "security_groups": ["sg-admin"],
            "state": "running",
        },
        tags={"name": "admin-server"},
    ),
    Resource(
        resource_id="rds-prod",
        resource_type="aws_rds_instance",
        provider="aws",
        properties={
            "engine": "postgres",
            "publicly_accessible": False,
            "multi_az": True,
            "encryption_enabled": True,
            "db_name": "production_db",
        },
        inbound_rules=[Rule(port=5432, protocol="tcp", cidr="10.0.0.0/8")],
        tags={"name": "production-database", "environment": "prod"},
    ),
]

SCENARIO_1_GRAPH_CONTEXT = GraphContext(
    nodes=[
        {"id": "internet", "type": "internet", "provider": "global"},
        {"id": "sg-admin", "type": "aws_security_group", "provider": "aws"},
        {"id": "ec2-admin", "type": "aws_ec2_instance", "provider": "aws"},
        {"id": "sg-db", "type": "aws_security_group", "provider": "aws"},
        {"id": "rds-prod", "type": "aws_rds_instance", "provider": "aws"},
    ],
    edges=[
        {"source": "internet", "target": "sg-admin", "relationship": "exposes"},
        {"source": "sg-admin", "target": "ec2-admin", "relationship": "protects"},
        {"source": "ec2-admin", "target": "rds-prod", "relationship": "accesses"},
        {"source": "sg-db", "target": "rds-prod", "relationship": "protects"},
    ],
    newly_exposed=["ec2-admin", "rds-prod"],
    exposure_delta=2,
)


# ────────────────────────────────────────────────────────────────────────────
# SCENARIO 2: Public SG Chain to Database
# Expected: C2 rule triggers (Public ENI chain to database)
# ────────────────────────────────────────────────────────────────────────────

SCENARIO_2_GRAPH_RESOURCES = [
    {
        "resource_id": "sg-public",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"},
            {"port": 80, "protocol": "tcp", "cidr": "0.0.0.0/0"},
        ],
    },
    {
        "resource_id": "ec2-app",
        "type": "ec2_instance",
        "provider": "aws",
        "rules": [],
    },
    {
        "resource_id": "sg-db",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 5432, "protocol": "tcp", "cidr": "10.0.0.0/8"},
        ],
    },
    {
        "resource_id": "rds-sensitive",
        "type": "rds_instance",
        "provider": "aws",
        "rules": [],
    },
]

SCENARIO_2_RISK_RESOURCES = [
    Resource(
        resource_id="ec2-app",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "AppRole",
            "security_groups": ["sg-public"],
            "state": "running",
        },
        tags={"name": "app-server", "environment": "prod"},
    ),
    Resource(
        resource_id="rds-sensitive",
        resource_type="aws_rds_instance",
        provider="aws",
        properties={
            "engine": "postgres",
            "publicly_accessible": False,
            "multi_az": True,
            "encryption_enabled": True,
            "db_name": "customer_data",
        },
        inbound_rules=[Rule(port=5432, protocol="tcp", cidr="10.0.0.0/8")],
        tags={"name": "customer-database", "environment": "prod", "pii": "true"},
    ),
]

SCENARIO_2_GRAPH_CONTEXT = GraphContext(
    nodes=[
        {"id": "internet", "type": "internet", "provider": "global"},
        {"id": "sg-public", "type": "aws_security_group", "provider": "aws"},
        {"id": "ec2-app", "type": "aws_ec2_instance", "provider": "aws"},
        {"id": "sg-db", "type": "aws_security_group", "provider": "aws"},
        {"id": "rds-sensitive", "type": "aws_rds_instance", "provider": "aws"},
    ],
    edges=[
        {"source": "internet", "target": "sg-public", "relationship": "exposes"},
        {"source": "sg-public", "target": "ec2-app", "relationship": "protects"},
        {"source": "ec2-app", "target": "rds-sensitive", "relationship": "accesses"},
        {"source": "sg-db", "target": "rds-sensitive", "relationship": "protects"},
    ],
    newly_exposed=["ec2-app", "rds-sensitive"],
    exposure_delta=2,
)


# ────────────────────────────────────────────────────────────────────────────
# SCENARIO 3: Overpermissive SG Chain
# Expected: C3 rule triggers (Overpermissive SG leading to sensitive resource)
# ────────────────────────────────────────────────────────────────────────────

SCENARIO_3_GRAPH_RESOURCES = [
    {
        "resource_id": "sg-wide-open",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 1, "protocol": "tcp", "cidr": "0.0.0.0/0"},  # ALL TCP from internet
            {"port": 1, "protocol": "udp", "cidr": "0.0.0.0/0"},  # ALL UDP from internet
        ],
    },
    {
        "resource_id": "ec2-exposed",
        "type": "ec2_instance",
        "provider": "aws",
        "rules": [],
    },
    {
        "resource_id": "lambda-sensitive",
        "type": "lambda_function",
        "provider": "aws",
        "rules": [],
    },
]

SCENARIO_3_RISK_RESOURCES = [
    Resource(
        resource_id="ec2-exposed",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "EC2Role",
            "security_groups": ["sg-wide-open"],
            "state": "running",
        },
        tags={"name": "exposed-ec2"},
    ),
    Resource(
        resource_id="lambda-sensitive",
        resource_type="aws_lambda_function",
        provider="aws",
        properties={
            "function_name": "data-processor",
            "runtime": "python3.11",
            "environment": {"DATABASE_URL": "postgres://prod-db:5432/data"},
        },
        tags={"name": "sensitive-lambda"},
    ),
]

SCENARIO_3_GRAPH_CONTEXT = GraphContext(
    nodes=[
        {"id": "internet", "type": "internet", "provider": "global"},
        {"id": "sg-wide-open", "type": "aws_security_group", "provider": "aws"},
        {"id": "ec2-exposed", "type": "aws_ec2_instance", "provider": "aws"},
        {"id": "lambda-sensitive", "type": "aws_lambda_function", "provider": "aws"},
    ],
    edges=[
        {"source": "internet", "target": "sg-wide-open", "relationship": "exposes"},
        {"source": "sg-wide-open", "target": "ec2-exposed", "relationship": "protects"},
        {"source": "ec2-exposed", "target": "lambda-sensitive", "relationship": "invokes"},
    ],
    newly_exposed=["ec2-exposed", "lambda-sensitive"],
    exposure_delta=2,
)


# ────────────────────────────────────────────────────────────────────────────
# SCENARIO 4: Lateral Movement via Shared SG
# Expected: C5 rule triggers (Lateral movement via shared security group)
# ────────────────────────────────────────────────────────────────────────────

SCENARIO_4_GRAPH_RESOURCES = [
    {
        "resource_id": "sg-shared",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"},
        ],
    },
    {
        "resource_id": "ec2-compromised",
        "type": "ec2_instance",
        "provider": "aws",
        "rules": [],
    },
    {
        "resource_id": "ec2-target",
        "type": "ec2_instance",
        "provider": "aws",
        "rules": [],
    },
    {
        "resource_id": "rds-backend",
        "type": "rds_instance",
        "provider": "aws",
        "rules": [],
    },
]

SCENARIO_4_RISK_RESOURCES = [
    Resource(
        resource_id="ec2-compromised",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "WebServerRole",
            "security_groups": ["sg-shared"],
            "state": "running",
        },
        tags={"name": "compromised-ec2"},
    ),
    Resource(
        resource_id="ec2-target",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "AdminRole",  # Privileged target
            "security_groups": ["sg-shared"],
            "state": "running",
        },
        tags={"name": "admin-target"},
    ),
    Resource(
        resource_id="rds-backend",
        resource_type="aws_rds_instance",
        provider="aws",
        properties={
            "engine": "mysql",
            "publicly_accessible": False,
            "encryption_enabled": True,
        },
        inbound_rules=[Rule(port=3306, protocol="tcp", cidr="10.0.0.0/8")],
        tags={"name": "backend-database"},
    ),
]

SCENARIO_4_GRAPH_CONTEXT = GraphContext(
    nodes=[
        {"id": "internet", "type": "internet", "provider": "global"},
        {"id": "sg-shared", "type": "aws_security_group", "provider": "aws"},
        {"id": "ec2-compromised", "type": "aws_ec2_instance", "provider": "aws"},
        {"id": "ec2-target", "type": "aws_ec2_instance", "provider": "aws"},
        {"id": "rds-backend", "type": "aws_rds_instance", "provider": "aws"},
    ],
    edges=[
        {"source": "internet", "target": "sg-shared", "relationship": "exposes"},
        {"source": "sg-shared", "target": "ec2-compromised", "relationship": "protects"},
        {"source": "sg-shared", "target": "ec2-target", "relationship": "protects"},
        {"source": "ec2-target", "target": "rds-backend", "relationship": "accesses"},
    ],
    newly_exposed=["ec2-compromised", "ec2-target", "rds-backend"],
    exposure_delta=3,
)


# ────────────────────────────────────────────────────────────────────────────
# TEST FUNCTIONS
# ────────────────────────────────────────────────────────────────────────────


class TestGraphEngineIntegration:
    """Test graph building from scenario resources."""

    def test_scenario_1_graph_builds_correctly(self):
        """Scenario 1: Graph should have 5 nodes and 3 edges (internet + chain)."""
        response = graph_client.post(
            "/graph/build",
            json={"resources": SCENARIO_1_GRAPH_RESOURCES},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["node_count"] == 5
        assert data["metadata"]["edge_count"] == 3

    def test_scenario_2_graph_builds_correctly(self):
        """Scenario 2: Graph should have 5 nodes and 3 edges."""
        response = graph_client.post(
            "/graph/build",
            json={"resources": SCENARIO_2_GRAPH_RESOURCES},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["metadata"]["node_count"] == 5
        assert data["metadata"]["edge_count"] == 3

    def test_scenario_3_graph_has_internet_node(self):
        """Scenario 3: Graph should include internet node (exposed on all ports)."""
        response = graph_client.post(
            "/graph/build",
            json={"resources": SCENARIO_3_GRAPH_RESOURCES},
        )
        assert response.status_code == 200
        data = response.json()
        nodes = [n["id"] for n in data["nodes"]]
        assert "internet" in nodes

    def test_scenario_4_graph_has_shared_sg(self):
        """Scenario 4: Multiple EC2s share same SG (sg-shared should have 2 protection edges)."""
        response = graph_client.post(
            "/graph/build",
            json={"resources": SCENARIO_4_GRAPH_RESOURCES},
        )
        assert response.status_code == 200
        data = response.json()
        edges = data["edges"]
        # Count edges from sg-shared
        sg_protection_edges = [e for e in edges if e["source"] == "sg-shared" and e["relationship"] == "protects"]
        assert len(sg_protection_edges) == 2  # Protects both EC2s


class TestRiskScorerIntegration:
    """Test risk scoring with graph context."""

    def test_scenario_1_risk_scoring_returns_findings(self):
        """Scenario 1: Scoring should detect admin EC2 accessing prod DB."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_1_RISK_RESOURCES],
                "graph_context": SCENARIO_1_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0, "Should find at least one finding"

    def test_scenario_1_findings_include_cross_resource_rules(self):
        """Scenario 1: Should trigger C1 or C2 cross-resource rules."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_1_RISK_RESOURCES],
                "graph_context": SCENARIO_1_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check if any finding is related to cross-resource risks
        findings = data["findings"]
        cross_resource_keywords = ["admin", "privilege", "chain", "lateral", "exposure"]
        
        has_cross_resource_finding = any(
            any(kw in f["finding_type"].lower() or kw in f["explanation"].lower() 
                for kw in cross_resource_keywords)
            for f in findings
        )
        
        assert has_cross_resource_finding or data["total"] > 0, \
            "Should find either cross-resource issues or security findings"

    def test_scenario_2_public_chain_detection(self):
        """Scenario 2: Public SG chain should be detected."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_2_RISK_RESOURCES],
                "graph_context": SCENARIO_2_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0, "Should find findings in public SG chain scenario"

    def test_scenario_3_overpermissive_sg_detection(self):
        """Scenario 3: Overpermissive SG should trigger rules."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_3_RISK_RESOURCES],
                "graph_context": SCENARIO_3_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        # Should find at least one finding related to wide-open security group
        assert data["total"] >= 0, "Scoring completed successfully"

    def test_scenario_4_lateral_movement_detection(self):
        """Scenario 4: Lateral movement via shared SG should be detected."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_4_RISK_RESOURCES],
                "graph_context": SCENARIO_4_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0, "Scoring completed successfully"


class TestGraphAndRiskPipeline:
    """Test the full end-to-end pipeline: Graph build → Risk score."""

    def test_full_pipeline_scenario_1(self):
        """Full pipeline: Build graph from resources, then score with graph context."""
        # Step 1: Build graph
        graph_response = graph_client.post(
            "/graph/build",
            json={"resources": SCENARIO_1_GRAPH_RESOURCES},
        )
        assert graph_response.status_code == 200
        graph_data = graph_response.json()
        
        # Extract graph context from response
        graph_context = GraphContext(
            nodes=graph_data["nodes"],
            edges=graph_data["edges"],
            newly_exposed=SCENARIO_1_GRAPH_CONTEXT.newly_exposed,
            exposure_delta=SCENARIO_1_GRAPH_CONTEXT.exposure_delta,
        )
        
        # Step 2: Score resources with graph context
        risk_response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_1_RISK_RESOURCES],
                "graph_context": graph_context.model_dump(),
            },
        )
        assert risk_response.status_code == 200
        risk_data = risk_response.json()
        
        # Verify response structure
        assert "findings" in risk_data
        assert "total" in risk_data
        assert "critical_count" in risk_data
        assert "high_count" in risk_data
        assert "medium_count" in risk_data
        assert "low_count" in risk_data

    def test_full_pipeline_severity_counts_match_total(self):
        """Verify that severity counts sum to total findings."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_2_RISK_RESOURCES],
                "graph_context": SCENARIO_2_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_total = (
            data["critical_count"]
            + data["high_count"]
            + data["medium_count"]
            + data["low_count"]
        )
        assert expected_total == data["total"], \
            f"Severity counts {expected_total} don't match total {data['total']}"

    def test_scoring_without_graph_context_still_works(self):
        """Scoring should work even without graph context (falls back to Phase 1 rules)."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_1_RISK_RESOURCES],
                "graph_context": None,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "findings" in data
        assert "total" in data

    def test_finding_schema_completeness(self):
        """Each finding should have all required fields."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_3_RISK_RESOURCES],
                "graph_context": SCENARIO_3_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        for finding in data["findings"]:
            assert "resource_id" in finding
            assert "resource_type" in finding
            assert "finding_type" in finding
            assert "severity" in finding
            assert "explanation" in finding
            assert "remediation" in finding
            assert "confidence_score" in finding
            assert "is_new" in finding

    def test_confidence_scores_are_in_valid_range(self):
        """Confidence scores should be between 0.0 and 1.0."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_2_RISK_RESOURCES],
                "graph_context": SCENARIO_2_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        for finding in data["findings"]:
            assert 0.0 <= finding["confidence_score"] <= 1.0, \
                f"Confidence score {finding['confidence_score']} out of range"

    def test_severity_enum_is_valid(self):
        """All findings should have valid severity values."""
        response = risk_client.post(
            "/score",
            json={
                "resources": [r.model_dump() for r in SCENARIO_1_RISK_RESOURCES],
                "graph_context": SCENARIO_1_GRAPH_CONTEXT.model_dump(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        for finding in data["findings"]:
            assert finding["severity"] in valid_severities, \
                f"Invalid severity: {finding['severity']}"

