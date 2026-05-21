"""Prompts for IaC autofix proposals (Gemini structured JSON output)."""

import json


FIX_SYSTEM_PROMPT = """You are an expert IaC security fixer for Terraform (.tf) and Kubernetes (.yaml/.yml).
You MUST reply with a valid JSON object only—no markdown fences, no prose outside JSON.

The JSON MUST match exactly this schema:
{
  "fix_format": "edits" | "none",
  "edits": [{"path": "relative/path.tf", "search": "exact substring to replace once", "replace": "replacement"}],
  "unified_diff": null,
  "rationale": "one short paragraph",
  "confidence": 0.0,
  "requires_human_review": true
}

Rules:
- Prefer "fix_format":"edits" with small localized search/replace edits anchored with enough unique context around each targeted block.
- The "path" must match one of the file paths supplied in the prompt.
- If you cannot propose a safe fix, set fix_format to "none" and edits to [].
- Never widen network exposure (e.g. do not add 0.0.0.0/0), never remove encryption, never grant cluster-admin unless the finding explicitly requires restricting that exact permission.
- Never invent fake identifiers (example account IDs like 123456789012, placeholder KMS keys, dummy ARNs, or synthetic UUIDs). Only use values already present in the provided file.
- Terraform must stay syntactically valid after edits: maintain balanced braces; never strip required attributes inside ingress/egress blocks (especially from_port/to_port). To fix ALL_PORTS_OPEN, narrow the overly wide rule to specific numeric ports rather than deleting block fields.
- For MISSING_TAGS, merge tags into existing tags blocks rather than inserting multiple tags arguments per resource; use environment, owner, and project keys (values may reference Terraform variables already defined in file such as var.environment — do not omit closing braces.)
"""


def build_fix_prompt(
    finding_type: str,
    severity: str,
    explanation: str,
    remediation: str,
    source_file: str | None,
    file_content_snippet: str | None,
    validation_feedback: str | None = None,
) -> dict[str, str]:
    snippet = file_content_snippet or "(content unavailable — return fix_format:none)"
    feedback_section = ""
    if validation_feedback and validation_feedback.strip():
        feedback_section = (
            "\n## Validation feedback from a failed attempt — address this precisely\n"
            f"{validation_feedback.strip()}\n"
        )

    user = f"""## Finding
- Type: {finding_type}
- Severity: {severity}
- Source file: {source_file or "unknown"}

## Rule explanations
{finding_type}: {explanation}

## Recommended remediation (from deterministic rules)
{remediation}
{feedback_section}
## File content (truncate if very long; apply edits to this file only)
Path: {source_file or "unknown"}
```
{snippet[:12000]}
```

Respond with the JSON object only.
"""
    return {"system": FIX_SYSTEM_PROMPT, "user": user}
