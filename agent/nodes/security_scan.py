from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.prompts import load_prompt
from agent.state import ReviewState

_SYSTEM = load_prompt("security_scan")


def security_node(state: ReviewState) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        state._provider, _SYSTEM, user, category="security"
    )
    state.security_findings = findings
    _accumulate(state, meta)
    return state


def _accumulate(state: ReviewState, meta: dict) -> None:
    state.token_usage["input_tokens"] += meta["input_tokens"]
    state.token_usage["output_tokens"] += meta["output_tokens"]
    state.token_usage["latency_ms"] += meta["latency_ms"]
    if meta["error"]:
        state.errors.append(meta["error"])
