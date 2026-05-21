from fastapi.testclient import TestClient

from services.parser.main import app


client = TestClient(app)


def test_services_parser_exposes_parse_endpoint():
    body = """
    resource "aws_s3_bucket" "demo" {
      bucket = "demo-bucket"
    }
    """
    response = client.post("/parse", files={"file": ("demo.tf", body)})
    assert response.status_code == 200
    payload = response.json()
    assert "resources" in payload
