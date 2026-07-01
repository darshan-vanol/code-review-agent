from evals.dataset import GoldenPR
from evals.harness import EvalRecord, build_records, serialize_findings
from agent.providers.mock import MockProvider

_DIFF = (
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
    "@@ -1 +1 @@\n-x = 1\n+y = run_security_check()\n"
)

_EXPECTED_FINDING = {
    "file": "app.py", "line_start": 1, "line_end": 1, "severity": "high",
    "category": "security", "message": "issue", "suggestion": "fix it",
}

_SCRIPTED = [{
    "file": "app.py", "line_start": 1, "line_end": 1, "severity": "high",
    "category": "security", "message": "SQLi", "suggestion": "parameterize",
}]


def test_serialize_findings_empty():
    assert serialize_findings([]) == "No issues found."


def test_serialize_findings_formats_each_line():
    text = serialize_findings([_EXPECTED_FINDING])
    assert "[high][security]" in text
    assert "app.py:1-1" in text
    assert "issue" in text


def test_build_records_shapes_one_record_per_golden():
    golden = GoldenPR(
        id="g1", language="python", category="security", diff=_DIFF,
        summary="expected verdict", findings=[_EXPECTED_FINDING],
    )
    provider = MockProvider(scripted={"security": _SCRIPTED})
    records = build_records([golden], provider)
    assert len(records) == 1
    r = records[0]
    assert isinstance(r, EvalRecord)
    assert r.id == "g1"
    assert r.user_input          # non-empty instruction
    assert "SQLi" in r.response  # agent's finding
    assert r.retrieved_contexts == [_DIFF]
    assert "expected verdict" in r.reference
    assert "issue" in r.reference


def test_build_records_carries_structured_findings():
    golden = GoldenPR(
        id="g1", language="python", category="security", diff=_DIFF,
        summary="expected verdict", findings=[_EXPECTED_FINDING],
    )
    provider = MockProvider(scripted={"security": _SCRIPTED})
    r = build_records([golden], provider)[0]
    # golden findings normalized to plain dicts with the 6 fields
    assert r.golden_findings == [{
        "file": "app.py", "line_start": 1, "line_end": 1,
        "severity": "high", "category": "security", "message": "issue",
    }]
    # agent findings normalized the same way (from the scripted security node)
    assert r.agent_findings[0]["file"] == "app.py"
    assert r.agent_findings[0]["category"] == "security"
    assert r.agent_findings[0]["message"] == "SQLi"
    assert r.agent_findings[0]["line_start"] == 1
