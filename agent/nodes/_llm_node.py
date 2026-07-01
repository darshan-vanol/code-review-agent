from __future__ import annotations

import json

from pydantic import ValidationError

from agent.providers.base import LLMProvider
from agent.state import Finding

# One retry: an LLM occasionally returns prose or trailing commas. We re-ask once
# before degrading to an empty list so a single node never crashes the review.
_MAX_ATTEMPTS = 2

# Fixed system role. The per-node instruction template (which carries the diff)
# is sent as the user message, so the system prompt stays a clean, reusable role
# instruction rather than an unsubstituted template.
SYSTEM_INSTRUCTION = (
    "You are a senior code reviewer. Follow the instructions in the user message "
    "and respond ONLY with strict JSON in the requested schema — no prose, no markdown."
)


def _parse_findings(text: str, category: str) -> list[Finding]:
    data = json.loads(text)
    raw = data["findings"]
    findings = [Finding(**item) for item in raw]
    # Trust the node's category over whatever the model labelled.
    for f in findings:
        f.category = category
    return findings


def run_llm_findings(
    provider: LLMProvider, system: str, user: str, *, category: str
) -> tuple[list[Finding], dict]:
    """Call the provider, parse + validate findings, retry once on failure.

    Returns (findings, meta) where meta carries token/latency totals and an
    optional 'error' string when both attempts failed."""
    meta = {
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0.0,
        "model": None,
        "error": None,
    }
    last_error = None

    for _ in range(_MAX_ATTEMPTS):
        resp = provider.complete(system, user)
        meta["input_tokens"] += resp.input_tokens
        meta["output_tokens"] += resp.output_tokens
        meta["latency_ms"] += resp.latency_ms
        meta["model"] = resp.model
        try:
            return _parse_findings(resp.text, category), meta
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            last_error = e

    meta["error"] = f"failed to parse findings: {last_error}"
    return [], meta
