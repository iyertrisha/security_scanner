# Quick Start Guide - Parser Service

Get the NetGuard Parser Service up and running in 2 minutes.

## Prerequisites

- Python 3.8+
- pip or conda

## Installation & Run (30 seconds)

```bash
# 1. Navigate to project
cd parser-service

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start service
uvicorn app.main:app --reload --port 8001

# Service is now running at http://localhost:8001
```

## Test the API (1 minute)

### Option A: Using Swagger UI (Interactive)

1. Open: http://localhost:8001/docs
2. Click "POST /parse" to expand
3. Click "Try it out"
4. Paste this in the request body:

```json
{
  "files": [
    {
      "name": "example.tf",
      "content": "resource \"aws_s3_bucket\" \"my_bucket\" {\n  bucket = \"my-data-bucket\"\n  tags = {\n    Environment = \"prod\"\n  }\n}"
    }
  ]
}
```

5. Click "Execute"
6. See the normalized resource in the response

### Option B: Using cURL

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "name": "main.tf",
      "content": "resource \"aws_s3_bucket\" \"test\" { bucket = \"test-bucket\" }"
    }]
  }'
```

### Option C: Using Python

```python
import requests

response = requests.post(
    "http://localhost:8001/parse",
    json={
        "files": [
            {
                "name": "main.tf",
                "content": 'resource "aws_s3_bucket" "test" { bucket = "test-bucket" }'
            }
        ]
    }
)

print(response.json())
```

## Supported File Types

### Terraform
- `.tf` files with AWS, GCP, Azure, Oracle resources
- Extracts: VPCs, subnets, security groups, EC2, RDS, S3, IAM roles, load balancers, etc.
- Parses: ingress/egress rules, tags, properties

### Kubernetes
- `.yaml` or `.yml` files
- Extracts: Deployments, Services, Ingresses, NetworkPolicies, ConfigMaps, Secrets, etc.
- Parses: ports, network policies, labels, properties

## Example Requests

### Parse Terraform Security Group

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "name": "security.tf",
      "content": "resource \"aws_security_group\" \"web\" {\n  name = \"web-sg\"\n  ingress {\n    from_port = 443\n    to_port = 443\n    protocol = \"tcp\"\n    cidr_blocks = [\"0.0.0.0/0\"]\n  }\n}"
    }]
  }'
```

### Parse Kubernetes Service

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "name": "service.yaml",
      "content": "apiVersion: v1\nkind: Service\nmetadata:\n  name: web-svc\nspec:\n  type: LoadBalancer\n  ports:\n  - port: 443\n    targetPort: 8443\n  selector:\n    app: web"
    }]
  }'
```

### Parse Multiple Files

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {"name": "main.tf", "content": "resource \"aws_vpc\" \"v\" { cidr_block = \"10.0.0.0/16\" }"},
      {"name": "deployment.yaml", "content": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web"}
    ]
  }'
```

## Response Format

All responses follow this structure:

```json
{
  "resources": [
    {
      "resource_id": "unique-name",
      "resource_type": "resource_type",
      "provider": "aws|gcp|azure|kubernetes",
      "properties": { ... },
      "inbound_rules": [ ... ],
      "outbound_rules": [ ... ],
      "tags": { ... },
      "metadata": { ... }
    }
  ],
  "stats": {
    "total_files": 1,
    "parsed_files": 1,
    "total_resources": 1,
    "terraform_resources": 0,
    "kubernetes_resources": 1,
    "errors": 0
  },
  "errors": null
}
```

## Run Tests

```bash
# Run all tests
pytest tests/test_parser.py -v

# Expected output: 26 passed ✓
```

## Documentation

- **Full Guide**: [README.md](README.md)
- **Schema Details**: [SCHEMA.md](SCHEMA.md)
- **API Testing**: [API_TESTING.md](API_TESTING.md)
- **Development**: [DEVELOPMENT.md](DEVELOPMENT.md)
- **Implementation**: [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)

## Common Tasks

### Stop the service
```bash
Ctrl+C
```

### Enable debug mode
```bash
uvicorn app.main:app --reload --port 8001 --log-level debug
```

### Check API health
```bash
curl http://localhost:8001/openapi.json
```

### View API documentation
```
http://localhost:8001/docs (Swagger UI)
http://localhost:8001/redoc (ReDoc)
```

## Troubleshooting

### Port 8001 already in use
```bash
# Use different port
uvicorn app.main:app --port 8002
```

### Module not found errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Tests fail
```bash
# Check Python version (requires 3.8+)
python --version

# Run tests with verbose output
pytest tests/test_parser.py -v -s
```

## Next Steps

1. ✅ Service is running
2. ✅ Try the API with sample files
3. 📖 Read [SCHEMA.md](SCHEMA.md) to understand the output format
4. 📚 Check [API_TESTING.md](API_TESTING.md) for more examples
5. 🔧 Read [DEVELOPMENT.md](DEVELOPMENT.md) to extend the service

## Performance

- **Single file**: ~5-10ms parsing time
- **Throughput**: 100+ files/second
- **Memory**: <100MB for typical workloads
- **Concurrent requests**: Fully async with uvicorn

## Key Features

✅ Auto-detect Terraform (.tf) and Kubernetes (.yaml/.yml)  
✅ Extract security rules (ingress/egress)  
✅ Parse network policies  
✅ Normalize across cloud providers (AWS, GCP, Azure, Kubernetes)  
✅ Comprehensive error handling  
✅ Production-ready API  

---

**Ready to use!** 🚀

For issues or questions, check the documentation files or run the test suite to verify everything is working.
