from __future__ import annotations

import agent.observability as obs
from agent.observability import (
    NoOpTracer,
    RecordingTracer,
    SpanRecord,
    make_tracer,
    traced_node,
)
from agent.providers.mock import MockProvider
from agent.state import ReviewState


def test_span_record_defaults_model_to_none():
    rec = SpanRecord(name="a", latency_ms=1.0)
    assert rec.model is None


def test_recording_tracer_observe_records_span_with_usage_and_model():
    t = RecordingTracer()
    with t.observe("security", kind="generation") as handle:
        handle.set_usage(input_tokens=10, output_tokens=4, model="mock-1")
    assert len(t.spans) == 1
    span = t.spans[0]
    assert span.name == "security"
    assert span.input_tokens == 10
    assert span.output_tokens == 4
    assert span.model == "mock-1"
    assert span.latency_ms >= 0


def test_noop_tracer_observe_records_nothing():
    t = NoOpTracer()
    with t.observe("a", kind="span") as handle:
        handle.set_usage(input_tokens=5, output_tokens=1, model="x")
    t.finish(score=None)
    assert t.spans == []


def test_traced_node_generation_captures_model_and_token_delta():
    t = RecordingTracer()

    def fake_llm_node(state: ReviewState) -> ReviewState:
        state.token_usage["input_tokens"] += 10
        state.token_usage["output_tokens"] += 4
        state.model = "mock-1"
        return state

    wrapped = traced_node(t, "security", fake_llm_node, kind="generation")
    wrapped(ReviewState(raw_diff="d"))

    span = t.spans[0]
    assert span.name == "security"
    assert span.input_tokens == 10
    assert span.output_tokens == 4
    assert span.model == "mock-1"


def test_traced_node_plain_span_leaves_model_none():
    t = RecordingTracer()

    def fake_plain_node(state: ReviewState) -> ReviewState:
        return state

    wrapped = traced_node(t, "ingest", fake_plain_node, kind="span")
    wrapped(ReviewState(raw_diff="d"))

    span = t.spans[0]
    assert span.name == "ingest"
    assert span.model is None


def test_make_tracer_default_is_recording(monkeypatch):
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    assert isinstance(make_tracer(), RecordingTracer)


def test_run_review_propagates_model_onto_generation_spans():
    from agent.graph import run_review

    diff = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n+++ b/app.py\n"
        "@@ -1,2 +1,3 @@\n import os\n+password = 'hunter2'\n"
    )
    tracer = RecordingTracer()
    run_review(diff, MockProvider(), tracer)

    by_name = {s.name: s for s in tracer.spans}
    # LLM nodes are generations and must carry the model for the dashboard.
    for node in ("security", "logic", "test_coverage"):
        assert by_name[node].model == "mock-1", f"{node} missing model"
    # Non-LLM nodes are plain spans with no model.
    assert by_name["ingest"].model is None
    assert by_name["aggregate"].model is None


# ---- LangfuseTracer: verify the exact SDK calls that make the dashboard work ----


class _FakeObservationCM:
    def __init__(self, recorder, name, as_type):
        self._recorder = recorder
        self._name = name
        self._as_type = as_type

    def __enter__(self):
        self._recorder.observations.append({"name": self._name, "as_type": self._as_type})
        return self

    def __exit__(self, *exc):
        return False


class _FakeLangfuse:
    def __init__(self):
        self.observations: list[dict] = []
        self.generation_updates: list[dict] = []
        self.trace_io: dict = {}
        self.scores: list[dict] = []
        self.flushed = 0

    def start_as_current_observation(self, *, name, as_type="span", input=None, **_):
        return _FakeObservationCM(self, name, as_type)

    def update_current_generation(self, **kwargs):
        self.generation_updates.append(kwargs)

    def update_current_span(self, **kwargs):
        pass

    def set_current_trace_io(self, *, input=None, output=None):
        if input is not None:
            self.trace_io["input"] = input
        if output is not None:
            self.trace_io["output"] = output

    def score_current_trace(self, *, name, value, **_):
        self.scores.append({"name": name, "value": value})

    def flush(self):
        self.flushed += 1


def _langfuse_tracer_with_fake(monkeypatch):
    fake = _FakeLangfuse()
    monkeypatch.setattr(obs, "get_client", lambda: fake, raising=False)
    tracer = obs.LangfuseTracer(trace_name="code-review")
    return tracer, fake


def test_langfuse_tracer_emits_generation_with_model_and_usage(monkeypatch):
    tracer, fake = _langfuse_tracer_with_fake(monkeypatch)
    tracer.begin_run(input="the diff")
    with tracer.observe("security", kind="generation") as handle:
        handle.set_usage(input_tokens=12, output_tokens=5, model="mock-1")
    tracer.finish(score=0.75, output={"score": 0.75})

    # A generation observation was opened for the LLM node.
    assert {"name": "security", "as_type": "generation"} in fake.observations
    # Model + token usage were set so Langfuse can show the model and compute cost.
    assert fake.generation_updates == [
        {"model": "mock-1", "usage_details": {"input": 12, "output": 5}}
    ]


def test_langfuse_tracer_sets_trace_io_score_and_flushes(monkeypatch):
    tracer, fake = _langfuse_tracer_with_fake(monkeypatch)
    tracer.begin_run(input="the diff")
    tracer.finish(score=0.75, output={"score": 0.75})

    # Root observation carries the trace name.
    assert fake.observations[0]["name"] == "code-review"
    assert fake.trace_io == {"input": "the diff", "output": {"score": 0.75}}
    assert fake.scores == [{"name": "overall", "value": 0.75}]
    assert fake.flushed == 1


def test_langfuse_tracer_plain_span_has_no_generation_update(monkeypatch):
    tracer, fake = _langfuse_tracer_with_fake(monkeypatch)
    tracer.begin_run(input="d")
    with tracer.observe("ingest", kind="span") as handle:
        handle.set_usage(input_tokens=0, output_tokens=0, model=None)
    tracer.finish(score=None)

    assert {"name": "ingest", "as_type": "span"} in fake.observations
    assert fake.generation_updates == []
