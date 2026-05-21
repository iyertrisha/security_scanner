"""
Hard-coded sample data for testing the Graph Engine.

BASE_RESOURCES = the 'before' state (e.g., main branch).
HEAD_RESOURCES = the 'after' state (e.g., a PR that changes things).

Stored as plain dicts so they can be:
  - Fed into Pydantic models:  Resource(**BASE_RESOURCES[0])
  - Sent as JSON via TestClient: client.post("/graph/build", json={"resources": BASE_RESOURCES})
  - Reused by other services later
"""

# --- BASE (before) state ---
# A small AWS setup: VPC → Subnet → EC2, with a Security Group that
# opens port 22 to the ENTIRE internet (0.0.0.0/0) — a security risk.

BASE_RESOURCES = [
    {
        "resource_id": "vpc-1",
        "type": "vpc",
        "provider": "aws",
    },
    {
        "resource_id": "subnet-1",
        "type": "subnet",
        "provider": "aws",
    },
    {
        "resource_id": "sg-1",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 22, "protocol": "tcp", "cidr": "0.0.0.0/0"}
        ],
    },
    {
        "resource_id": "ec2-1",
        "type": "ec2_instance",
        "provider": "aws",
    },
]

# --- HEAD (after) state ---
# Changes from base:
# 1. sg-1's rule CIDR changed from 0.0.0.0/0 → 10.0.0.0/16 (no longer internet-exposed)
# 2. A new EC2 instance (ec2-2) was added

HEAD_RESOURCES = [
    {
        "resource_id": "vpc-1",
        "type": "vpc",
        "provider": "aws",
    },
    {
        "resource_id": "subnet-1",
        "type": "subnet",
        "provider": "aws",
    },
    {
        "resource_id": "sg-1",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 22, "protocol": "tcp", "cidr": "10.0.0.0/16"}
        ],
    },
    {
        "resource_id": "ec2-1",
        "type": "ec2_instance",
        "provider": "aws",
    },
    {
        "resource_id": "ec2-2",
        "type": "ec2_instance",
        "provider": "aws",
    },
]
