from agent.nodes.aggregate import aggregate_node
from agent.state import Finding, ReviewState, Severity


def _finding(sev):
    return Finding(file="a", line_start=1, line_end=1, severity=sev,
                   category="x", message="m", suggestion="s")


def test_aggregate_computes_score_from_all_findings():
    state = ReviewState(raw_diff="d")
    state.security_findings = [_finding(Severity.HIGH)]
    state.logic_findings = [_finding(Severity.LOW)]
    state.test_suggestions = []
    out = aggregate_node(state)
    assert out.score is not None
    assert out.score.counts["high"] == 1
    assert out.score.counts["low"] == 1
    assert out.score.overall < 1.0


def test_aggregate_clean_diff_scores_one():
    state = ReviewState(raw_diff="d")
    out = aggregate_node(state)
    assert out.score.overall == 1.0
