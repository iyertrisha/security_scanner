from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from services.api.main import app
from services.database.database import Base
import services.api.main as api_main


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


class DummyAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, files=None, json=None):
        if url.endswith("/parse"):
            return DummyResponse(
                {
                    "resources": [
                        {
                            "resource_id": "aws_security_group.sg_web",
                            "resource_type": "aws_security_group",
                            "provider": "aws",
                            "properties": {},
                            "inbound_rules": [{"port": "22", "protocol": "tcp", "cidr": "0.0.0.0/0"}],
                            "outbound_rules": [],
                            "tags": {"environment": "dev"},
                        }
                    ],
                    "module_sources": [],
                }
            )
        if url.endswith("/graph/build"):
            return DummyResponse(
                {
                    "nodes": [{"id": "aws_security_group.sg_web", "blast_radius": {"count": 1, "resources": ["aws_security_group.sg_web"]}}],
                    "edges": [],
                    "metadata": {"node_count": 1, "edge_count": 0},
                }
            )
        if url.endswith("/graph/diff"):
            return DummyResponse(
                {
                    "added_nodes": ["aws_security_group.sg_web"],
                    "removed_nodes": [],
                    "added_edges": [],
                    "removed_edges": [],
                    "modified_nodes": [],
                    "newly_exposed": ["aws_security_group.sg_web"],
                    "no_longer_exposed": [],
                    "exposure_delta": 1,
                }
            )
        if url.endswith("/score"):
            return DummyResponse(
                {
                    "findings": [
                        {
                            "resource_id": "aws_security_group.sg_web",
                            "resource_type": "aws_security_group",
                            "finding_type": "SSH_EXPOSED_TO_PUBLIC",
                            "severity": "CRITICAL",
                            "explanation": "test",
                            "remediation": "test",
                            "confidence_score": 0.9,
                            "is_new": True,
                            "source_file": "main.tf",
                            "source_line": 1,
                        }
                    ]
                }
            )
        return DummyResponse({})


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[api_main.get_db] = override_get_db
# The auth middleware opens its own SessionLocal — point it at the in-memory test DB.
api_main.SessionLocal = TestingSessionLocal


def _signup_and_get_key(client, email="alice@example.com"):
    resp = client.post(
        "/api/auth/signup",
        json={"name": "Alice Corp", "email": email, "password": "supersecret"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["api_key"]


def _auth_headers(api_key):
    return {"X-API-Key": api_key}


def test_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_unauthenticated_requests_rejected():
    client = TestClient(app)
    assert client.get("/api/scans").status_code == 401
    assert client.get("/api/repos").status_code == 401
    assert client.get("/api/me").status_code == 401


def test_signup_login_me_flow():
    client = TestClient(app)
    signup = client.post(
        "/api/auth/signup",
        json={"name": "Acme Co", "email": "owner@acme.test", "password": "supersecret"},
    )
    assert signup.status_code == 200, signup.text
    api_key = signup.json()["api_key"]
    assert api_key.startswith("ng_")
    # Login no longer rotates keys; CI keys remain stable.
    login = client.post(
        "/api/auth/login",
        json={"email": "owner@acme.test", "password": "supersecret"},
    )
    assert login.status_code == 200
    assert login.json()["api_key"] is None

    me = client.get("/api/me", headers=_auth_headers(api_key))
    assert me.status_code == 200
    body = me.json()
    assert body["org_name"] == "Acme Co"
    assert body["user_email"] == "owner@acme.test"
    assert body["api_key"] == api_key
    assert body["api_key_masked"].startswith(api_key[:8])

    settings = client.get("/api/settings", headers=_auth_headers(api_key))
    assert settings.status_code == 200
    assert settings.json()["api_key"] == api_key
    assert settings.json()["api_key_masked"].startswith(api_key[:8])


def test_regenerate_key_explicitly_rotates():
    client = TestClient(app)
    old_key = _signup_and_get_key(client, email="rotate@example.com")
    headers = _auth_headers(old_key)

    rotated = client.post("/api/auth/regenerate-key", headers=headers)
    assert rotated.status_code == 200
    new_key = rotated.json()["api_key"]
    assert new_key.startswith("ng_")
    assert new_key != old_key

    assert client.get("/api/me", headers=_auth_headers(old_key)).status_code == 401
    assert client.get("/api/me", headers=_auth_headers(new_key)).status_code == 200


def test_scan_and_read_endpoints(monkeypatch):
    monkeypatch.setattr(api_main.httpx, "AsyncClient", lambda timeout=60.0: DummyAsyncClient())

    client = TestClient(app)
    api_key = _signup_and_get_key(client, email="scan-tester@example.com")
    headers = _auth_headers(api_key)
    payload = {
        "repository": "repo-a",
        "repository_url": "https://github.com/acme/repo-a",
        "pr_number": 1,
        "commit_sha": "abcd1234",
        "files": [{"filename": "main.tf", "content": "resource \"aws_security_group\" \"sg_web\" {}"}],
    }
    scan_response = client.post("/api/scan", json=payload, headers=headers)
    assert scan_response.status_code == 200, scan_response.text
    scan_id = scan_response.json()["scan_id"]

    scans_response = client.get("/api/scans", headers=headers)
    assert scans_response.status_code == 200
    assert scans_response.json()["total"] >= 1

    detail_response = client.get(f"/api/scans/{scan_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_json = detail_response.json()
    assert len(detail_json["findings"]) >= 1
    assert detail_json["status"] == "completed"
    assert detail_json["summary"]["total"] >= 1
    assert "blocking" in detail_json
    row = detail_json["findings"][0]
    assert row.get("github_url") == (
        "https://github.com/acme/repo-a/blob/abcd1234/main.tf#L1"
    )
    assert row.get("source_file") == "main.tf"
    assert row.get("source_line") == 1

    graph_response = client.get(f"/api/scans/{scan_id}/graph", headers=headers)
    assert graph_response.status_code == 200

    diff_response = client.get(f"/api/scans/{scan_id}/diff", headers=headers)
    assert diff_response.status_code == 200

    repos_response = client.get("/api/repos", headers=headers)
    assert repos_response.status_code == 200
    assert len(repos_response.json()["items"]) >= 1

    stats_response = client.get("/api/stats", headers=headers)
    assert stats_response.status_code == 200
    assert "compliance_posture" in stats_response.json()


def test_scan_async_wait_false(monkeypatch):
    monkeypatch.setattr(api_main.httpx, "AsyncClient", lambda timeout=60.0: DummyAsyncClient())

    client = TestClient(app)
    api_key = _signup_and_get_key(client, email="async-scan@example.com")
    headers = _auth_headers(api_key)
    payload = {
        "repository": "async-repo",
        "repository_url": "https://github.com/acme/async-repo",
        "pr_number": 2,
        "commit_sha": "async1234",
        "files": [{"filename": "main.tf", "content": "resource \"aws_security_group\" \"sg_web\" {}"}],
    }
    scan_response = client.post("/api/scan?wait=false", json=payload, headers=headers)
    assert scan_response.status_code == 202, scan_response.text
    body = scan_response.json()
    assert body["status"] == "running"
    scan_id = body["scan_id"]

    detail_response = client.get(f"/api/scans/{scan_id}", headers=headers)
    assert detail_response.status_code == 200
    detail_json = detail_response.json()
    assert detail_json["status"] == "completed"
    assert detail_json["summary"]["critical"] >= 1
    assert detail_json["blocking"] is True


def test_ci_hmac_bypass_uses_api_key_in_body(monkeypatch):
    monkeypatch.setattr(api_main.httpx, "AsyncClient", lambda timeout=60.0: DummyAsyncClient())
    # Force HMAC verification path with a known secret.
    monkeypatch.setattr(api_main, "NETGUARD_SECRET", "ci-secret-123", raising=False)

    client = TestClient(app)
    api_key = _signup_and_get_key(client, email="ci-bot@example.com")

    import hashlib as _hashlib
    import hmac as _hmac
    import json as _json

    body = {
        "repository": "ci-repo",
        "repository_url": "https://github.com/acme/ci-repo",
        "pr_number": 11,
        "commit_sha": "ci0001",
        "files": [{"filename": "main.tf", "content": "resource \"aws_security_group\" \"sg_web\" {}"}],
        "api_key": api_key,
    }
    body_bytes = _json.dumps(body).encode("utf-8")
    sig = _hmac.new(b"ci-secret-123", body_bytes, _hashlib.sha256).hexdigest()

    res = client.post(
        "/api/scan",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-NetGuard-Signature": f"sha256={sig}",
        },
    )
    assert res.status_code == 200, res.text


def test_other_org_cannot_see_first_orgs_scans(monkeypatch):
    monkeypatch.setattr(api_main.httpx, "AsyncClient", lambda timeout=60.0: DummyAsyncClient())
    client = TestClient(app)

    alice_key = _signup_and_get_key(client, email="alice-isolated@example.com")
    bob_key = _signup_and_get_key(client, email="bob-isolated@example.com")

    payload = {
        "repository": "alice-only-repo",
        "repository_url": "https://github.com/alice/alice-only-repo",
        "pr_number": 7,
        "commit_sha": "deadbeef",
        "files": [{"filename": "main.tf", "content": "resource \"aws_security_group\" \"sg_web\" {}"}],
    }
    res = client.post("/api/scan", json=payload, headers=_auth_headers(alice_key))
    assert res.status_code == 200
    alice_scan_id = res.json()["scan_id"]

    bob_scans = client.get("/api/scans", headers=_auth_headers(bob_key))
    assert bob_scans.status_code == 200
    bob_ids = {item["id"] for item in bob_scans.json()["items"]}
    assert alice_scan_id not in bob_ids

    # Bob is denied direct access to Alice's scan.
    assert client.get(f"/api/scans/{alice_scan_id}", headers=_auth_headers(bob_key)).status_code == 404


def test_override_and_evaluation_endpoints(monkeypatch):
    monkeypatch.setattr(api_main.httpx, "AsyncClient", lambda timeout=60.0: DummyAsyncClient())
    client = TestClient(app)
    api_key = _signup_and_get_key(client, email="ovr-tester@example.com")
    headers = _auth_headers(api_key)

    payload = {
        "repository": "ovr-repo",
        "repository_url": "https://github.com/acme/ovr",
        "pr_number": 9,
        "commit_sha": "deadbeef",
        "files": [{"filename": "main.tf", "content": "resource \"aws_security_group\" \"sg_web\" {}"}],
    }
    res = client.post("/api/scan", json=payload, headers=headers)
    assert res.status_code == 200
    scan_id = res.json()["scan_id"]

    override = client.post(
        "/api/overrides",
        json={
            "finding_type": "SSH_EXPOSED_TO_PUBLIC",
            "resource_pattern": "*",
            "justification": "accepted risk",
            "created_by": "tester",
        },
        headers=headers,
    )
    assert override.status_code == 200
    override_id = override.json()["id"]

    list_overrides = client.get("/api/overrides", headers=headers)
    assert list_overrides.status_code == 200
    assert len(list_overrides.json()["items"]) >= 1

    delete_override = client.delete(f"/api/overrides/{override_id}", headers=headers)
    assert delete_override.status_code == 200

    evaluation = client.post(
        "/api/evaluations",
        json={
            "scan_id": scan_id,
            "accuracy": 4.1,
            "specificity": 3.9,
            "blast_radius_correctness": 4.0,
            "actionability": 4.2,
            "calibration": 3.8,
        },
        headers=headers,
    )
    assert evaluation.status_code == 200

    evaluations = client.get("/api/evaluations", headers=headers)
    assert evaluations.status_code == 200

    summary = client.get("/api/evaluations/summary", headers=headers)
    assert summary.status_code == 200
    assert "mean_accuracy" in summary.json()
