#!/usr/bin/env python
"""
NetGuard Demo: Full Pipeline (Graph Engine → Risk Scorer)

Demonstrates the complete workflow:
  1. Parse dummy AWS resources
  2. Build network topology graph
  3. Generate security findings
  4. Display results in readable format
"""

import json
from datetime import datetime
from services.graph_engine.builder import build_graph
from services.graph_engine.serializer import serialize_graph
from services.risk_scorer.schemas import Resource, GraphContext, Rule, ScoreRequest
from services.risk_scorer.main import app as risk_scorer_app
from fastapi.testclient import TestClient

# ────────────────────────────────────────────────────────────────────────────
# SCENARIO: Public Website → Admin EC2 → Production Database
# ────────────────────────────────────────────────────────────────────────────

DEMO_RESOURCES_GRAPH = [
    {
        "resource_id": "sg-public",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 80, "protocol": "tcp", "cidr": "0.0.0.0/0"},   # HTTP from internet
            {"port": 443, "protocol": "tcp", "cidr": "0.0.0.0/0"},  # HTTPS from internet
        ],
    },
    {
        "resource_id": "ec2-web",
        "type": "ec2_instance",
        "provider": "aws",
    },
    {
        "resource_id": "sg-admin",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 22, "protocol": "tcp", "cidr": "10.0.0.0/8"},  # SSH from private
        ],
    },
    {
        "resource_id": "ec2-admin",
        "type": "ec2_instance",
        "provider": "aws",
    },
    {
        "resource_id": "sg-db",
        "type": "security_group",
        "provider": "aws",
        "rules": [
            {"port": 5432, "protocol": "tcp", "cidr": "10.0.0.0/8"},  # PostgreSQL
        ],
    },
    {
        "resource_id": "rds-prod",
        "type": "rds_instance",
        "provider": "aws",
    },
]

DEMO_RESOURCES_RISK = [
    Resource(
        resource_id="ec2-web",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "WebServerRole",
            "security_groups": ["sg-public"],
            "state": "running",
            "instance_type": "t3.medium",
        },
        tags={"name": "web-server", "environment": "prod"},
    ),
    Resource(
        resource_id="ec2-admin",
        resource_type="aws_ec2_instance",
        provider="aws",
        properties={
            "iam_instance_profile": "AdminRole",  # ⚠️ Privileged role
            "security_groups": ["sg-admin"],
            "state": "running",
            "instance_type": "t3.large",
        },
        tags={"name": "admin-server", "environment": "prod"},
    ),
    Resource(
        resource_id="rds-prod",
        resource_type="aws_rds_instance",
        provider="aws",
        properties={
            "engine": "postgres",
            "publicly_accessible": False,
            "multi_az": True,
            "encryption_enabled": True,
            "db_name": "production_db",
        },
        inbound_rules=[Rule(port=5432, protocol="tcp", cidr="10.0.0.0/8")],
        tags={"name": "production-database", "environment": "prod"},
    ),
]


def print_section(title: str, char: str = "="):
    """Print a formatted section header."""
    print(f"\n{char * 80}")
    print(f"  {title}")
    print(f"{char * 80}\n")


def print_graph_info(graph_data: dict):
    """Pretty-print graph information."""
    print(f"📊 Graph Metadata:")
    print(f"   • Nodes: {graph_data['metadata']['node_count']}")
    print(f"   • Edges: {graph_data['metadata']['edge_count']}")
    print(f"\n📍 Nodes:")
    for node in graph_data["nodes"]:
        print(f"   • {node['id']:<20} → {node['type']}")
    print(f"\n🔗 Edges:")
    for edge in graph_data["edges"]:
        print(f"   • {edge['source']:<20} → {edge['target']:<20} [{edge['relationship']}]")


def print_findings(findings_data: dict):
    """Pretty-print security findings."""
    total = findings_data["total"]
    critical = findings_data["critical_count"]
    high = findings_data["high_count"]
    medium = findings_data["medium_count"]
    low = findings_data["low_count"]

    print(f"🔍 Findings Summary:")
    print(f"   • Total:    {total}")
    print(f"   • Critical: {critical} ⚠️")
    print(f"   • High:     {high} 🔴")
    print(f"   • Medium:   {medium} 🟠")
    print(f"   • Low:      {low} 🟡")

    if total == 0:
        print("\n✅ No findings detected!")
        return

    print(f"\n📋 Detailed Findings:")
    for i, finding in enumerate(findings_data["findings"], 1):
        severity_icon = {
            "CRITICAL": "⚠️",
            "HIGH": "🔴",
            "MEDIUM": "🟠",
            "LOW": "🟡",
        }.get(finding["severity"], "❓")

        print(f"\n   [{i}] {severity_icon} {finding['finding_type']}")
        print(f"       Resource: {finding['resource_id']} ({finding['resource_type']})")
        print(f"       Severity: {finding['severity']}")
        print(f"       Confidence: {finding['confidence_score']:.0%}")
        print(f"       Is New Exposure: {'Yes' if finding['is_new'] else 'No'}")
        print(f"       Explanation: {finding['explanation'][:100]}...")
        print(f"       Remediation: {finding['remediation'][:100]}...")


def main():
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 78 + "║")
    print("║" + "NetGuard: Graph Engine + Risk Scorer Demo".center(78) + "║")
    print("║" + " " * 78 + "║")
    print("╚" + "=" * 78 + "╝")
    print(f"\nDemo Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # ────────────────────────────────────────────────────────────────────────
    # STEP 1: Build Network Graph
    # ────────────────────────────────────────────────────────────────────────

    print_section("STEP 1: Building Network Topology Graph", "─")
    print("📌 Scenario: Public Web Server → Admin EC2 → Production Database")
    print("   This simulates a configuration where:")
    print("   • Web server is exposed to the internet (ports 80, 443)")
    print("   • Admin server has elevated privileges (AdminRole IAM)")
    print("   • Production database contains sensitive data")
    print()

    from services.graph_engine.models import Resource as GraphResource

    graph_resources = [GraphResource(**r) for r in DEMO_RESOURCES_GRAPH]
    graph = build_graph(graph_resources)
    graph_data = serialize_graph(graph)

    print_graph_info(graph_data)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 2: Create Graph Context
    # ────────────────────────────────────────────────────────────────────────

    print_section("STEP 2: Creating Graph Context", "─")
    print("Building network context for Risk Scorer...")

    graph_context = GraphContext(
        nodes=graph_data["nodes"],
        edges=graph_data["edges"],
        newly_exposed=["ec2-web", "ec2-admin"],  # Resources exposed in this scan
        exposure_delta=2,  # 2 new exposures
    )
    print(f"✅ Graph context created with {len(graph_context.nodes)} nodes")
    print(f"   Newly exposed resources: {graph_context.newly_exposed}")

    # ────────────────────────────────────────────────────────────────────────
    # STEP 3: Score Resources for Security Findings
    # ────────────────────────────────────────────────────────────────────────

    print_section("STEP 3: Scoring Resources for Security Findings", "─")
    print("Running security rules against resources with graph context...")
    print()

    client = TestClient(risk_scorer_app)
    response = client.post(
        "/score",
        json={
            "resources": [r.model_dump() for r in DEMO_RESOURCES_RISK],
            "graph_context": graph_context.model_dump(),
        },
    )

    if response.status_code != 200:
        print(f"❌ Error scoring resources: {response.status_code}")
        print(response.text)
        return

    findings_data = response.json()

    # ────────────────────────────────────────────────────────────────────────
    # STEP 4: Display Results
    # ────────────────────────────────────────────────────────────────────────

    print_section("STEP 4: Security Assessment Results", "─")
    print_findings(findings_data)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 5: Detailed Analysis
    # ────────────────────────────────────────────────────────────────────────

    print_section("STEP 5: Detailed Analysis", "─")
    if findings_data["total"] > 0:
        print("🔍 Key Insights:")
        
        # Check for critical findings
        critical_findings = [f for f in findings_data["findings"] if f["severity"] == "CRITICAL"]
        if critical_findings:
            print(f"\n   ⚠️  {len(critical_findings)} CRITICAL issue(s) detected:")
            for f in critical_findings:
                print(f"      • {f['finding_type']} on {f['resource_id']}")
        
        # Check for blast radius
        newly_exposed_with_findings = set(
            f["resource_id"] for f in findings_data["findings"] if f["is_new"]
        )
        if newly_exposed_with_findings:
            print(f"\n   🔗 Blast Radius: {len(newly_exposed_with_findings)} new exposures detected:")
            for resource_id in newly_exposed_with_findings:
                print(f"      • {resource_id}")

        # Severity distribution
        print(f"\n   📊 Severity Distribution:")
        total = findings_data["total"]
        crit_pct = (findings_data["critical_count"] / total * 100) if total > 0 else 0
        high_pct = (findings_data["high_count"] / total * 100) if total > 0 else 0
        med_pct = (findings_data["medium_count"] / total * 100) if total > 0 else 0
        low_pct = (findings_data["low_count"] / total * 100) if total > 0 else 0

        if crit_pct > 0:
            print(f"      • Critical: {crit_pct:.1f}% ⚠️")
        if high_pct > 0:
            print(f"      • High:     {high_pct:.1f}% 🔴")
        if med_pct > 0:
            print(f"      • Medium:   {med_pct:.1f}% 🟠")
        if low_pct > 0:
            print(f"      • Low:      {low_pct:.1f}% 🟡")

    else:
        print("✅ No security issues found - infrastructure is well-configured!")

    # ────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ────────────────────────────────────────────────────────────────────────

    print_section("Summary", "=")
    print("📈 Pipeline Execution Complete")
    print(f"\n   ✓ Resources Scanned: {len(DEMO_RESOURCES_RISK)}")
    print(f"   ✓ Graph Nodes: {graph_data['metadata']['node_count']}")
    print(f"   ✓ Graph Edges: {graph_data['metadata']['edge_count']}")
    print(f"   ✓ Security Findings: {findings_data['total']}")
    print(f"   ✓ Risk Score: {findings_data['critical_count']} critical, {findings_data['high_count']} high")
    print()


if __name__ == "__main__":
    main()
