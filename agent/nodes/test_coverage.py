from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.nodes.security_scan import _accumulate
from agent.prompts import load_prompt
from agent.state import ReviewState

_SYSTEM = load_prompt("test_coverage")


def test_coverage_node(state: ReviewState) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        state._provider, _SYSTEM, user, category="test"
    )
    state.test_suggestions = findings
    _accumulate(state, meta)
    return state


# Prevent pytest from treating this node function as a test.
test_coverage_node.__test__ = False  # type: ignore[attr-defined]
