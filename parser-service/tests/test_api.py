import os
import sys
from fastapi.testclient import TestClient

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.main import app

client = TestClient(app)

def test_parse_endpoint():

    file_content = """
    resource "aws_s3_bucket" "test" {
      bucket = "demo-bucket"
    }
    """

    response = client.post(
        "/parse",
        files={"file": ("test.tf", file_content)}
    )

    assert response.status_code == 200
    payload = response.json()
    assert "resources" in payload
    assert "module_sources" in payload


def test_parse_endpoint_returns_422_for_invalid_terraform():
    invalid_tf = 'resource "aws_s3_bucket" "broken" {\n  bucket = "demo"\n'
    response = client.post(
        "/parse",
        files={"file": ("broken.tf", invalid_tf)}
    )
    assert response.status_code == 422
    payload = response.json()
    assert payload["detail"]["message"] == "Unable to parse IaC file"