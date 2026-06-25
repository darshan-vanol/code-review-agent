from __future__ import annotations

import os
import time

from pydantic import BaseModel


class SpanRecord(BaseModel):
    name: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0


class NoOpTracer:
    """Tracer that does nothing. Default so the agent core never depends on
    observability being configured."""

    def record_span(self, record: SpanRecord) -> None:
        pass

    def finish(self, *, score: float | None) -> None:
        pass

    @property
    def spans(self) -> list[SpanRecord]:
        return []


class RecordingTracer:
    """Collects spans in memory so the API can return them in the response."""

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []
        self._score: float | None = None

    def record_span(self, record: SpanRecord) -> None:
        self._spans.append(record)

    def finish(self, *, score: float | None) -> None:
        self._score = score

    @property
    def spans(self) -> list[SpanRecord]:
        return list(self._spans)


class LangfuseTracer(RecordingTracer):
    """Records spans in memory AND ships them to Langfuse as one trace.

    Imports langfuse lazily so the package is only needed when enabled. The exact
    span/trace API is verified against the installed SDK during execution (see
    the build step); this class isolates that surface so the rest of the system
    is unaffected if the SDK call shape differs by version.
    """

    def __init__(self, *, trace_name: str = "code-review") -> None:
        super().__init__()
        from langfuse import Langfuse  # lazy import

        self._lf = Langfuse()
        self._trace_name = trace_name

    def record_span(self, record: SpanRecord) -> None:
        super().record_span(record)
        # langfuse v4.x: start_observation() replaces start_span().
        span = self._lf.start_observation(
            name=record.name,
            metadata={
                "latency_ms": record.latency_ms,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
            },
        )
        span.end()

    def finish(self, *, score: float | None) -> None:
        super().finish(score=score)
        if score is not None:
            # langfuse v4.x: create_score() replaces score().
            self._lf.create_score(name="overall", value=score)
        self._lf.flush()


def make_tracer():
    """Return the configured tracer: Langfuse when enabled, else recording."""
    if os.environ.get("LANGFUSE_ENABLED", "").lower() in {"1", "true", "yes"}:
        return LangfuseTracer()
    return RecordingTracer()


def traced_node(tracer, name: str, fn):
    """Wrap a node callable (state) -> state so each invocation emits a span with
    wall-clock latency and the token delta the node added to state.token_usage."""

    def wrapped(state):
        before_in = state.token_usage["input_tokens"]
        before_out = state.token_usage["output_tokens"]
        start = time.perf_counter()
        result = fn(state)
        latency_ms = (time.perf_counter() - start) * 1000
        tracer.record_span(
            SpanRecord(
                name=name,
                latency_ms=latency_ms,
                input_tokens=int(result.token_usage["input_tokens"] - before_in),
                output_tokens=int(result.token_usage["output_tokens"] - before_out),
            )
        )
        return result

    return wrapped
