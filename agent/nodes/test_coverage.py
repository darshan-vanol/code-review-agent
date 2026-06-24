from __future__ import annotations

from agent.nodes._llm_node import SYSTEM_INSTRUCTION, run_llm_findings
from agent.nodes.security_scan import _accumulate
from agent.prompts import load_prompt
from agent.providers.base import LLMProvider
from agent.state import ReviewState

_PROMPT = load_prompt("test_coverage")


def test_coverage_node(state: ReviewState, provider: LLMProvider) -> ReviewState:
    user = _PROMPT.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        provider, SYSTEM_INSTRUCTION, user, category="test"
    )
    state.test_suggestions = findings
    _accumulate(state, meta)
    return state


# Prevent pytest from treating this node function as a test.
test_coverage_node.__test__ = False  # type: ignore[attr-defined]
