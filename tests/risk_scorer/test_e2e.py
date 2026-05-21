"""
End-to-end tests for POST /score endpoint.
Tests the full pipeline as a black box — sends real HTTP requests
to the FastAPI app and verifies the complete response structure.
"""
from fastapi.testclient import TestClient
from services.risk_scorer.main import app

client = TestClient(app)


# ── Reusable payloads ──────────────────────────────────────────────────────────

CRITICAL_RESOURCE = {
    "resource_id": "aws_security_group.bad",
    "resource_type": "aws_security_group",
    "provider": "aws",
    "properties": {},
    "inbound_rules": [{"port": "22", "protocol": "tcp", "cidr": "0.0.0.0/0"}],
    "outbound_rules": [],
    "tags": {}
}

SAFE_RESOURCE = {
    "resource_id": "aws_security_group.good",
    "resource_type": "aws_security_group",
    "provider": "aws",
    "properties": {},
    "inbound_rules": [{"port": "443", "protocol": "tcp", "cidr": "10.0.0.0/8"}],
    "outbound_rules": [],
    "tags": {"environment": "prod", "owner": "mohit", "project": "netguard"}
}

S3_PUBLIC_RESOURCE = {
    "resource_id": "aws_s3_bucket.data",
    "resource_type": "aws_s3_bucket",
    "provider": "aws",
    "properties": {"acl": "public-read"},
    "inbound_rules": [],
    "outbound_rules": [],
    "tags": {}
}

K8S_PRIVILEGED_RESOURCE = {
    "resource_id": "kubernetes_deployment.app",
    "resource_type": "kubernetes_deployment",
    "provider": "kubernetes",
    "properties": {
        "containers": [{"name": "app", "security_context": {"privileged": True}}]
    },
    "inbound_rules": [],
    "outbound_rules": [],
    "tags": {"environment": "prod", "owner": "mohit", "project": "netguard"}
}


# ── Health check ───────────────────────────────────────────────────────────────

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "risk_scorer"}


def test_source_location_propagates_to_findings():
    resource = {
        **CRITICAL_RESOURCE,
        "source_file": "main.tf",
        "source_line": 42,
    }
    response = client.post("/score", json={"resources": [resource]})
    assert response.status_code == 200
    findings = response.json()["findings"]
    assert findings
    f = findings[0]
    assert f.get("source_file") == "main.tf"
    assert f.get("source_line") == 42


# ── Basic endpoint behaviour ───────────────────────────────────────────────────

def test_empty_resources_returns_400():
    response = client.post("/score", json={"resources": []})
    assert response.status_code == 400


def test_safe_resource_returns_200():
    response = client.post("/score", json={"resources": [SAFE_RESOURCE]})
    assert response.status_code == 200


def test_response_has_required_fields():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    data = response.json()
    assert "findings" in data
    assert "total" in data
    assert "critical_count" in data
    assert "high_count" in data
    assert "medium_count" in data
    assert "low_count" in data


# ── Severity counting ──────────────────────────────────────────────────────────

def test_critical_resource_has_critical_count():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    data = response.json()
    assert data["critical_count"] >= 1


def test_safe_resource_zero_criticals():
    response = client.post("/score", json={"resources": [SAFE_RESOURCE]})
    data = response.json()
    assert data["critical_count"] == 0


def test_total_equals_sum_of_counts():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE, S3_PUBLIC_RESOURCE]})
    data = response.json()
    assert data["total"] == (
        data["critical_count"] +
        data["high_count"] +
        data["medium_count"] +
        data["low_count"]
    )


# ── Finding structure ──────────────────────────────────────────────────────────

def test_finding_has_required_fields():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    findings = response.json()["findings"]
    assert len(findings) >= 1
    f = findings[0]
    assert "resource_id" in f
    assert "resource_type" in f
    assert "finding_type" in f
    assert "severity" in f
    assert "explanation" in f
    assert "remediation" in f
    assert "confidence_score" in f
    assert "is_new" in f


def test_ssh_finding_type_correct():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    findings = response.json()["findings"]
    finding_types = [f["finding_type"] for f in findings]
    assert "SSH_EXPOSED_TO_PUBLIC" in finding_types


def test_severity_values_are_valid():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    findings = response.json()["findings"]
    valid = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}
    for f in findings:
        assert f["severity"] in valid


# ── Multi-resource payload ─────────────────────────────────────────────────────

def test_multi_resource_payload():
    payload = {
        "resources": [
            CRITICAL_RESOURCE,
            S3_PUBLIC_RESOURCE,
            K8S_PRIVILEGED_RESOURCE,
            SAFE_RESOURCE
        ]
    }
    response = client.post("/score", json=payload)
    assert response.status_code == 200
    data = response.json()
    # Should have criticals from SSH + S3
    assert data["critical_count"] >= 2
    # Should have high from privileged container
    assert data["high_count"] >= 1
    assert data["total"] > 0


# ── Graph context ──────────────────────────────────────────────────────────────

def test_graph_context_marks_is_new():
    payload = {
        "resources": [CRITICAL_RESOURCE],
        "graph_context": {
            "nodes": [],
            "edges": [],
            "newly_exposed": ["aws_security_group.bad"],
            "exposure_delta": 1
        }
    }
    response = client.post("/score", json=payload)
    findings = response.json()["findings"]
    # The critical resource is in newly_exposed so is_new should be True
    ssh_finding = next((f for f in findings if f["finding_type"] == "SSH_EXPOSED_TO_PUBLIC"), None)
    assert ssh_finding is not None
    assert ssh_finding["is_new"] is True


def test_no_graph_context_is_new_false():
    response = client.post("/score", json={"resources": [CRITICAL_RESOURCE]})
    findings = response.json()["findings"]
    for f in findings:
        assert f["is_new"] is False
