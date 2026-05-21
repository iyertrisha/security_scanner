"""
Prompt builder for GPT-4o LLM calls.
Constructs system + user prompts for each security finding.
No API key needed here — this just builds strings.
"""
import json
from typing import Optional
from ..schemas import Finding, Resource, GraphContext


SYSTEM_PROMPT = """You are a senior cloud security engineer specializing in Infrastructure-as-Code security analysis. You review security findings in Terraform and Kubernetes configurations and provide clear, actionable guidance.

You will be given a security finding detected by a rule-based scanner. Your job is to enrich it with deeper context.

You MUST respond with a valid JSON object and nothing else. No markdown, no explanation outside the JSON. The JSON must have exactly these fields:

{
  "explanation": "Clear 2-3 sentence explanation of why this is dangerous",
  "blast_radius": "Plain English description of what could be compromised if exploited",
  "remediation": "Specific, actionable fix with example config if possible",
  "confidence_adjustment": 0
}

confidence_adjustment must be one of: -1, 0, or 1
  -1 = rule overfired, actual risk is lower than stated severity
   0 = rule severity is accurate
   1 = risk is worse than the rule suggests given the context
"""


def build_finding_prompt(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext] = None,
) -> dict:
    """
    Builds the full prompt dict for a single finding.
    Returns {"system": str, "user": str} ready to send to GPT-4o.
    """
    # Build graph context section
    graph_section = _build_graph_section(resource, graph_context)

    user_prompt = f"""Analyze this security finding:

## Finding
- Type: {finding.finding_type}
- Severity: {finding.severity.value}
- Resource ID: {resource.resource_id}
- Resource Type: {resource.resource_type}
- Provider: {resource.provider}

## Resource Configuration
```json
{json.dumps(_safe_resource_props(resource), indent=2)}
```

## Rule-Based Detection
{finding.explanation}

{graph_section}

Provide your analysis as a JSON object with the fields: explanation, blast_radius, remediation, confidence_adjustment."""

    return {
        "system": SYSTEM_PROMPT,
        "user": user_prompt,
    }


def _build_graph_section(
    resource: Resource,
    graph_context: Optional[GraphContext],
) -> str:
    """Builds the graph context section of the prompt if available."""
    if not graph_context:
        return "## Graph Context\nNo graph context available."

    lines = ["## Graph Context"]

    # Is this resource newly exposed in this PR?
    if resource.resource_id in graph_context.newly_exposed:
        lines.append(
            f"⚠️  This resource is NEWLY INTERNET-FACING in this PR "
            f"(exposure delta: +{graph_context.exposure_delta})"
        )

    # Find connected resources from edges
    connected = []
    for edge in graph_context.edges:
        if edge.get("source") == resource.resource_id:
            connected.append(
                f"  → {edge.get('target')} "
                f"(relationship: {edge.get('relationship', 'unknown')}, "
                f"exposure: {edge.get('exposure_type', 'unknown')})"
            )
        elif edge.get("target") == resource.resource_id:
            connected.append(
                f"  ← {edge.get('source')} "
                f"(relationship: {edge.get('relationship', 'unknown')}, "
                f"exposure: {edge.get('exposure_type', 'unknown')})"
            )

    if connected:
        lines.append(f"Connected resources ({len(connected)}):")
        lines.extend(connected)
    else:
        lines.append("No connected resources found in graph.")

    return "\n".join(lines)


def _safe_resource_props(resource: Resource) -> dict:
    """
    Returns a safe subset of resource properties for the prompt.
    Excludes anything that looks like a secret or key.
    """
    sensitive_keywords = {"password", "secret", "key", "token", "credential"}

    safe_props = {}
    for k, v in resource.properties.items():
        if any(kw in k.lower() for kw in sensitive_keywords):
            safe_props[k] = "[REDACTED]"
        else:
            safe_props[k] = v

    return {
        "resource_id": resource.resource_id,
        "resource_type": resource.resource_type,
        "provider": resource.provider,
        "inbound_rules": [r.model_dump() for r in resource.inbound_rules],
        "outbound_rules": [r.model_dump() for r in resource.outbound_rules],
        "properties": safe_props,
        "tags": resource.tags,
    }
