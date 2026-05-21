# Development Guide

Comprehensive guide for developing and extending the NetGuard Parser Service

## Table of Contents

1. [Setup & Installation](#setup--installation)
2. [Project Architecture](#project-architecture)
3. [Adding New Resource Types](#adding-new-resource-types)
4. [Extending Parsers](#extending-parsers)
5. [Testing Guidelines](#testing-guidelines)
6. [Code Style](#code-style)
7. [Debugging](#debugging)
8. [Performance Optimization](#performance-optimization)

## Setup & Installation

### Prerequisites

- Python 3.8+
- pip
- Virtual environment (recommended)

### Installation Steps

```bash
# Clone or navigate to project
cd parser-service

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Linux/Mac:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install development dependencies
pip install black flake8 pytest-cov ipython
```

### Verify Installation

```bash
# Run tests
pytest tests/test_parser.py -v

# Start development server
uvicorn app.main:app --reload --port 8001

# Check API docs
curl http://localhost:8001/docs
```

## Project Architecture

### Directory Structure

```
parser-service/
├── app/
│   ├── __init__.py              # Package initialization
│   ├── main.py                  # FastAPI app setup
│   ├── parser_router.py         # API endpoints
│   ├── terraform_parser.py      # Terraform parsing logic
│   ├── kubernetes_parser.py     # Kubernetes parsing logic
│   ├── schema.py                # Pydantic models
│   └── utils.py                 # Utility functions
├── tests/
│   └── test_parser.py           # Test suite (26 tests)
├── benchmark/
│   ├── terragoat/              # TerraGoat fixtures
│   └── kubernetes-goat/        # Kubernetes Goat fixtures
├── requirements.txt
├── README.md
├── SCHEMA.md
├── API_TESTING.md
└── DEVELOPMENT.md              # This file
```

### Data Flow

```
Client Request
    ↓
parser_router.py (@router.post("/parse"))
    ↓
├─→ detect_file_and_provider() [utils.py]
    ↓
├─→ parse_terraform() [terraform_parser.py]
│   ├─→ hcl2.loads() → parse HCL
│   ├─→ extract_security_group_rules()
│   ├─→ extract_aws_resources()
│   └─→ return [Resource dict, ...]
│
├─→ parse_kubernetes() [kubernetes_parser.py]
│   ├─→ yaml.safe_load_all() → parse YAML
│   ├─→ extract_network_policies()
│   ├─→ extract_service_rules()
│   └─→ return [Resource dict, ...]
    ↓
Resource(**res) [schema.py - validation]
    ↓
ParseResponse(resources=[...], stats={...}, errors=[...])
    ↓
JSON Response to Client
```

## Adding New Resource Types

### Example: Add Support for AWS Load Balancer

#### 1. Update Terraform Parser

Edit `app/terraform_parser.py`:

```python
# Add to extract_aws_resources() function

def extract_load_balancer_rules(config: Dict) -> List[Dict]:
    """Extract rules from load balancer configuration"""
    rules = []
    
    listeners = config.get("listener", [])
    if not isinstance(listeners, list):
        listeners = [listeners]
    
    for listener in listeners:
        if isinstance(listener, dict):
            rule = {
                "port": str(listener.get("instance_port", "*")),
                "protocol": listener.get("instance_protocol", "http").upper(),
                "cidr": "0.0.0.0/0",  # Load balancers accept from anywhere
                "description": f"LB listener on port {listener.get('instance_port')}"
            }
            rules.append(rule)
    
    return rules

# In extract_aws_resources(), add this case:
elif resource_type == "aws_elb":  # Classic Load Balancer
    inbound_rules = extract_load_balancer_rules(config)
    outbound_rules = []
```

#### 2. Update Tests

Add test case to `tests/test_parser.py`:

```python
TERRAFORM_ELB_FIXTURE = """
resource "aws_elb" "web" {
  name               = "foobar-terraform-elb"
  availability_zones = ["us-west-2a", "us-west-2b"]

  listener {
    instance_port     = 8000
    instance_protocol = "http"
    lb_port           = 80
    lb_protocol       = "http"
  }

  instances                   = [aws_instance.web.id]
  cross_zone_load_balancing   = true
  idle_timeout                = 400
  connection_draining         = true
  connection_draining_timeout = 400

  tags = {
    Name = "foobar-terraform-elb"
  }
}
"""

class TestTerraformParser:
    def test_parse_load_balancer(self):
        """Test parsing AWS Classic Load Balancer"""
        resources = parse_terraform(TERRAFORM_ELB_FIXTURE)
        assert len(resources) >= 1
        
        elb = resources[0]
        assert elb["resource_type"] == "aws_elb"
        assert elb["provider"] == "aws"
        assert len(elb["inbound_rules"]) > 0
```

#### 3. Run Tests

```bash
pytest tests/test_parser.py::TestTerraformParser::test_parse_load_balancer -v
```

### Example: Add Support for Kubernetes StatefulSet

#### 1. Update Kubernetes Parser

The parser already handles `StatefulSet` because it uses generic `yaml.safe_load_all()`:

Just add a test to verify:

#### 2. Update Tests

```python
KUBERNETES_STATEFULSET_FIXTURE = """
apiVersion: v1
kind: Service
metadata:
  name: mysql
spec:
  ports:
  - port: 3306
  clusterIP: None
  selector:
    app: mysql
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mysql
spec:
  serviceName: mysql
  replicas: 3
  selector:
    matchLabels:
      app: mysql
  template:
    metadata:
      labels:
        app: mysql
    spec:
      containers:
      - name: mysql
        image: mysql:5.7
        ports:
        - containerPort: 3306
"""

class TestKubernetesParser:
    def test_parse_statefulset(self):
        """Test parsing Kubernetes StatefulSet"""
        resources = parse_kubernetes(KUBERNETES_STATEFULSET_FIXTURE)
        
        statefulsets = [r for r in resources if r["resource_type"] == "StatefulSet"]
        assert len(statefulsets) >= 1
        
        ss = statefulsets[0]
        assert ss["resource_id"].endswith("/mysql")
        assert ss["provider"] == "kubernetes"
```

## Extending Parsers

### Adding New Provider Support

To add a new cloud provider (e.g., GCP):

#### 1. Create New Parser

Create `app/gcp_parser.py`:

```python
import json
from typing import List, Dict, Any

def detect_gcp_provider(resource_type: str) -> str:
    """Detect GCP resources by type prefix"""
    if resource_type.startswith("google_"):
        return "gcp"
    return "unknown"

def extract_gcp_firewall_rules(config: Dict) -> List[Dict]:
    """Extract firewall rules from GCP config"""
    rules = []
    
    allows = config.get("allow", [])
    if not isinstance(allows, list):
        allows = [allows]
    
    for allow in allows:
        if isinstance(allow, dict):
            protocols = allow.get("protocol", [])
            ports = allow.get("ports", [])
            
            if not isinstance(protocols, list):
                protocols = [protocols]
            if not isinstance(ports, list):
                ports = [ports]
            
            for protocol in protocols:
                for port in ports:
                    rule = {
                        "port": port if port != "-1" else "*",
                        "protocol": protocol,
                        "cidr": ", ".join(config.get("source_ranges", ["0.0.0.0/0"])),
                        "description": config.get("description", "")
                    }
                    rules.append(rule)
    
    return rules

def parse_gcp(content: str) -> List[Dict[str, Any]]:
    """Parse GCP Terraform configuration"""
    try:
        # Parse HCL similar to AWS
        from app.terraform_parser import parse_terraform
        # GCP uses same HCL format
        return parse_terraform(content)  # Use existing HCL parser
    except Exception as e:
        return []
```

#### 2. Update Router

Edit `app/parser_router.py`:

```python
from app.gcp_parser import parse_gcp

# In parse_files endpoint:
elif file_type == "gcp" or "google_" in content_lower:
    try:
        parsed_resources = parse_gcp(content)
        stats["gcp_resources"] += len(parsed_resources)
    except Exception as e:
        errors.append(f"GCP parse error in '{name}': {str(e)}")
```

#### 3. Add Tests

```python
GCP_FIREWALL_FIXTURE = """
resource "google_compute_firewall" "default" {
  name    = "test-firewall"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", "80", "443"]
  }

  source_ranges = ["0.0.0.0/0"]
}
"""

def test_parse_gcp_firewall():
    """Test parsing GCP firewall"""
    resources = parse_gcp(GCP_FIREWALL_FIXTURE)
    # ...
```

### Customizing Rule Extraction

If you need different rule extraction logic:

```python
# In terraform_parser.py

def extract_custom_rules(config: Dict, rule_type: str) -> List[Dict]:
    """Custom rule extraction for specific resource types"""
    rules = []
    
    # Your custom logic here
    for rule_config in config.get(rule_type, []):
        rule = {
            "port": str(rule_config.get("port")),
            "protocol": rule_config.get("protocol"),
            "cidr": rule_config.get("source"),
            "description": rule_config.get("note")
        }
        rules.append(rule)
    
    return rules
```

## Testing Guidelines

### Unit Testing Structure

```python
# Test file structure
class TestParserName:
    """Test class for specific parser"""
    
    @pytest.fixture
    def sample_content(self):
        """Fixture providing test content"""
        return "resource ..."
    
    def test_parsing_success(self, sample_content):
        """Test successful parsing"""
        resources = parse_xxx(sample_content)
        assert len(resources) > 0
    
    def test_error_handling(self):
        """Test error cases"""
        resources = parse_xxx("invalid content")
        assert isinstance(resources, list)
```

### Running Tests

```bash
# All tests
pytest tests/test_parser.py

# Specific test class
pytest tests/test_parser.py::TestTerraformParser

# Specific test
pytest tests/test_parser.py::TestTerraformParser::test_parse_s3_bucket

# Verbose output
pytest tests/test_parser.py -v

# With coverage
pytest tests/test_parser.py --cov=app --cov-report=html

# Watch mode (requires pytest-watch)
ptw tests/test_parser.py
```

### Test Coverage Target

Aim for >85% code coverage:

```bash
pytest tests/test_parser.py --cov=app --cov-report=term-missing

# View HTML report
pytest tests/test_parser.py --cov=app --cov-report=html
open htmlcov/index.html
```

## Code Style

### Code Formatting

Use Black for consistent formatting:

```bash
# Format single file
black app/terraform_parser.py

# Format entire app
black app/

# Check formatting without changing
black app/ --check
```

### Linting

Use Flake8 to check code quality:

```bash
# Check entire app
flake8 app/

# Check specific file
flake8 app/terraform_parser.py

# Show style guide
flake8 app/ --statistics
```

### Type Hints

Always use type hints:

```python
# Good ✓
def parse_terraform(content: str) -> List[Dict[str, Any]]:
    """Parse Terraform HCL content"""
    pass

# Avoid ✗
def parse_terraform(content):
    pass
```

### Docstrings

Use Google-style docstrings:

```python
def extract_rules(config: Dict, rule_type: str) -> List[Dict]:
    """Extract security rules from configuration.
    
    Args:
        config: Resource configuration dictionary
        rule_type: Type of rule (ingress or egress)
    
    Returns:
        List of normalized rule dictionaries
    
    Raises:
        ValueError: If config format is invalid
    """
    pass
```

## Debugging

### Enable Debug Logging

```python
# In main.py or router
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
```

### Interactive Debugging

```python
# Use IPython REPL
from IPython import embed

def parse_terraform(content: str):
    data = hcl2.loads(content)
    embed()  # Drops into IPython debugger
    # Inspect 'data' interactively
```

### Print Debugging

```python
# Add debug prints
import json

def parse_terraform(content: str):
    data = hcl2.loads(content)
    print("Parsed HCL:", json.dumps(data, indent=2, default=str))
    
    resources = extract_aws_resources(data)
    print(f"Extracted {len(resources)} resources")
```

### Test Debugging

```bash
# Run with pdb debugger
pytest tests/test_parser.py::TestTerraformParser::test_parse_s3_bucket -s

# Stop on first failure
pytest tests/test_parser.py -x

# Show local variables on failure
pytest tests/test_parser.py -l
```

## Performance Optimization

### Profiling

```bash
# Profile with cProfile
python -m cProfile -s cumulative -m pytest tests/test_parser.py

# Profile with line_profiler
pip install line_profiler
kernprof -l -v app/terraform_parser.py
```

### Benchmarking

```python
import time

def benchmark_parser(content: str, iterations: int = 100):
    """Benchmark parser performance"""
    start = time.time()
    
    for _ in range(iterations):
        resources = parse_terraform(content)
    
    elapsed = time.time() - start
    avg_time = elapsed / iterations
    
    print(f"Parsed {iterations} files in {elapsed:.2f}s")
    print(f"Average: {avg_time*1000:.2f}ms per file")
    print(f"Throughput: {iterations/elapsed:.1f} files/sec")

# Usage
with open("large_terraform.tf") as f:
    content = f.read()
benchmark_parser(content)
```

### Optimization Tips

1. **Cache HCL/YAML parsing**: Reuse parsed structures
2. **Batch rule extraction**: Process multiple rules at once
3. **Lazy loading**: Load large configurations on demand
4. **Parallel processing**: Parse multiple files concurrently

```python
# Example: Parallel file parsing
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import cpu_count

def parse_files_parallel(files: List[Dict]) -> List[Dict]:
    """Parse multiple files in parallel"""
    resources = []
    
    with ThreadPoolExecutor(max_workers=cpu_count()) as executor:
        futures = []
        
        for file in files:
            if file["name"].endswith(".tf"):
                future = executor.submit(parse_terraform, file["content"])
            elif file["name"].endswith((".yaml", ".yml")):
                future = executor.submit(parse_kubernetes, file["content"])
            else:
                continue
            
            futures.append(future)
        
        for future in futures:
            resources.extend(future.result())
    
    return resources
```

## Maintenance

### Keeping Dependencies Updated

```bash
# Check for outdated packages
pip list --outdated

# Update all packages
pip install --upgrade -r requirements.txt

# Update specific package
pip install --upgrade fastapi
```

### Monitoring

```bash
# Check service health
curl http://localhost:8001/openapi.json

# Monitor logs
tail -f /var/log/parser-service.log

# Check resource usage
ps aux | grep uvicorn
```

---

For questions or issues, refer to:
- [README.md](README.md) - Project overview
- [SCHEMA.md](SCHEMA.md) - Schema documentation
- [API_TESTING.md](API_TESTING.md) - API testing guide
