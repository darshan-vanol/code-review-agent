from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.nodes.security_scan import _accumulate
from agent.prompts import load_prompt
from agent.providers.base import LLMProvider
from agent.state import ReviewState

_SYSTEM = load_prompt("logic_analysis")


def logic_node(state: ReviewState, provider: LLMProvider) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        provider, _SYSTEM, user, category="logic"
    )
    state.logic_findings = findings
    _accumulate(state, meta)
    return state
