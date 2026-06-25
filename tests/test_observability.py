from agent.observability import (
    NoOpTracer,
    RecordingTracer,
    SpanRecord,
    make_tracer,
    traced_node,
)
from agent.state import ReviewState


def test_recording_tracer_collects_spans():
    t = RecordingTracer()
    t.record_span(SpanRecord(name="a", latency_ms=1.0, input_tokens=2, output_tokens=3))
    t.finish(score=0.5)
    assert len(t.spans) == 1
    assert t.spans[0].name == "a"


def test_noop_tracer_records_nothing():
    t = NoOpTracer()
    t.record_span(SpanRecord(name="a", latency_ms=1.0))
    t.finish(score=None)
    assert t.spans == []


def test_traced_node_records_latency_and_token_delta():
    t = RecordingTracer()

    def fake_node(state: ReviewState) -> ReviewState:
        state.token_usage["input_tokens"] += 10
        state.token_usage["output_tokens"] += 4
        return state

    wrapped = traced_node(t, "security", fake_node)
    out = wrapped(ReviewState(raw_diff="d"))
    assert out.token_usage["input_tokens"] == 10
    assert len(t.spans) == 1
    span = t.spans[0]
    assert span.name == "security"
    assert span.input_tokens == 10
    assert span.output_tokens == 4
    assert span.latency_ms >= 0


def test_make_tracer_default_is_recording(monkeypatch):
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert isinstance(make_tracer(), RecordingTracer)
