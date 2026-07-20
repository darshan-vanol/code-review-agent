from pathlib import Path

from agent.graph import run_review
from agent.providers.mock import MockProvider

FIXTURES = Path(__file__).parent / "fixtures"

_SECURITY = [{
    "file": "app.py", "line_start": 6, "line_end": 6, "severity": "high",
    "category": "security", "message": "SQL injection", "suggestion": "parameterize",
}]


def test_run_review_full_path_produces_findings_and_score():
    diff = (FIXTURES / "simple_python.diff").read_text()
    provider = MockProvider(scripted={"security": _SECURITY})
    result = run_review(diff, provider)
    assert result.score is not None
    assert len(result.security_findings) == 1
    assert result.is_trivial is False
    assert result.token_usage["input_tokens"] > 0


def test_run_review_skips_analysis_on_trivial_diff():
    diff = (FIXTURES / "trivial_whitespace.diff").read_text()
    # Even though security is scripted, trivial diffs skip the analysis nodes.
    provider = MockProvider(scripted={"security": _SECURITY})
    result = run_review(diff, provider)
    assert result.is_trivial is True
    assert result.security_findings == []
    assert result.score.overall == 1.0


def test_run_review_analyzes_unparsed_raw_code():
    provider = MockProvider(scripted={"security": _SECURITY})
    result = run_review('def foo():\n    return eval(input())\n', provider)
    assert result.is_trivial is False
    assert len(result.security_findings) == 1
