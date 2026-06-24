from agent.state import Finding, ReviewScore, ReviewState, Severity


def test_finding_defaults_and_fields():
    f = Finding(
        file="app.py",
        line_start=10,
        line_end=12,
        severity=Severity.HIGH,
        category="security",
        message="SQL injection risk",
        suggestion="Use parameterized queries",
    )
    assert f.severity == Severity.HIGH
    assert f.line_end == 12


def test_review_score_rollup_counts():
    findings = [
        Finding(file="a", line_start=1, line_end=1, severity=Severity.HIGH,
                category="security", message="m", suggestion="s"),
        Finding(file="a", line_start=2, line_end=2, severity=Severity.LOW,
                category="logic", message="m", suggestion="s"),
    ]
    score = ReviewScore.from_findings(findings)
    assert score.counts["high"] == 1
    assert score.counts["low"] == 1
    assert 0.0 <= score.overall <= 1.0


def test_review_state_starts_empty():
    state = ReviewState(raw_diff="diff")
    assert state.files == []
    assert state.security_findings == []
    assert state.is_trivial is False
