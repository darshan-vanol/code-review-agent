from __future__ import annotations

from agent.state import ReviewScore, ReviewState


def aggregate_node(state: ReviewState) -> ReviewState:
    all_findings = (
        state.security_findings + state.logic_findings + state.test_suggestions
    )
    state.score = ReviewScore.from_findings(all_findings)
    return state
