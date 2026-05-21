# Parser Service - JSON Schema Documentation

This document describes the normalized JSON schema that all parser services produce. This is the **contract** that all downstream services depend on.

## Overview

All Infrastructure-as-Code resources (Terraform, Kubernetes, CloudFormation, etc.) are normalized into a consistent JSON schema that enables:

- **Consistency**: Same structure regardless of source format or cloud provider
- **Compatibility**: Downstream services can work with any provider
- **Extensibility**: New fields can be added without breaking existing services
- **Searchability**: Standardized queries across all resource types

## Core Resource Schema

```json
{
  "resource_id": "string",
  "resource_type": "string",
  "provider": "string",
  "properties": "object",
  "inbound_rules": "array",
  "outbound_rules": "array",
  "tags": "object",
  "network_policies": "array|null",
  "metadata": "object"
}
```

### Field Definitions

#### resource_id
- **Type**: `string` (required)
- **Description**: Unique identifier for the resource within its provider and type
- **Examples**:
  - Terraform: `"my-bucket"`, `"web-sg"`, `"db-instance"`
  - Kubernetes: `"default/nginx-deployment"`, `"kube-system/coredns"` (format: `namespace/name`)
- **Uniqueness**: `{provider}:{resource_type}:{resource_id}` should be globally unique

#### resource_type
- **Type**: `string` (required)
- **Description**: Type classification of the resource
- **AWS Terraform Examples**:
  - `"aws_s3_bucket"`, `"aws_security_group"`, `"aws_instance"`
  - `"aws_iam_role"`, `"aws_rds_instance"`, `"aws_vpc"`
- **Kubernetes Examples**:
  - `"Deployment"`, `"Service"`, `"Ingress"`, `"NetworkPolicy"`
  - `"ConfigMap"`, `"Secret"`, `"ServiceAccount"`, `"Role"`
- **GCP Terraform Examples**:
  - `"google_compute_instance"`, `"google_storage_bucket"`, `"google_container_cluster"`

#### provider
- **Type**: `string` (required, enum)
- **Description**: Cloud provider or orchestration platform
- **Allowed Values**:
  - `"aws"` - Amazon Web Services
  - `"gcp"` - Google Cloud Platform
  - `"azure"` - Microsoft Azure
  - `"oracle"` - Oracle Cloud
  - `"kubernetes"` - Kubernetes (any provider)
  - `"unknown"` - Could not detect provider

#### properties
- **Type**: `object` (required, default: `{}`)
- **Description**: Complete resource configuration as extracted from source
- **Content**: All attributes from the original resource definition
- **Examples**:
  ```json
  {
    "bucket": "my-data-bucket",
    "versioning": true,
    "server_side_encryption_configuration": {...},
    "lifecycle": {...}
  }
  ```
- **Notes**:
  - Sensitive data (passwords, keys) should NOT be included
  - Computed/generated values may vary from source

#### inbound_rules
- **Type**: `array[Rule]` (required, default: `[]`)
- **Description**: Ingress/inbound security rules
- **Applicable to**:
  - Security Groups (AWS)
  - Network ACLs (AWS)
  - Services (Kubernetes)
  - Firwall rules (GCP, Azure)
- **See**: Rule schema below

#### outbound_rules
- **Type**: `array[Rule]` (required, default: `[]`)
- **Description**: Egress/outbound security rules
- **Applicable to**:
  - Security Groups (AWS)
  - Network ACLs (AWS)
  - NetworkPolicies (Kubernetes egress)
- **See**: Rule schema below

#### tags
- **Type**: `object` (required, default: `{}`)
- **Description**: Resource tags, labels, or annotations
- **Key-Value Pairs**:
  - **Keys**: string, typically lowercase with hyphens
  - **Values**: string
- **Examples**:
  ```json
  {
    "Name": "web-server",
    "Environment": "production",
    "CostCenter": "engineering",
    "ManagedBy": "terraform"
  }
  ```
- **Kubernetes**: Uses `metadata.labels`
- **AWS**: Uses `tags` attribute
- **GCP**: Uses `labels` attribute

#### network_policies
- **Type**: `array[NetworkPolicy]` | `null` (optional)
- **Description**: Network access policies (Kubernetes-specific)
- **Applicable to**:
  - NetworkPolicy resources (primary)
  - Services, Ingresses (may include policy context)
- **See**: NetworkPolicy schema below
- **Default**: `null` if not applicable

#### metadata
- **Type**: `object` (required, default: `{}`)
- **Description**: Additional metadata about resource extraction
- **Standard Fields**:
  ```json
  {
    "file_type": "terraform|kubernetes|cloudformation",
    "extracted_from": "resource_type",
    "namespace": "string (kubernetes only)",
    "api_version": "string (kubernetes only)",
    "region": "string (aws only)",
    "account_id": "string (aws only)"
  }
  ```

## Rule Schema

Security rules extracted from various sources (Security Groups, NetworkPolicies, etc.)

```json
{
  "port": "string|null",
  "protocol": "string",
  "cidr": "string",
  "description": "string|null"
}
```

### Rule Field Definitions

#### port
- **Type**: `string` | `null` (optional)
- **Description**: Port or port range
- **Formats**:
  - Single port: `"80"`, `"443"`
  - Port range: `"80-8080"`, `"1000-65535"`
  - All ports: `"*"`, `"0-65535"`
  - None (ICMP): `null`
- **Default**: `null`

#### protocol
- **Type**: `string` (required)
- **Description**: Network protocol
- **Values**:
  - `"tcp"` - Transmission Control Protocol
  - `"udp"` - User Datagram Protocol
  - `"icmp"` - Internet Control Message Protocol
  - `"igmp"` - Internet Group Management Protocol
  - `"all"` - All protocols (`-1` in AWS)
- **Case**: Lowercase

#### cidr
- **Type**: `string` (required)
- **Description**: Source/destination IP range or special identifier
- **Formats**:
  - CIDR notation: `"10.0.0.0/8"`, `"172.16.0.0/12"`, `"192.168.0.0/16"`
  - Single IP: `"10.0.0.5/32"`, `"203.0.113.42/32"`
  - All traffic: `"0.0.0.0/0"`, `"::/0"`
  - Special (Kubernetes): `"cluster-internal"`, `"pod-internal"`
- **Default Insecure**: `"0.0.0.0/0"` indicates open to all IPs

#### description
- **Type**: `string` | `null` (optional)
- **Description**: Human-readable rule description
- **Examples**:
  - `"Allow HTTP traffic"`
  - `"Database access from app servers"`
  - `"Prometheus metrics endpoint"`
- **Default**: `null` or empty string

### Example Rules

```json
[
  {
    "port": "443",
    "protocol": "tcp",
    "cidr": "0.0.0.0/0",
    "description": "HTTPS from anywhere"
  },
  {
    "port": "3306",
    "protocol": "tcp",
    "cidr": "10.0.1.0/24",
    "description": "MySQL from application subnet"
  },
  {
    "port": null,
    "protocol": "icmp",
    "cidr": "10.0.0.0/8",
    "description": "ICMP from internal network"
  }
]
```

## NetworkPolicy Schema

Kubernetes NetworkPolicy specification (extracted from NetworkPolicy resources)

```json
{
  "ingress": "array|null",
  "egress": "array|null",
  "pod_selector": "object|null",
  "policy_types": "array|null"
}
```

### NetworkPolicy Field Definitions

#### ingress
- **Type**: `array` | `null`
- **Description**: Ingress policy rules (inbound)
- **Content**: Kubernetes policyRule objects
- **See**: Kubernetes NetworkPolicy specification

#### egress
- **Type**: `array` | `null`
- **Description**: Egress policy rules (outbound)
- **Content**: Kubernetes policyRule objects

#### pod_selector
- **Type**: `object` | `null`
- **Description**: Pod selector for policy application
- **Content**: Kubernetes selector objects
- **Examples**:
  ```json
  { "matchLabels": { "role": "db" } }
  ```

#### policy_types
- **Type**: `array` | `null`
- **Description**: Policy types (Ingress, Egress, or both)
- **Values**: `["Ingress"]`, `["Egress"]`, `["Ingress", "Egress"]`

### Example NetworkPolicy

```json
{
  "ingress": [
    {
      "from": [
        { "podSelector": { "matchLabels": { "role": "frontend" } } }
      ],
      "ports": [
        { "protocol": "TCP", "port": 5432 }
      ]
    }
  ],
  "egress": [
    {
      "to": [{ "namespaceSelector": {} }],
      "ports": [
        { "protocol": "TCP", "port": 53 }
      ]
    }
  ],
  "pod_selector": { "matchLabels": { "role": "db" } },
  "policy_types": ["Ingress", "Egress"]
}
```

## Complete Example: AWS Security Group

```json
{
  "resource_id": "web-sg",
  "resource_type": "aws_security_group",
  "provider": "aws",
  "properties": {
    "name": "web-sg",
    "description": "Security group for web servers",
    "vpc_id": "vpc-12345678",
    "tags": {
      "Name": "web-sg",
      "Environment": "prod"
    }
  },
  "inbound_rules": [
    {
      "port": "80",
      "protocol": "tcp",
      "cidr": "0.0.0.0/0",
      "description": "HTTP from anywhere"
    },
    {
      "port": "443",
      "protocol": "tcp",
      "cidr": "0.0.0.0/0",
      "description": "HTTPS from anywhere"
    },
    {
      "port": "22",
      "protocol": "tcp",
      "cidr": "10.0.0.0/8",
      "description": "SSH from internal network"
    }
  ],
  "outbound_rules": [
    {
      "port": "0-65535",
      "protocol": "all",
      "cidr": "0.0.0.0/0",
      "description": "All traffic outbound"
    }
  ],
  "tags": {
    "Name": "web-sg",
    "Environment": "prod",
    "ManagedBy": "terraform"
  },
  "network_policies": null,
  "metadata": {
    "file_type": "terraform",
    "extracted_from": "aws_security_group",
    "region": "us-west-2",
    "account_id": "123456789012"
  }
}
```

## Complete Example: Kubernetes Deployment

```json
{
  "resource_id": "default/nginx-deployment",
  "resource_type": "Deployment",
  "provider": "kubernetes",
  "properties": {
    "replicas": 3,
    "selector": {
      "matchLabels": { "app": "nginx" }
    },
    "template": {
      "metadata": {
        "labels": { "app": "nginx" }
      },
      "spec": {
        "containers": [
          {
            "name": "nginx",
            "image": "nginx:1.21",
            "ports": [{ "containerPort": 80 }]
          }
        ]
      }
    }
  },
  "inbound_rules": [],
  "outbound_rules": [],
  "tags": {
    "app": "nginx",
    "version": "1.0"
  },
  "network_policies": null,
  "metadata": {
    "file_type": "kubernetes",
    "extracted_from": "Deployment",
    "namespace": "default",
    "api_version": "apps/v1"
  }
}
```

## Complete Example: Kubernetes NetworkPolicy

```json
{
  "resource_id": "default/deny-all-ingress",
  "resource_type": "NetworkPolicy",
  "provider": "kubernetes",
  "properties": {
    "podSelector": {},
    "policyTypes": ["Ingress"]
  },
  "inbound_rules": [],
  "outbound_rules": [],
  "tags": {},
  "network_policies": [
    {
      "ingress": [],
      "egress": null,
      "pod_selector": {},
      "policy_types": ["Ingress"]
    }
  ],
  "metadata": {
    "file_type": "kubernetes",
    "extracted_from": "NetworkPolicy",
    "namespace": "default",
    "api_version": "networking.k8s.io/v1"
  }
}
```

## Validation Rules

All resources MUST satisfy:

1. **Required Fields**: `resource_id`, `resource_type`, `provider` must be non-empty strings
2. **Valid Provider**: Must be one of: `aws`, `gcp`, `azure`, `oracle`, `kubernetes`, `unknown`
3. **Valid Rules**: Each rule must have `protocol` and `cidr`
4. **Tags**: Must be key-value pairs where keys and values are strings
5. **No Duplicates**: Within a resource, rules should not be duplicated

## Type Conversions

When converting from source formats:

### Terraform to Schema
- Resource name → `resource_id`
- `terraform_resource_type` → `resource_type`
- AWS inferred → `provider: "aws"`
- `ingress` blocks → `inbound_rules`
- `egress` blocks → `outbound_rules`
- `tags` → `tags`

### Kubernetes YAML to Schema
- `metadata.name` → `resource_id`
- `kind` → `resource_type`
- Kubernetes inferred → `provider: "kubernetes"`
- Service ports → `inbound_rules`
- NetworkPolicy ingress → `inbound_rules`
- NetworkPolicy egress → `outbound_rules`
- `metadata.labels` → `tags`

## Extension Points

Future enhancements:

- Add `compliance_tags` for security scanning
- Add `relationships` to link resources
- Add `sensitivity_level` for data classification
- Add `owner` for organizational mapping
- Add `cost_center` for financial tracking
- Add `audit_trail` for change history

## Version History

- **v1.0** (Current): Initial schema with basic resource support
  - Resources: Terraform AWS, Kubernetes
  - Rules: Ingress/Egress with port/protocol/CIDR
  - Metadata: File type, extraction source

---

**Contract Stability**: This schema is versioned and maintained for backward compatibility. Breaking changes will increment the major version number.
