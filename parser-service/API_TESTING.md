# API Testing Guide

Quick reference for testing the Parser Service API

## Starting the Service

```bash
cd parser-service
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Service will be available at: `http://localhost:8001`

## Interactive API Documentation

- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Example Requests

### 1. Parse Terraform S3 Bucket

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "name": "main.tf",
        "content": "resource \"aws_s3_bucket\" \"my_bucket\" {\n  bucket = \"my-data-bucket\"\n  tags = {\n    Environment = \"prod\"\n  }\n}"
      }
    ]
  }'
```

**Response:**
```json
{
  "resources": [
    {
      "resource_id": "my_bucket",
      "resource_type": "aws_s3_bucket",
      "provider": "aws",
      "properties": {
        "bucket": "my-data-bucket",
        "tags": {"Environment": "prod"}
      },
      "inbound_rules": [],
      "outbound_rules": [],
      "tags": {"Environment": "prod"},
      "network_policies": null,
      "metadata": {
        "file_type": "terraform",
        "extracted_from": "aws_s3_bucket"
      }
    }
  ],
  "stats": {
    "total_files": 1,
    "parsed_files": 1,
    "total_resources": 1,
    "terraform_resources": 1,
    "kubernetes_resources": 0,
    "errors": 0
  },
  "errors": null
}
```

### 2. Parse Terraform Security Group

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "name": "security.tf",
        "content": "resource \"aws_security_group\" \"web\" {\n  name = \"web-sg\"\n  \n  ingress {\n    from_port   = 80\n    to_port     = 80\n    protocol    = \"tcp\"\n    cidr_blocks = [\"0.0.0.0/0\"]\n  }\n  \n  ingress {\n    from_port   = 443\n    to_port     = 443\n    protocol    = \"tcp\"\n    cidr_blocks = [\"0.0.0.0/0\"]\n  }\n  \n  egress {\n    from_port   = 0\n    to_port     = 0\n    protocol    = \"-1\"\n    cidr_blocks = [\"0.0.0.0/0\"]\n  }\n}"
      }
    ]
  }'
```

**Response includes inbound and outbound rules:**
```json
{
  "inbound_rules": [
    {
      "port": "80",
      "protocol": "tcp",
      "cidr": "0.0.0.0/0"
    },
    {
      "port": "443",
      "protocol": "tcp",
      "cidr": "0.0.0.0/0"
    }
  ],
  "outbound_rules": [
    {
      "port": "0-0",
      "protocol": "-1",
      "cidr": "0.0.0.0/0"
    }
  ]
}
```

### 3. Parse Kubernetes Deployment

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "name": "deployment.yaml",
        "content": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: nginx\n  namespace: default\nspec:\n  replicas: 3\n  selector:\n    matchLabels:\n      app: nginx\n  template:\n    metadata:\n      labels:\n        app: nginx\n    spec:\n      containers:\n      - name: nginx\n        image: nginx:latest\n        ports:\n        - containerPort: 80"
      }
    ]
  }'
```

### 4. Parse Kubernetes NetworkPolicy

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "name": "network-policy.yaml",
        "content": "apiVersion: networking.k8s.io/v1\nkind: NetworkPolicy\nmetadata:\n  name: deny-all\n  namespace: default\nspec:\n  podSelector: {}\n  policyTypes:\n  - Ingress"
      }
    ]
  }'
```

### 5. Parse Multiple Files

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {
        "name": "main.tf",
        "content": "resource \"aws_s3_bucket\" \"data\" {\n  bucket = \"my-bucket\"\n}"
      },
      {
        "name": "deployment.yaml",
        "content": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n  namespace: default\nspec:\n  replicas: 1\n  selector:\n    matchLabels:\n      app: web"
      }
    ]
  }'
```

**Response combines both:**
```json
{
  "resources": [
    {
      "resource_id": "data",
      "resource_type": "aws_s3_bucket",
      "provider": "aws"
    },
    {
      "resource_id": "default/web",
      "resource_type": "Deployment",
      "provider": "kubernetes"
    }
  ],
  "stats": {
    "total_files": 2,
    "parsed_files": 2,
    "total_resources": 2,
    "terraform_resources": 1,
    "kubernetes_resources": 1,
    "errors": 0
  }
}
```

## Testing with Python

```python
import requests
import json

URL = "http://localhost:8001/parse"

# Test 1: Parse Terraform
payload_tf = {
    "files": [
        {
            "name": "main.tf",
            "content": """
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "main-vpc"
  }
}
"""
        }
    ]
}

response = requests.post(URL, json=payload_tf)
print("Status:", response.status_code)
print("Response:", json.dumps(response.json(), indent=2))

# Test 2: Parse Kubernetes
payload_k8s = {
    "files": [
        {
            "name": "service.yaml",
            "content": """
apiVersion: v1
kind: Service
metadata:
  name: web-svc
  namespace: default
spec:
  type: LoadBalancer
  ports:
  - port: 80
    targetPort: 8080
  selector:
    app: web
"""
        }
    ]
}

response = requests.post(URL, json=payload_k8s)
print("Status:", response.status_code)
print("Response:", json.dumps(response.json(), indent=2))

# Test 3: Error handling - empty files
payload_empty = {
    "files": []
}

response = requests.post(URL, json=payload_empty)
print("Status:", response.status_code)
print("Error Response:", json.dumps(response.json(), indent=2))
```

## Testing with httpie

```bash
# Install httpie
pip install httpie

# Test 1: Parse single Terraform file
http POST http://localhost:8001/parse \
  files:='[{"name": "main.tf", "content": "resource \"aws_s3_bucket\" \"test\" { bucket = \"test-bucket\" }"}]'

# Test 2: Parse single Kubernetes file
http POST http://localhost:8001/parse \
  files:='[{"name": "pod.yaml", "content": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test\n  namespace: default"}]'
```

## Error Cases

### 1. Invalid JSON

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{invalid json}'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "json_invalid",
      "loc": ["body"],
      "msg": "Invalid JSON"
    }
  ]
}
```

### 2. Missing Required Field

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Response:**
```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "files"],
      "msg": "Field required"
    }
  ]
}
```

### 3. Empty Files Array

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{"files": []}'
```

**Response:**
```json
{
  "resources": [],
  "stats": null,
  "errors": ["No files provided in request"]
}
```

### 4. Invalid File Format

```bash
curl -X POST http://localhost:8001/parse \
  -H "Content-Type: application/json" \
  -d '{"files": [{"name": "file.txt"}]}'
```

**Response:**
```json
{
  "resources": [],
  "stats": {
    "errors": 1
  },
  "errors": ["Invalid file format: missing 'name' or 'content' key"]
}
```

## Performance Testing

### Load Testing with Apache Bench

```bash
# Create a test file
cat > test-payload.json << 'EOF'
{
  "files": [
    {
      "name": "main.tf",
      "content": "resource \"aws_s3_bucket\" \"test\" { bucket = \"test-bucket\" }"
    }
  ]
}
EOF

# Run load test: 100 requests, 10 concurrent
ab -p test-payload.json -T application/json -n 100 -c 10 \
  http://localhost:8001/parse
```

### Load Testing with wrk

```bash
# Install wrk (https://github.com/wg/wrk)
brew install wrk

# Create Lua script
cat > test.lua << 'EOF'
request = function()
  wrk.headers["Content-Type"] = "application/json"
  body = '{"files":[{"name":"main.tf","content":"resource \\"aws_s3_bucket\\" \\"test\\" { bucket = \\"test\\" }"}]}'
  return wrk.format(nil, body)
end
EOF

# Run test: 1 connection, 2 threads, 30 seconds
wrk -c 1 -t 2 -d 30s -s test.lua http://localhost:8001/parse
```

## Health Check

```bash
curl http://localhost:8001/openapi.json
curl http://localhost:8001/docs
```

## Debugging

Enable verbose logging in Python:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

import requests
requests.packages.urllib3.disable_warnings()
response = requests.post(...)
```

View FastAPI debug info:

```bash
# Enable uvicorn debug mode
uvicorn app.main:app --reload --log-level debug
```

## Integration Test Script

```bash
#!/bin/bash

# Test parser service

BASE_URL="http://localhost:8001"

echo "Testing Parser Service at $BASE_URL"
echo "===================================="

# Test 1: Terraform S3
echo -e "\nTest 1: Parse Terraform S3"
curl -s -X POST "$BASE_URL/parse" \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "name": "s3.tf",
      "content": "resource \"aws_s3_bucket\" \"data\" { bucket = \"test\" }"
    }]
  }' | python -m json.tool | head -20

# Test 2: Kubernetes Deployment
echo -e "\nTest 2: Parse Kubernetes Deployment"
curl -s -X POST "$BASE_URL/parse" \
  -H "Content-Type: application/json" \
  -d '{
    "files": [{
      "name": "deployment.yaml",
      "content": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\n  namespace: default"
    }]
  }' | python -m json.tool | head -20

# Test 3: Multiple files
echo -e "\nTest 3: Parse Multiple Files"
curl -s -X POST "$BASE_URL/parse" \
  -H "Content-Type: application/json" \
  -d '{
    "files": [
      {"name": "main.tf", "content": "resource \"aws_vpc\" \"v\" { cidr_block = \"10.0.0.0/16\" }"},
      {"name": "pod.yaml", "content": "apiVersion: v1\nkind: Pod\nmetadata:\n  name: test"}
    ]
  }' | python -m json.tool | head -30

echo -e "\n===================================="
echo "Tests completed!"
```

Save as `test-api.sh` and run:

```bash
chmod +x test-api.sh
./test-api.sh
```
