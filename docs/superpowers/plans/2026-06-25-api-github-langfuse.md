# API + GitHub + Langfuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the agent-core review graph as a traced FastAPI service that accepts either a raw diff or a GitHub PR URL, behind real (offline-testable) LLM provider adapters, with per-node Langfuse observability.

**Architecture:** A thin `api/` FastAPI layer wraps `agent.graph.run_review`. Real provider adapters (Groq, Gemini) implement the existing `LLMProvider` protocol and are selected by env var, defaulting to the deterministic `MockProvider` so everything runs offline. A small `Tracer` abstraction records one span per graph node (latency + token delta); `RecordingTracer` always returns spans in the API response, and `LangfuseTracer` additionally ships them to Langfuse when enabled. A `github` module turns a PR URL into a unified diff.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx (with `httpx.MockTransport` for offline tests of HTTP code), Langfuse SDK, pytest, ruff. Builds on the existing `agent/` package.

## Global Constraints

- Python `>=3.11`; manage deps + run via `uv` (`uv add ...`, `uv run ...`).
- ruff line-length 100; keep the tree `uv run ruff check .`-clean before every commit.
- All LLM access goes through `agent.providers.base.LLMProvider` (`complete(system, user) -> LLMResponse`). Never call an SDK directly from a node or the API.
- Everything must run offline with **no API keys**: default provider is `mock`, and all HTTP code is tested with `httpx.MockTransport` (no network in tests).
- Reuse existing agent-core types verbatim — do not redefine `Finding`, `ReviewScore`, `ReviewState`, `LLMResponse`.
- Follow TDD: failing test → confirm fail → implement → confirm pass → commit.

### Agent-core interfaces this plan consumes (authoritative)

```python
# agent/providers/base.py
@dataclass
class LLMResponse:
    text: str; input_tokens: int; output_tokens: int; latency_ms: float; model: str

@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, system: str, user: str) -> LLMResponse: ...

# agent/providers/mock.py
class MockProvider:  # MockProvider(scripted: dict[str, list[dict]] | None = None)
    def complete(self, system, user) -> LLMResponse: ...

# agent/state.py
class Finding(BaseModel):  # file, line_start, line_end, severity, category, message, suggestion
class ReviewScore(BaseModel):  # overall: float, counts: dict[str, int]
class ReviewState(BaseModel):
    raw_diff: str; files: list[FileDiff]; is_trivial: bool
    security_findings: list[Finding]; logic_findings: list[Finding]; test_suggestions: list[Finding]
    score: ReviewScore | None; errors: list[str]
    token_usage: dict[str, float]  # {"input_tokens","output_tokens","latency_ms"}

# agent/graph.py  (signatures CHANGE in Task 2 to add an optional tracer)
def build_graph(provider: LLMProvider): ...            # -> compiled graph
def run_review(diff: str, provider: LLMProvider) -> ReviewState: ...
```

---

## File Structure

```
agent/
├── providers/
│   ├── groq.py            # GroqProvider (httpx, OpenAI-compatible endpoint)
│   ├── gemini.py          # GeminiProvider (httpx, Google generateContent)
│   └── factory.py         # make_provider(name|env) -> LLMProvider
├── observability.py       # SpanRecord, NoOpTracer, RecordingTracer, LangfuseTracer,
│                          # make_tracer(), traced_node()
└── graph.py               # MODIFIED: build_graph/run_review take optional tracer

api/
├── __init__.py
├── main.py                # FastAPI app: /review, /health, /version
├── schemas.py             # ReviewRequest, ReviewResponse, SpanOut
└── github.py              # parse_pr_url(), fetch_pull_request() -> PullRequest

tests/
├── test_provider_groq.py
├── test_provider_gemini.py
├── test_provider_factory.py
├── test_observability.py
├── test_graph_tracing.py
├── test_github.py
└── test_api.py

.env.example               # documents env vars
README.md                  # MODIFIED/created: run + API + observability docs
```

---

## Task 1: Real provider adapters + factory

**Files:**
- Create: `agent/providers/groq.py`
- Create: `agent/providers/gemini.py`
- Create: `agent/providers/factory.py`
- Test: `tests/test_provider_groq.py`, `tests/test_provider_gemini.py`, `tests/test_provider_factory.py`

**Interfaces:**
- Consumes: `LLMResponse`, `LLMProvider` (base), `MockProvider`.
- Produces:
  - `GroqProvider(api_key: str | None = None, model: str = "llama-3.3-70b-versatile", client: httpx.Client | None = None)` with `.complete(system, user) -> LLMResponse`.
  - `GeminiProvider(api_key: str | None = None, model: str = "gemini-2.0-flash", client: httpx.Client | None = None)` with `.complete(...) -> LLMResponse`.
  - `make_provider(name: str | None = None) -> LLMProvider` — resolves `name` or `$LLM_PROVIDER` (default `"mock"`); supports `mock|groq|gemini`; raises `ValueError` on unknown.

- [ ] **Step 1: Add httpx dependency**

Run: `uv add httpx`
Expected: httpx added to `pyproject.toml` dependencies and installed.

- [ ] **Step 2: Write the failing test for GroqProvider**

`tests/test_provider_groq.py`:
```python
import json

import httpx

from agent.providers.base import LLMProvider, LLMResponse
from agent.providers.groq import GroqProvider


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"findings": []}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_groq_is_an_llm_provider():
    assert isinstance(GroqProvider(api_key="k", client=httpx.Client()), LLMProvider)


def test_groq_complete_parses_content_and_usage():
    captured: dict = {}
    p = GroqProvider(api_key="secret", client=_mock_client(captured))
    r = p.complete("system text", "user text")
    assert isinstance(r, LLMResponse)
    assert r.text == '{"findings": []}'
    assert r.input_tokens == 12
    assert r.output_tokens == 5
    assert r.latency_ms >= 0
    # request was well-formed
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["content"] == "user text"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_provider_groq.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.providers.groq'`.

- [ ] **Step 4: Implement GroqProvider**

`agent/providers/groq.py`:
```python
from __future__ import annotations

import os
import time

import httpx

from agent.providers.base import LLMResponse

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_S = 60.0


class GroqProvider:
    """LLMProvider backed by Groq's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self._model = model
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)

    def complete(self, system: str, user: str) -> LLMResponse:
        start = time.perf_counter()
        resp = self._client.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            model=self._model,
        )
```

- [ ] **Step 5: Run Groq test to verify it passes**

Run: `uv run pytest tests/test_provider_groq.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Write the failing test for GeminiProvider**

`tests/test_provider_gemini.py`:
```python
import httpx

from agent.providers.base import LLMResponse
from agent.providers.gemini import GeminiProvider


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"findings": []}'}]}}
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 7},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_complete_parses_content_and_usage():
    captured: dict = {}
    p = GeminiProvider(api_key="secret", client=_mock_client(captured))
    r = p.complete("system text", "user text")
    assert isinstance(r, LLMResponse)
    assert r.text == '{"findings": []}'
    assert r.input_tokens == 20
    assert r.output_tokens == 7
    # key is passed as a query param, not a header
    assert "key=secret" in captured["url"]
```

- [ ] **Step 7: Run test to verify it fails**

Run: `uv run pytest tests/test_provider_gemini.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.providers.gemini'`.

- [ ] **Step 8: Implement GeminiProvider**

`agent/providers/gemini.py`:
```python
from __future__ import annotations

import os
import time

import httpx

from agent.providers.base import LLMResponse

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"
_TIMEOUT_S = 60.0


class GeminiProvider:
    """LLMProvider backed by Google's Gemini generateContent REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)

    def complete(self, system: str, user: str) -> LLMResponse:
        start = time.perf_counter()
        url = f"{_BASE}/{self._model}:generateContent?key={self._api_key}"
        resp = self._client.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000
        usage = data.get("usageMetadata", {})
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            latency_ms=latency_ms,
            model=self._model,
        )
```

- [ ] **Step 9: Run Gemini test to verify it passes**

Run: `uv run pytest tests/test_provider_gemini.py -v`
Expected: PASS (1 passed).

- [ ] **Step 10: Write the failing test for the factory**

`tests/test_provider_factory.py`:
```python
import pytest

from agent.providers.factory import make_provider
from agent.providers.gemini import GeminiProvider
from agent.providers.groq import GroqProvider
from agent.providers.mock import MockProvider


def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(make_provider(), MockProvider)


def test_factory_explicit_names():
    assert isinstance(make_provider("groq"), GroqProvider)
    assert isinstance(make_provider("gemini"), GeminiProvider)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert isinstance(make_provider(), GroqProvider)


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        make_provider("nope")
```

- [ ] **Step 11: Run test to verify it fails**

Run: `uv run pytest tests/test_provider_factory.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.providers.factory'`.

- [ ] **Step 12: Implement the factory**

`agent/providers/factory.py`:
```python
from __future__ import annotations

import os

from agent.providers.base import LLMProvider
from agent.providers.gemini import GeminiProvider
from agent.providers.groq import GroqProvider
from agent.providers.mock import MockProvider


def make_provider(name: str | None = None) -> LLMProvider:
    """Build an LLMProvider by name, falling back to $LLM_PROVIDER then "mock".

    Real providers read their own key from the environment (GROQ_API_KEY /
    GEMINI_API_KEY); the mock needs nothing, so the system runs offline by
    default."""
    name = (name or os.environ.get("LLM_PROVIDER", "mock")).lower()
    if name == "mock":
        return MockProvider()
    if name == "groq":
        return GroqProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider {name!r}; expected mock|groq|gemini")
```

- [ ] **Step 13: Run factory test + full suite + lint**

Run: `uv run pytest tests/test_provider_factory.py -v && uv run pytest -q && uv run ruff check .`
Expected: factory tests PASS; full suite PASS; ruff clean.

- [ ] **Step 14: Commit**

```bash
git add agent/providers/groq.py agent/providers/gemini.py agent/providers/factory.py tests/test_provider_groq.py tests/test_provider_gemini.py tests/test_provider_factory.py pyproject.toml uv.lock
git commit -m "feat: add Groq + Gemini provider adapters and provider factory"
```

---

## Task 2: Observability layer + graph tracing

**Files:**
- Create: `agent/observability.py`
- Modify: `agent/graph.py` (add optional `tracer` to `build_graph` and `run_review`)
- Test: `tests/test_observability.py`, `tests/test_graph_tracing.py`

**Interfaces:**
- Consumes: `ReviewState`, existing node functions, `partial`-bound provider.
- Produces:
  - `SpanRecord(name: str, latency_ms: float, input_tokens: int = 0, output_tokens: int = 0)` — a pydantic model.
  - `NoOpTracer()`, `RecordingTracer()`, `LangfuseTracer()` — all expose `record_span(SpanRecord) -> None`, `finish(*, score: float | None) -> None`, and a `spans` property returning `list[SpanRecord]`.
  - `make_tracer() -> Tracer` — returns `LangfuseTracer` when `$LANGFUSE_ENABLED` is truthy, else `RecordingTracer`.
  - `traced_node(tracer, name: str, fn)` — wraps a node callable `(state) -> state`, timing it and recording a `SpanRecord` with the per-node token delta.
  - `build_graph(provider, tracer=None)` and `run_review(diff, provider, tracer=None) -> ReviewState` (tracer defaults to `NoOpTracer`).

- [ ] **Step 1: Write the failing test for the tracers + traced_node**

`tests/test_observability.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_observability.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.observability'`.

- [ ] **Step 3: Implement the observability layer**

`agent/observability.py`:
```python
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

    def record_span(self, record: SpanRecord) -> None:  # noqa: D102
        pass

    def finish(self, *, score: float | None) -> None:  # noqa: D102
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
        self._lf.start_span(
            name=record.name,
            metadata={
                "latency_ms": record.latency_ms,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
            },
        ).end()

    def finish(self, *, score: float | None) -> None:
        super().finish(score=score)
        if score is not None:
            self._lf.score(name="overall", value=score)
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
```

- [ ] **Step 4: Run observability test to verify it passes**

Run: `uv run pytest tests/test_observability.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Write the failing test for graph tracing**

`tests/test_graph_tracing.py`:
```python
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `uv run pytest tests/test_graph_tracing.py -v`
Expected: FAIL — `run_review()` takes 2 positional args (no `tracer`), so a `TypeError` is raised.

- [ ] **Step 7: Modify `agent/graph.py` to thread the tracer through**

Replace the entire contents of `agent/graph.py` with:
```python
from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from agent.nodes.aggregate import aggregate_node
from agent.nodes.ingest import ingest_node
from agent.nodes.logic_analysis import logic_node
from agent.nodes.security_scan import security_node
from agent.nodes.test_coverage import test_coverage_node
from agent.observability import NoOpTracer, traced_node
from agent.providers.base import LLMProvider
from agent.state import ReviewState


def _route_after_ingest(state: ReviewState) -> str:
    # Trivial diffs (whitespace/docs only) skip straight to aggregation.
    return "aggregate" if state.is_trivial else "security"


def build_graph(provider: LLMProvider, tracer=None):
    """Build and compile the review StateGraph.

    The provider is bound into each LLM node with functools.partial (LangGraph
    reconstructs the state between nodes, so it cannot travel on the state).
    Each node is wrapped with traced_node so the tracer gets one span per node.
    """
    tracer = tracer or NoOpTracer()
    g = StateGraph(ReviewState)
    g.add_node("ingest", traced_node(tracer, "ingest", ingest_node))
    g.add_node("security", traced_node(tracer, "security", partial(security_node, provider=provider)))
    g.add_node("logic", traced_node(tracer, "logic", partial(logic_node, provider=provider)))
    g.add_node("test_coverage", traced_node(tracer, "test_coverage", partial(test_coverage_node, provider=provider)))
    g.add_node("aggregate", traced_node(tracer, "aggregate", aggregate_node))

    g.set_entry_point("ingest")
    g.add_conditional_edges(
        "ingest", _route_after_ingest,
        {"security": "security", "aggregate": "aggregate"},
    )
    g.add_edge("security", "logic")
    g.add_edge("logic", "test_coverage")
    g.add_edge("test_coverage", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


def run_review(diff: str, provider: LLMProvider, tracer=None) -> ReviewState:
    """Run the full review graph over a unified diff and return the final state.

    An optional tracer receives one span per node and a final score."""
    tracer = tracer or NoOpTracer()
    compiled = build_graph(provider, tracer)
    result = compiled.invoke(ReviewState(raw_diff=diff))
    final = ReviewState(
        **{k: v for k, v in dict(result).items() if k in ReviewState.model_fields}
    )
    tracer.finish(score=final.score.overall if final.score else None)
    return final
```

- [ ] **Step 8: Run graph-tracing test + full suite**

Run: `uv run pytest tests/test_graph_tracing.py -v && uv run pytest -q`
Expected: graph-tracing PASS (2 passed); full suite PASS (existing `tests/test_graph.py` still green because `tracer` is optional).

- [ ] **Step 9: Add langfuse dependency and verify the SDK span API**

Run: `uv add langfuse && uv run python -c "import langfuse, inspect; lf=langfuse.Langfuse; print('langfuse', langfuse.__version__); print('has start_span:', hasattr(lf, 'start_span')); print('has score:', hasattr(lf, 'score'))"`
Expected: prints the installed langfuse version and whether `start_span`/`score` exist.

> If `start_span` or `score` is reported as `False`, the installed SDK uses a
> different surface. Adjust `LangfuseTracer.record_span` / `finish` to the
> installed version's documented API (e.g. v2 uses `self._lf.trace(...)` then
> `trace.span(...)`; some versions use `start_as_current_span` context managers).
> The `RecordingTracer` contract and all tracing tests stay unchanged — only the
> Langfuse-specific calls inside `LangfuseTracer` change. Re-run step 8 to confirm
> nothing else regressed.

- [ ] **Step 10: Commit**

```bash
git add agent/observability.py agent/graph.py tests/test_observability.py tests/test_graph_tracing.py pyproject.toml uv.lock
git commit -m "feat: add tracer abstraction and per-node graph observability"
```

---

## Task 3: GitHub PR-URL → diff fetcher

**Files:**
- Create: `api/__init__.py` (empty)
- Create: `api/github.py`
- Test: `tests/test_github.py`

**Interfaces:**
- Consumes: nothing from agent-core; httpx.
- Produces:
  - `parse_pr_url(url: str) -> tuple[str, str, int]` — returns `(owner, repo, number)` for `https://github.com/<owner>/<repo>/pull/<n>` or the shorthand `<owner>/<repo>#<n>`. Raises `ValueError` on anything else.
  - `PullRequest` dataclass: `title: str`, `body: str`, `diff: str`.
  - `fetch_pull_request(url: str, token: str | None = None, client: httpx.Client | None = None) -> PullRequest` — fetches PR metadata (JSON) and the unified diff. Raises `GitHubError` (subclass of `RuntimeError`) on non-200.

- [ ] **Step 1: Write the failing test**

`tests/test_github.py`:
```python
import httpx
import pytest

from api.github import GitHubError, PullRequest, fetch_pull_request, parse_pr_url


def test_parse_full_url():
    assert parse_pr_url("https://github.com/octocat/hello/pull/42") == ("octocat", "hello", 42)


def test_parse_shorthand():
    assert parse_pr_url("octocat/hello#42") == ("octocat", "hello", 42)


def test_parse_invalid_raises():
    with pytest.raises(ValueError):
        parse_pr_url("not a pr url")


def _client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        accept = request.headers.get("accept", "")
        if "diff" in accept:
            return httpx.Response(200, text="diff --git a/x.py b/x.py\n@@ -1 +1 @@\n-a\n+b\n")
        return httpx.Response(200, json={"title": "Add feature", "body": "Why this PR"})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_pull_request_returns_title_body_and_diff():
    pr = fetch_pull_request("https://github.com/octocat/hello/pull/42", client=_client())
    assert isinstance(pr, PullRequest)
    assert pr.title == "Add feature"
    assert pr.body == "Why this PR"
    assert "diff --git a/x.py" in pr.diff


def test_fetch_pull_request_raises_on_404():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "Not Found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(GitHubError):
        fetch_pull_request("https://github.com/octocat/hello/pull/42", client=client)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_github.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api'` / `api.github`.

- [ ] **Step 3: Implement the fetcher**

`api/__init__.py`: empty file.

`api/github.py`:
```python
from __future__ import annotations

import re
from dataclasses import dataclass

import httpx

_API = "https://api.github.com"
_TIMEOUT_S = 30.0
_FULL_URL = re.compile(r"github\.com/([^/]+)/([^/]+)/pull/(\d+)")
_SHORTHAND = re.compile(r"^([^/]+)/([^/#]+)#(\d+)$")


class GitHubError(RuntimeError):
    """Raised when the GitHub API returns a non-success response."""


@dataclass
class PullRequest:
    title: str
    body: str
    diff: str


def parse_pr_url(url: str) -> tuple[str, str, int]:
    m = _FULL_URL.search(url) or _SHORTHAND.match(url.strip())
    if not m:
        raise ValueError(f"Not a GitHub PR URL or owner/repo#n shorthand: {url!r}")
    return m.group(1), m.group(2), int(m.group(3))


def _headers(token: str | None, accept: str) -> dict[str, str]:
    headers = {"Accept": accept, "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_pull_request(
    url: str, token: str | None = None, client: httpx.Client | None = None
) -> PullRequest:
    owner, repo, number = parse_pr_url(url)
    client = client or httpx.Client(timeout=_TIMEOUT_S)
    endpoint = f"{_API}/repos/{owner}/{repo}/pulls/{number}"

    meta = client.get(endpoint, headers=_headers(token, "application/vnd.github+json"))
    if meta.status_code != 200:
        raise GitHubError(f"GitHub metadata fetch failed ({meta.status_code}) for {url}")

    diff = client.get(endpoint, headers=_headers(token, "application/vnd.github.v3.diff"))
    if diff.status_code != 200:
        raise GitHubError(f"GitHub diff fetch failed ({diff.status_code}) for {url}")

    payload = meta.json()
    return PullRequest(
        title=payload.get("title") or "",
        body=payload.get("body") or "",
        diff=diff.text,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_github.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add api/__init__.py api/github.py tests/test_github.py
git commit -m "feat: add GitHub PR-URL to unified-diff fetcher"
```

---

## Task 4: FastAPI app

**Files:**
- Create: `api/schemas.py`
- Create: `api/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `run_review`, `make_provider`, `make_tracer`, `fetch_pull_request`, `parse_pr_url`, `GitHubError`, `SpanRecord`, `Finding`, `ReviewScore`.
- Produces: a FastAPI `app` with `POST /review`, `GET /health`, `GET /version`.

- [ ] **Step 1: Add FastAPI dependencies**

Run: `uv add fastapi "uvicorn[standard]"`
Expected: fastapi + uvicorn installed.

> Note: `fastapi.testclient.TestClient` requires `httpx`, which is already a
> runtime dependency from Task 1 — no extra install needed.

- [ ] **Step 2: Write the failing test**

`tests/test_api.py`:
```python
from fastapi.testclient import TestClient

import api.main as main
from api.github import PullRequest
from api.main import app

client = TestClient(app)

_DIFF = (
    "diff --git a/app.py b/app.py\n"
    "--- a/app.py\n+++ b/app.py\n"
    "@@ -1 +1 @@\n-x = 1\n+y = eval(input())\n"
)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_version_reports_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    r = client.get("/version")
    assert r.status_code == 200
    assert r.json()["provider"] == "mock"


def test_review_with_raw_diff_returns_findings_score_and_spans():
    r = client.post("/review", json={"diff": _DIFF})
    assert r.status_code == 200
    body = r.json()
    assert body["is_trivial"] is False
    assert "overall" in body["score"]
    assert isinstance(body["security_findings"], list)
    assert [s["name"] for s in body["spans"]] == [
        "ingest", "security", "logic", "test_coverage", "aggregate"
    ]
    assert "input_tokens" in body["token_usage"]


def test_review_requires_exactly_one_of_diff_or_pr_url():
    assert client.post("/review", json={}).status_code == 422
    assert client.post(
        "/review", json={"diff": "d", "pr_url": "x"}
    ).status_code == 422


def test_review_with_pr_url_fetches_diff(monkeypatch):
    def fake_fetch(url, token=None):
        return PullRequest(title="T", body="B", diff=_DIFF)

    monkeypatch.setattr(main, "fetch_pull_request", fake_fetch)
    r = client.post("/review", json={"pr_url": "https://github.com/o/r/pull/1"})
    assert r.status_code == 200
    assert r.json()["is_trivial"] is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.main'` / `api.schemas`.

- [ ] **Step 4: Implement the schemas**

`api/schemas.py`:
```python
from __future__ import annotations

from pydantic import BaseModel, model_validator

from agent.observability import SpanRecord
from agent.state import Finding, ReviewScore


class ReviewRequest(BaseModel):
    diff: str | None = None
    pr_url: str | None = None

    @model_validator(mode="after")
    def exactly_one_input(self) -> "ReviewRequest":
        if bool(self.diff) == bool(self.pr_url):
            raise ValueError("Provide exactly one of 'diff' or 'pr_url'.")
        return self


class ReviewResponse(BaseModel):
    is_trivial: bool
    score: ReviewScore | None
    security_findings: list[Finding]
    logic_findings: list[Finding]
    test_suggestions: list[Finding]
    token_usage: dict[str, float]
    spans: list[SpanRecord]
    errors: list[str]
```

- [ ] **Step 5: Implement the app**

`api/main.py`:
```python
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException

from agent.graph import run_review
from agent.observability import make_tracer
from agent.providers.factory import make_provider
from api.github import GitHubError, fetch_pull_request
from api.schemas import ReviewRequest, ReviewResponse

app = FastAPI(title="Code Review Assistant", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict[str, str]:
    return {
        "version": app.version,
        "provider": os.environ.get("LLM_PROVIDER", "mock").lower(),
        "langfuse_enabled": os.environ.get("LANGFUSE_ENABLED", "").lower()
        in {"1", "true", "yes"},
    }


@app.post("/review", response_model=ReviewResponse)
def review(req: ReviewRequest) -> ReviewResponse:
    if req.pr_url:
        try:
            pr = fetch_pull_request(req.pr_url, token=os.environ.get("GITHUB_TOKEN"))
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
        except GitHubError as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        # Prepend PR title/body as context; the diff parser ignores non-diff prose.
        diff = f"PR: {pr.title}\n\n{pr.body}\n\n{pr.diff}"
    else:
        diff = req.diff or ""

    tracer = make_tracer()
    result = run_review(diff, make_provider(), tracer)
    return ReviewResponse(
        is_trivial=result.is_trivial,
        score=result.score,
        security_findings=result.security_findings,
        logic_findings=result.logic_findings,
        test_suggestions=result.test_suggestions,
        token_usage=result.token_usage,
        spans=tracer.spans,
        errors=result.errors,
    )
```

> Note: the test monkeypatches `api.main.fetch_pull_request`, so the handler must
> call the name imported into `api.main` (it does). The `version` endpoint returns
> a bool for `langfuse_enabled`; FastAPI serializes the mixed dict fine.

- [ ] **Step 6: Run API test + full suite + lint**

Run: `uv run pytest tests/test_api.py -v && uv run pytest -q && uv run ruff check .`
Expected: API tests PASS (5 passed); full suite PASS; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add api/schemas.py api/main.py tests/test_api.py pyproject.toml uv.lock
git commit -m "feat: add FastAPI /review (diff or PR URL), /health, /version"
```

---

## Task 5: Env docs, README, and manual smoke

**Files:**
- Create: `.env.example`
- Create/Modify: `README.md`

**Interfaces:** none (documentation + manual verification).

- [ ] **Step 1: Create `.env.example`**

`.env.example`:
```bash
# LLM provider selection: mock (default, offline) | groq | gemini
LLM_PROVIDER=mock

# Provider API keys (only needed when LLM_PROVIDER is not 'mock')
GROQ_API_KEY=
GEMINI_API_KEY=

# GitHub token: optional; enables private repos + higher rate limits
GITHUB_TOKEN=

# Observability: set to 'true' to ship traces to Langfuse
LANGFUSE_ENABLED=false
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com
```

- [ ] **Step 2: Create/extend `README.md`**

Write `README.md` with these sections (use real, runnable commands):
````markdown
# Code Review Assistant

An observable, multi-step AI code-review agent built on LangGraph, served over
FastAPI, with provider-agnostic LLM adapters and per-node Langfuse tracing.

> **Stack note:** the assignment names NestJS; this is built in Python/FastAPI
> because the LangGraph + RAGAS ecosystem is first-class there. The agent core
> (`agent/`) has no web dependency, so the same graph could be wrapped by a
> NestJS controller unchanged.

## Quickstart (offline, no keys)

```bash
uv venv && uv pip install -e ".[dev]"
uv run uvicorn api.main:app --reload
# then in another shell:
curl -s localhost:8000/health
curl -s -X POST localhost:8000/review \
  -H 'content-type: application/json' \
  -d '{"diff": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x=1\n+y=eval(input())\n"}'
```

With `LLM_PROVIDER=mock` (the default) the agent runs fully offline and returns
deterministic, empty findings — enough to demo the API, tracing, and routing.

## Using a real model

```bash
cp .env.example .env        # then fill in one key
export LLM_PROVIDER=groq GROQ_API_KEY=...   # or gemini / GEMINI_API_KEY
uv run uvicorn api.main:app
```

## Reviewing a real PR

```bash
curl -s -X POST localhost:8000/review \
  -H 'content-type: application/json' \
  -d '{"pr_url": "https://github.com/<owner>/<repo>/pull/<n>"}'
```

Set `GITHUB_TOKEN` for private repos / higher rate limits.

## Observability

Set `LANGFUSE_ENABLED=true` plus `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`
to ship one trace per review, with a span per node (latency + token counts) and
an overall score. When disabled, spans are still returned inline in the
`/review` response under `spans`.

## Tests

```bash
uv run pytest -q
uv run ruff check .
```
````

- [ ] **Step 3: Manual smoke — boot the server and hit it**

Run (in background, then curl, then stop):
```bash
uv run uvicorn api.main:app --port 8000 &
sleep 2
curl -s localhost:8000/health
curl -s localhost:8000/version
curl -s -X POST localhost:8000/review -H 'content-type: application/json' -d '{"diff": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x=1\n+y=eval(input())\n"}'
kill %1
```
Expected: `/health` → `{"status":"ok"}`; `/version` → provider `mock`; `/review` → JSON with `is_trivial`, `score`, finding arrays, `token_usage`, and 5 `spans`.

- [ ] **Step 4: Commit**

```bash
git add .env.example README.md
git commit -m "docs: add .env.example and README with run/API/observability docs"
```

---

## Self-review notes (spec coverage)

- Spec §2 adapter layer → Task 1 (Groq + Gemini + factory, mock default, offline-tested).
- Spec §3 FastAPI `/review` + thin API → Task 4; data flow (diff or pr_url) → Tasks 3 + 4.
- Spec §5 Langfuse per-node spans + token/latency + toggle → Task 2 (`LangfuseTracer`, `make_tracer`, `traced_node`); mock still produces spans (latency real, tokens 0 on non-LLM nodes, >0 on analysis nodes).
- Spec §5b GitHub PR-URL fetch (full URL + shorthand, optional token, title/body context, error handling) → Task 3 + Task 4 error mapping.
- Out of scope (unchanged): webhook/App auto-comment bot; RAGAS eval + CI (Plan 3); dashboard (Plan 4).

## Done criteria

- `uv run pytest -q` fully green (agent-core + provider + observability + github + api tests).
- `uv run ruff check .` clean.
- `uvicorn api.main:app` boots; `/review` returns findings, score, token usage, and one span per executed node, offline with the mock provider.
- Swapping `LLM_PROVIDER=groq` (with a key) routes through the real adapter with no code change.
