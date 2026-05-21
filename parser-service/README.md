# NetGuard Parser Service

FastAPI microservice for parsing Infrastructure-as-Code (IaC) files and returning normalized JSON resources.

**Port**: 8001

## Features

- **Terraform Parser**: Extracts AWS resources (VPCs, subnets, security groups, IAM roles, EC2, load balancers, RDS, S3 buckets, gateways)
- **Kubernetes YAML Parser**: Extracts Services, Deployments, Ingresses, NetworkPolicies, ConfigMaps, Namespaces, ServiceAccounts
- **Auto-detection**: Automatically detects file type (.tf vs .yaml) and cloud provider
- **Normalized Schema**: Provides consistent JSON schema for all resources across cloud providers
- **Rule Extraction**: Extracts and normalizes inbound/outbound security rules and network policies
- **Comprehensive Testing**: 15+ unit tests with real-world fixtures from TerraGoat and Kubernetes Goat benchmarks

## Installation

```bash
pip install -r requirements.txt
```

## Running the Service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

Access API documentation at `http://localhost:8001/docs`

## API Endpoints

### POST /parse

Parse Infrastructure-as-Code files and return normalized resources.

**Request:**
```json
{
  "files": [
    {
      "name": "main.tf",
      "content": "resource \"aws_s3_bucket\" \"my_bucket\" { ... }"
    },
    {
      "name": "deployment.yaml",
      "content": "apiVersion: apps/v1\nkind: Deployment\n..."
    }
  ]
}
```

**Response:**
```json
{
  "resources": [
    {
      "resource_id": "my_bucket",
      "resource_type": "aws_s3_bucket",
      "provider": "aws",
      "properties": { ... },
      "inbound_rules": [],
      "outbound_rules": [],
      "tags": {
        "Name": "my_bucket",
        "Environment": "prod"
      },
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

## Normalized JSON Schema

All parsed resources conform to the following schema:

```python
{
  "resource_id": str,           # Unique resource identifier
  "resource_type": str,         # Resource type (e.g., aws_s3_bucket, Deployment)
  "provider": str,              # Cloud provider (aws, gcp, azure, kubernetes)
  "properties": Dict,           # Full resource configuration
  "inbound_rules": List[Rule],  # Inbound security rules
  "outbound_rules": List[Rule], # Outbound security rules
  "tags": Dict,                 # Resource tags/labels
  "network_policies": List,     # Kubernetes network policies (optional)
  "metadata": Dict              # Additional metadata
}

Rule = {
  "port": str,           # Port or port range
  "protocol": str,       # tcp, udp, icmp, all
  "cidr": str,          # CIDR block or IP
  "description": str    # Optional description
}
```

## Supported Resources

### Terraform (AWS)

- **Networking**: VPC, Subnet, Security Group, Internet Gateway, NAT Gateway, EIP
- **Compute**: EC2 Instance, Auto Scaling Group
- **Storage**: S3 Bucket, S3 Bucket Public Access Block, EBS Volume
- **Database**: RDS Instance, DB Instance
- **IAM**: IAM User, IAM Role, IAM Policy, IAM Access Key
- **Load Balancing**: ALB, NLB, Classic Load Balancer

### Kubernetes

- Deployment
- Service (ClusterIP, NodePort, LoadBalancer)
- Ingress
- NetworkPolicy (with ingress/egress rules)
- ConfigMap
- Secret
- ServiceAccount
- Role / ClusterRole
- RoleBinding / ClusterRoleBinding
- Namespace

## Project Structure

```
parser-service/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── parser_router.py     # API endpoints
│   ├── terraform_parser.py  # Terraform parsing logic
│   ├── kubernetes_parser.py # Kubernetes parsing logic
│   ├── schema.py            # Pydantic models/schemas
│   └── utils.py             # Utility functions
├── tests/
│   └── test_parser.py       # Comprehensive test suite
├── benchmark/
│   ├── terragoat/          # TerraGoat fixtures
│   └── kubernetes-goat/    # Kubernetes Goat fixtures
├── requirements.txt
└── README.md
```

## Testing

Run the full test suite:

```bash
pytest tests/test_parser.py -v
```

Run specific test class:

```bash
pytest tests/test_parser.py::TestTerraformParser -v
```

Run with coverage:

```bash
pytest tests/test_parser.py --cov=app --cov-report=html
```

## Test Coverage

The test suite includes 15+ tests covering:

### Terraform Parser (8 tests)
- ✅ S3 bucket parsing
- ✅ IAM user and policy parsing
- ✅ Security group with ingress/egress rules
- ✅ EC2 instance parsing
- ✅ RDS database instance parsing
- ✅ VPC, subnet, and internet gateway
- ✅ NAT gateway and Elastic IP
- ✅ Schema validation and error handling

### Kubernetes Parser (9 tests)
- ✅ Deployment parsing
- ✅ Service parsing with port extraction
- ✅ NetworkPolicy parsing with ingress/egress rules
- ✅ ConfigMap parsing
- ✅ Secret parsing
- ✅ Ingress parsing
- ✅ ServiceAccount and RBAC parsing
- ✅ Metadata extraction
- ✅ Schema validation and error handling

### Integration Tests (3 tests)
- ✅ Multiple file type parsing
- ✅ Resource schema consistency
- ✅ File type and provider detection

## Example Usage

### Python Client

```python
import requests

url = "http://localhost:8001/parse"

payload = {
    "files": [
        {
            "name": "main.tf",
            "content": """
resource "aws_security_group" "web" {
  name = "web-sg"
  
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
"""
        }
    ]
}

response = requests.post(url, json=payload)
resources = response.json()["resources"]

for resource in resources:
    print(f"{resource['provider']}/{resource['resource_type']}/{resource['resource_id']}")
    for rule in resource["inbound_rules"]:
        print(f"  - Port {rule['port']}/{rule['protocol']} from {rule['cidr']}")
```

### Using FastAPI Docs

1. Navigate to `http://localhost:8001/docs`
2. Expand the POST /parse endpoint
3. Click "Try it out"
4. Paste your Terraform or Kubernetes configuration
5. Click "Execute"

## Benchmark Fixtures

The project includes real-world vulnerable configurations from:

- **TerraGoat**: Open-source Terraform security benchmark with 100+ misconfigurations
- **Kubernetes Goat**: Open-source Kubernetes security benchmark with intentional vulnerabilities

These are used as test fixtures to ensure the parser correctly handles:
- Complex nested configurations
- Various cloud providers (AWS, GCP, Azure, Oracle)
- Security group rules and network policies
- IAM policies and RBAC configurations
- Tags and metadata

## Performance Considerations

- **Terraform Parsing**: Uses `python-hcl2` library for HCL parsing
- **Kubernetes Parsing**: Uses PyYAML for YAML parsing
- **Rule Extraction**: Optimized to extract only relevant security rules
- **Error Handling**: Graceful degradation - invalid files don't crash the service

## Error Handling

The API provides detailed error information:

```json
{
  "resources": [],
  "stats": {
    "total_files": 1,
    "parsed_files": 0,
    "total_resources": 0,
    "terraform_resources": 0,
    "kubernetes_resources": 0,
    "errors": 1
  },
  "errors": [
    "Terraform parse error in 'main.tf': Invalid HCL syntax"
  ]
}
```

## Development

### Adding a New Resource Type

1. Update `terraform_parser.py` or `kubernetes_parser.py`
2. Add extraction logic in the respective parser
3. Add test fixtures and tests to `test_parser.py`
4. Update this README with the new resource type

### Debugging

Enable verbose logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Future Enhancements

- [ ] GCP Terraform provider support
- [ ] Azure Resource Manager (ARM) template parsing
- [ ] Helm chart parsing
- [ ] CloudFormation template parsing
- [ ] Precision/recall benchmarks (Phase 6)
- [ ] Performance optimizations for large files
- [ ] Caching of parsed resources

## Contributing

1. Add tests for new resource types
2. Ensure all tests pass: `pytest tests/test_parser.py -v`
3. Update documentation
4. Follow PEP 8 code style

## License

MIT

## Links

- [TerraGoat Repository](https://github.com/bridgecrewio/terragoat)
- [Kubernetes Goat Repository](https://github.com/madhuakula/kubernetes-goat)
- [Terraform Documentation](https://www.terraform.io/docs)
- [Kubernetes Documentation](https://kubernetes.io/docs)
