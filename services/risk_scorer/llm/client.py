"""
LLM client for enriching findings with AI explanations.
- Supports Gemini, Groq, or OpenAI with structured JSON output
- If not set: returns mock enrichment so pipeline works without a key
"""

import json
import logging
import os
import re
from typing import Optional

import httpx

from ..schemas import Finding, Resource, GraphContext, Severity

from .prompt_builder import build_finding_prompt

logger = logging.getLogger(__name__)

# Severity ladder for +/-1 severity adjustments
_SEVERITY_LADDER = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def _resolve_api_key() -> str | None:
    for k in (os.getenv("GEMINI_API_KEY"), os.getenv("LLM_API_KEY")):
        if k and isinstance(k, str):
            ks = k.strip()
            if ks and ks != "your_api_key_here":
                return ks
    return None


def _gemini_model() -> str:
    return os.getenv("GEMINI_MODEL", "gemini-2.5-flash")


def _llm_provider() -> str:
    return os.getenv("LLM_PROVIDER", "gemini").strip().lower()


def _groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _resolve_groq_api_key() -> str | None:
    value = (os.getenv("GROQ_API_KEY") or "").strip()
    return value or None


def _openai_model() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


def _resolve_openai_api_key() -> str | None:
    value = (os.getenv("OPENAI_API_KEY") or "").strip()
    return value or None


def enrich_finding(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext] = None,
) -> Finding:
    """
    Enriches a rule-based finding with AI explanation.
    Automatically falls back to mock if no API key is set.
    """
    try:
        provider = _llm_provider()
        if provider == "groq":
            api_key = _resolve_groq_api_key()
            if not api_key:
                return _mock_enrich(finding, resource, graph_context)
            return _llm_enrich_groq(finding, resource, graph_context, api_key)
        if provider == "openai":
            gemini_key = _resolve_api_key()
            if gemini_key:
                return _llm_enrich_gemini(finding, resource, graph_context, gemini_key)
            api_key = _resolve_openai_api_key()
            if not api_key:
                return _mock_enrich(finding, resource, graph_context)
            return _llm_enrich_openai(finding, resource, graph_context, api_key)
        api_key = _resolve_api_key()
        if not api_key:
            return _mock_enrich(finding, resource, graph_context)
        return _llm_enrich_gemini(finding, resource, graph_context, api_key)
    except Exception as e:
        logger.warning("LLM call failed for %s: %s. Falling back to mock.", finding.finding_type, e)
        return _mock_enrich(finding, resource, graph_context)


def _extract_json(text: str) -> str:
    """Extract the first {...} JSON block from text.

    Gemini 2.5 Flash with thinking enabled can prepend reasoning text before the
    JSON payload even when response_mime_type='application/json' is set.  This
    helper strips any leading/trailing non-JSON content so json.loads succeeds.
    """
    text = text.strip()
    # Fast path: already valid JSON
    if text.startswith("{"):
        return text
    # Find first '{' ... last '}' block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text  # let json.loads raise its own error


def _llm_enrich_gemini(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext],
    api_key: str,
) -> Finding:
    """Gemini structured JSON enrichment when GEMINI_API_KEY is set."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    prompt = build_finding_prompt(finding, resource, graph_context)

    config = types.GenerateContentConfig(
        system_instruction=prompt["system"],
        temperature=0.2,
        max_output_tokens=1024,
        response_mime_type="application/json",
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    response = client.models.generate_content(
        model=_gemini_model(),
        contents=prompt["user"],
        config=config,
    )
    raw = response.text
    if raw is None:
        raise RuntimeError("Gemini returned no text")
    data = json.loads(_extract_json(raw))
    return _build_enriched_finding(finding, resource, graph_context, data)


def _llm_enrich_groq(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext],
    api_key: str,
) -> Finding:
    """Groq structured JSON enrichment when GROQ_API_KEY is set."""
    prompt = build_finding_prompt(finding, resource, graph_context)
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _groq_model(),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
    if not raw:
        raise RuntimeError("Groq returned no content")
    data = json.loads(raw)
    return _build_enriched_finding(finding, resource, graph_context, data)


def _llm_enrich_openai(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext],
    api_key: str,
) -> Finding:
    """OpenAI structured JSON enrichment when OPENAI_API_KEY is set."""
    prompt = build_finding_prompt(finding, resource, graph_context)
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _openai_model(),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
        },
        timeout=30.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
    if not raw:
        raise RuntimeError("OpenAI returned no content")
    data = json.loads(raw)
    return _build_enriched_finding(finding, resource, graph_context, data)


def _build_enriched_finding(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext],
    data: dict,
) -> Finding:

    adjusted_severity = _adjust_severity(
        finding.severity,
        data.get("confidence_adjustment", 0),
    )

    is_new = (
        resource.resource_id in graph_context.newly_exposed
        if graph_context else False
    )

    return Finding(
        resource_id=finding.resource_id,
        resource_type=finding.resource_type,
        finding_type=finding.finding_type,
        severity=adjusted_severity,
        explanation=data.get("explanation", finding.explanation),
        remediation=data.get("remediation", finding.remediation),
        confidence_score=_adjustment_to_confidence(data.get("confidence_adjustment", 0)),
        is_new=is_new,
        source_file=finding.source_file,
        source_line=finding.source_line,
    )


def _mock_enrich(
    finding: Finding,
    resource: Resource,
    graph_context: Optional[GraphContext] = None,
) -> Finding:
    """Mock enrichment when no API key is available."""
    is_new = (
        resource.resource_id in graph_context.newly_exposed
        if graph_context else False
    )
    return Finding(
        resource_id=finding.resource_id,
        resource_type=finding.resource_type,
        finding_type=finding.finding_type,
        severity=finding.severity,
        explanation=(
            finding.explanation
            + " [AI enrichment pending — set GEMINI_API_KEY, LLM_API_KEY, GROQ_API_KEY, or OPENAI_API_KEY per LLM_PROVIDER]"
        ),
        remediation=finding.remediation,
        confidence_score=0.90,
        is_new=is_new,
        source_file=finding.source_file,
        source_line=finding.source_line,
    )


def _adjust_severity(current: Severity, adjustment: int) -> Severity:
    """Shifts severity up or down by 1 step. Never goes above CRITICAL or below LOW."""
    if adjustment == 0:
        return current
    idx = _SEVERITY_LADDER.index(current)
    new_idx = max(0, min(len(_SEVERITY_LADDER) - 1, idx + adjustment))
    return _SEVERITY_LADDER[new_idx]


def _adjustment_to_confidence(adjustment: int) -> float:
    """Converts adjustment to a confidence score."""
    return {-1: 0.60, 0: 0.90, 1: 0.95}.get(adjustment, 0.90)
