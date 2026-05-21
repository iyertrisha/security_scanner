"""Generate structured autofix proposals via Gemini, Groq, or OpenAI."""

import json
import logging
import os
import re
from typing import Any, Optional

import httpx
from google import genai
from google.genai import types

from .fix_prompt import build_fix_prompt

logger = logging.getLogger(__name__)


def _stub_fix_payload(reason: str) -> dict[str, Any]:
    """Deterministic fallback payload when Gemini cannot return edits."""
    return {
        "fix_format": "none",
        "edits": [],
        "unified_diff": None,
        "rationale": reason,
        "confidence": 0.0,
        "requires_human_review": True,
        "stub": True,
    }


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


def propose_fix_json(
    finding_type: str,
    severity: str,
    explanation: str,
    remediation: str,
    source_file: Optional[str],
    file_snippet: Optional[str],
    validation_feedback: Optional[str] = None,
) -> dict[str, Any]:
    """
    Calls configured LLM provider with JSON output and returns parsed dict.

    Fallback when no API key: returns deterministic no-fix payload.
    """
    prompt = build_fix_prompt(
        finding_type,
        severity,
        explanation,
        remediation,
        source_file,
        file_snippet,
        validation_feedback=validation_feedback,
    )
    try:
        provider = _llm_provider()
        if provider == "groq":
            api_key = _resolve_groq_api_key()
            if not api_key:
                logger.info("GROQ_API_KEY unset — autofix propose returns stub")
                return _stub_fix_payload("Set GROQ_API_KEY to generate AI-fix proposals.")
            return _propose_fix_groq(prompt, api_key)
        if provider == "openai":
            gemini_key = _resolve_api_key()
            if gemini_key:
                logger.info(
                    "LLM_PROVIDER=openai but GEMINI_API_KEY is set — using Gemini for autofix"
                )
                return _propose_fix_gemini(prompt, gemini_key)
            api_key = _resolve_openai_api_key()
            if not api_key:
                logger.info("OPENAI_API_KEY unset — autofix propose returns stub")
                return _stub_fix_payload("Set OPENAI_API_KEY to generate AI-fix proposals.")
            return _propose_fix_openai(prompt, api_key)
        api_key = _resolve_api_key()
        if not api_key:
            logger.info("GEMINI_API_KEY unset — autofix propose returns stub")
            return _stub_fix_payload("Set GEMINI_API_KEY to generate AI-fix proposals.")
        return _propose_fix_gemini(prompt, api_key)
    except Exception as exc:
        logger.warning("LLM autofix generation failed: %s", exc)
        return _stub_fix_payload(
            f"LLM autofix unavailable right now ({type(exc).__name__}); check provider key/quota/billing and retry."
        )


def _extract_json(text: str) -> str:
    """Extract the first {...} JSON block from text (handles Gemini 2.5 thinking preamble)."""
    text = text.strip()
    if text.startswith("{"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return text


def _propose_fix_gemini(prompt: dict[str, str], api_key: str) -> dict[str, Any]:
    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=prompt["system"],
        temperature=0.1,
        max_output_tokens=4096,
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
    return json.loads(_extract_json(raw))


def _propose_fix_groq(prompt: dict[str, str], api_key: str) -> dict[str, Any]:
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _groq_model(),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
        },
        timeout=40.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
    if not raw:
        raise RuntimeError("Groq returned no content")
    return json.loads(raw)


def _propose_fix_openai(prompt: dict[str, str], api_key: str) -> dict[str, Any]:
    response = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": _openai_model(),
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
        },
        timeout=40.0,
    )
    response.raise_for_status()
    payload = response.json()
    raw = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content"))
    if not raw:
        raise RuntimeError("OpenAI returned no content")
    return json.loads(raw)
