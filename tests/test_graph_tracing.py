from pathlib import Path

from agent.graph import run_review
from agent.observability import RecordingTracer
from agent.providers.mock import MockProvider

FIXTURES = Path(__file__).parent / "fixtures"

_SECURITY = [{
    "file": "app.py", "line_start": 6, "line_end": 6, "severity": "high",
    "category": "security", "message": "SQL injection", "suggestion": "parameterize",
}]


def test_run_review_emits_a_span_per_node():
    diff = (FIXTURES / "simple_python.diff").read_text()
    tracer = RecordingTracer()
    run_review(diff, MockProvider(scripted={"security": _SECURITY}), tracer)
    names = [s.name for s in tracer.spans]
    assert names == ["ingest", "security", "logic", "test_coverage", "aggregate"]
    security_span = next(s for s in tracer.spans if s.name == "security")
    assert security_span.input_tokens > 0


def test_trivial_diff_only_traces_ingest_and_aggregate():
    diff = (FIXTURES / "trivial_whitespace.diff").read_text()
    tracer = RecordingTracer()
    run_review(diff, MockProvider(), tracer)
    assert [s.name for s in tracer.spans] == ["ingest", "aggregate"]
