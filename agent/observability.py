from __future__ import annotations

import os
import time
from contextlib import contextmanager

from langfuse import get_client
from pydantic import BaseModel


class SpanRecord(BaseModel):
    name: str
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    # Model that produced this span, when it is an LLM call. None for plain
    # (non-generation) nodes. Carried through so Langfuse can populate the model
    # column and compute cost, and so the web UI can show it per node.
    model: str | None = None


class _SpanHandle:
    """Handed to a node while its observation is open so the node can attach the
    token usage and model it discovered during execution (both are only known
    after the LLM call returns)."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.model: str | None = None

    def set_usage(
        self, *, input_tokens: int, output_tokens: int, model: str | None = None
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.model = model


class NoOpTracer:
    """Tracer that does nothing. Default so the agent core never depends on
    observability being configured."""

    def begin_run(self, *, input=None) -> None:
        pass

    @contextmanager
    def observe(self, name: str, *, kind: str = "span"):
        yield _SpanHandle()

    def finish(self, *, score: float | None, output=None) -> None:
        pass

    @property
    def spans(self) -> list[SpanRecord]:
        return []


class RecordingTracer:
    """Collects spans in memory so the API can return them in the response."""

    def __init__(self) -> None:
        self._spans: list[SpanRecord] = []
        self._score: float | None = None

    def _record(self, name: str, latency_ms: float, handle: _SpanHandle) -> None:
        self._spans.append(
            SpanRecord(
                name=name,
                latency_ms=latency_ms,
                input_tokens=handle.input_tokens,
                output_tokens=handle.output_tokens,
                model=handle.model,
            )
        )

    def begin_run(self, *, input=None) -> None:
        pass

    @contextmanager
    def observe(self, name: str, *, kind: str = "span"):
        handle = _SpanHandle()
        start = time.perf_counter()
        try:
            yield handle
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record(name, latency_ms, handle)

    def finish(self, *, score: float | None, output=None) -> None:
        self._score = score

    @property
    def spans(self) -> list[SpanRecord]:
        return list(self._spans)


class LangfuseTracer(RecordingTracer):
    """Records spans in memory AND ships them to Langfuse as one nested trace.

    Best-practice instrumentation for the Langfuse v4 (OpenTelemetry) SDK:
      * A single root observation per review, so every node nests under one
        trace instead of appearing as fragmented top-level observations.
      * LLM nodes are emitted as `generation` observations carrying the model
        and `usage_details` — this is what lets the Langfuse dashboard populate
        the model column and compute token cost / latency metrics.
      * Non-LLM nodes are plain `span` observations.
      * The diff and final score are attached as trace-level input/output and a
        score, then buffered events are flushed before the request returns.
    """

    def __init__(self, *, trace_name: str = "code-review") -> None:
        super().__init__()
        self._lf = get_client()
        self._trace_name = trace_name
        self._root_cm = None

    def begin_run(self, *, input=None) -> None:
        # Root observation whose name becomes the trace name. Entered manually so
        # it stays the current OTEL context for the whole graph invocation; the
        # per-node observations opened in observe() nest under it automatically.
        self._root_cm = self._lf.start_as_current_observation(
            name=self._trace_name, as_type="chain", input=input
        )
        self._root_cm.__enter__()
        if input is not None:
            self._lf.set_current_trace_io(input=input)

    @contextmanager
    def observe(self, name: str, *, kind: str = "span"):
        handle = _SpanHandle()
        as_type = "generation" if kind == "generation" else "span"
        cm = self._lf.start_as_current_observation(name=name, as_type=as_type)
        cm.__enter__()
        start = time.perf_counter()
        try:
            yield handle
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            self._record(name, latency_ms, handle)
            if kind == "generation":
                # Set on the generation so Langfuse shows the model and derives cost.
                self._lf.update_current_generation(
                    model=handle.model,
                    usage_details={
                        "input": handle.input_tokens,
                        "output": handle.output_tokens,
                    },
                )
            cm.__exit__(None, None, None)

    def finish(self, *, score: float | None, output=None) -> None:
        super().finish(score=score)
        # These run while the root observation is still the current context, so
        # the trace output and score attach to this review's trace.
        if output is not None:
            self._lf.set_current_trace_io(output=output)
        if score is not None:
            self._lf.score_current_trace(name="overall", value=score)
        if self._root_cm is not None:
            self._root_cm.__exit__(None, None, None)
            self._root_cm = None
        self._lf.flush()


def make_tracer():
    """Return the configured tracer: Langfuse when enabled, else recording."""
    if os.environ.get("LANGFUSE_ENABLED", "").lower() in {"1", "true", "yes"}:
        return LangfuseTracer()
    return RecordingTracer()


def traced_node(tracer, name: str, fn, *, kind: str = "span"):
    """Wrap a node callable (state) -> state so each invocation opens one
    observation. LLM nodes (kind="generation") attach their model and the token
    delta they added to state.token_usage; plain nodes record latency only."""

    def wrapped(state):
        before_in = state.token_usage["input_tokens"]
        before_out = state.token_usage["output_tokens"]
        with tracer.observe(name, kind=kind) as handle:
            result = fn(state)
            handle.set_usage(
                input_tokens=int(result.token_usage["input_tokens"] - before_in),
                output_tokens=int(result.token_usage["output_tokens"] - before_out),
                model=result.model if kind == "generation" else None,
            )
        return result

    return wrapped
