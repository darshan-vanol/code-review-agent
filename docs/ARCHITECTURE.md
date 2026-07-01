# System Architecture

This document describes how the Code Review Assistant is put together: the
runtime components, how the LangGraph review runs node-by-node, how each node is
traced into Langfuse, and how the offline evaluation harness scores the agent
against a golden dataset.

All diagrams are ASCII so they render anywhere (GitHub, editors, terminals).

---

## 1. Components at a glance

The system has three cooperating layers plus two cross-cutting concerns
(observability and evaluation). The **agent core** (`agent/`) has no web
dependency — the API and the eval harness are just two different callers of the
same `run_review()` function.

```
                          ┌───────────────────────────────────────────┐
                          │              web/  (Vite + React)          │
                          │  • Review Playground  (paste diff / PR URL) │
                          │  • Eval Analytics     (score trends)        │
                          └───────────────┬─────────────────────────────┘
                                          │ HTTP (JSON / NDJSON stream)
                                          │ dev: Vite proxy → :8000
                                          ▼
                          ┌─────────────────────────────────────────────┐
                          │              api/  (FastAPI)                  │
                          │  GET  /health   /version                     │
                          │  POST /review   /review/stream               │
                          │  GET  /eval/reports  /eval/reports/{id}       │
                          │  • _resolve_diff(): PR URL → unified diff     │
                          │    (api/github.py fetches the PR)             │
                          └───────────────┬─────────────────────────────┘
                                          │ run_review(diff, provider, tracer)
                                          ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │                    agent/  (LangGraph core)                          │
        │                                                                      │
        │   graph.py  ── builds + compiles the StateGraph, one span per node   │
        │   state.py  ── ReviewState (pydantic), Finding, ReviewScore          │
        │   nodes/    ── ingest · security · logic · test_coverage · aggregate │
        │   prompts/  ── per-node instruction templates (*.txt)                │
        │                                                                      │
        │   providers/ (swappable LLM adapters, chosen by $LLM_PROVIDER)       │
        │     ┌─────────┐   ┌─────────┐   ┌──────────┐                         │
        │     │  mock   │   │  groq   │   │  gemini  │  ← base.LLMProvider      │
        │     └─────────┘   └─────────┘   └──────────┘    (Protocol)           │
        └───────────────┬──────────────────────────────────┬───────────────────┘
                        │ observe() per node                │ same run_review()
                        ▼                                    ▼
        ┌───────────────────────────────┐     ┌──────────────────────────────┐
        │  observability.py (tracing)   │     │      evals/  (harness)        │
        │  • NoOpTracer                 │     │  • golden PRs (diff+expected) │
        │  • RecordingTracer (in-mem)   │     │  • build_records → run_review │
        │  • LangfuseTracer  ───────────┼──▶  │  • detection / RAGAS scorer   │
        │      one trace / review       │ Langfuse   • gate at 0.75          │
        └───────────────────────────────┘ cloud └──────────────────────────────┘
```

**Provider selection.** `agent/providers/factory.py:make_provider()` reads
`$LLM_PROVIDER` (default `mock`) and returns the matching adapter. All adapters
satisfy the `LLMProvider` Protocol in `agent/providers/base.py`
(`.model` + `.complete(system, user) -> LLMResponse`), so the graph never knows
which model it is talking to. The default `mock` provider runs fully offline and
returns deterministic, empty findings — enough to exercise the API, routing, and
tracing without any keys.

---

## 2. The review graph (node sequence)

`agent/graph.py:build_graph()` wires a LangGraph `StateGraph` over a single
mutable `ReviewState`. Each node takes the whole state and returns the whole
state; LangGraph reconstructs the state between nodes, so the LLM provider is
bound into each node with `functools.partial` rather than travelling on the
state.

There is exactly one branch: after `ingest`, trivial diffs (whitespace- or
docs-only, decided by `agent/diff_parser.py:is_trivial`) skip the three LLM
nodes and go straight to `aggregate` — so a no-op PR costs zero tokens.

```
   raw_diff
      │
      ▼
 ┌──────────┐   span      parse_diff() → files[]; is_trivial flag
 │  ingest  │             (deterministic, no LLM)
 └────┬─────┘
      │
      │  _route_after_ingest(state)
      │
      ├───────────────── is_trivial == True ──────────────────────┐
      │                                                           │
      │  is_trivial == False                                      │
      ▼                                                           │
 ┌──────────┐   generation   prompt: prompts/security_scan.txt    │
 │ security │   ───────────▶  provider.complete() → JSON findings  │
 └────┬─────┘                 → state.security_findings            │
      ▼                                                           │
 ┌──────────┐   generation   prompt: prompts/logic_analysis.txt    │
 │  logic   │   ───────────▶  → state.logic_findings               │
 └────┬─────┘                                                     │
      ▼                                                           │
 ┌───────────────┐ generation prompt: prompts/test_coverage.txt    │
 │ test_coverage │ ─────────▶ → state.test_suggestions             │
 └────┬──────────┘                                                │
      │                                                           │
      ▼                                                           ▼
 ┌───────────┐   span      ReviewScore.from_findings(all findings)
 │ aggregate │◀────────────  → state.score  (0..1 cleanliness gauge)
 └────┬──────┘
      ▼
     END  →  ReviewState { findings, score, token_usage, errors, spans }
```

### What flows on the state

`agent/state.py:ReviewState` is the single object every node reads and writes:

| Field                | Written by       | Meaning                                             |
| -------------------- | ---------------- | --------------------------------------------------- |
| `raw_diff`           | caller           | the unified diff under review                       |
| `files`, `is_trivial`| `ingest`         | parsed per-file diffs + the skip decision           |
| `security_findings`  | `security`       | list of `Finding`                                   |
| `logic_findings`     | `logic`          | list of `Finding`                                   |
| `test_suggestions`   | `test_coverage`  | list of `Finding`                                   |
| `model`              | LLM nodes        | model name, so tracing can label generation spans   |
| `token_usage`        | LLM nodes        | running `{input_tokens, output_tokens, latency_ms}` |
| `score`              | `aggregate`      | `ReviewScore{overall, counts}`                      |
| `errors`             | any LLM node     | parse failures that were degraded, not raised       |

### LLM node contract (resilience)

Every LLM node routes through `agent/nodes/_llm_node.py:run_llm_findings()`,
which sends a fixed system role + the per-node instruction (carrying the diff),
then parses strict-JSON findings. It **retries once** on malformed output and,
if the second attempt still fails, records an `error` on the state and returns
an empty finding list. A single bad model response therefore never crashes the
review — it degrades to "no findings from this node".

### Scoring

`ReviewScore.from_findings` turns severity counts into a single `overall`
0..1 **cleanliness gauge**: `1.0` is clean and it saturates at `0.0` once the
severity-weighted penalty reaches `1.0`. Per-severity detail is preserved in
`counts` for callers that need to tell "bad" from "very bad".

### Streaming

`stream_review()` runs the same compiled graph via `compiled.stream(...)` and
yields `("progress", node_name)` as each node finishes, then a final
`("result", ReviewState)`. `POST /review/stream` serialises those as
newline-delimited JSON so the dashboard can show live per-stage progress.

---

## 3. Observability — one Langfuse trace per review

Tracing is a cross-cutting wrapper, not a node. `build_graph()` wraps every node
with `observability.py:traced_node(...)`, which opens one observation around the
node call and attaches the token delta that node added to `state.token_usage`
(and, for LLM nodes, the model name).

Three tracer implementations share one interface (`begin_run` / `observe` /
`finish` / `spans`), selected by `make_tracer()`:

- **`NoOpTracer`** — the agent-core default; does nothing.
- **`RecordingTracer`** — buffers `SpanRecord`s in memory so the API can return
  them inline under `spans` in the `/review` response.
- **`LangfuseTracer`** — extends the recording tracer *and* ships to Langfuse.

`make_tracer()` returns the `LangfuseTracer` when `LANGFUSE_ENABLED` is truthy,
otherwise the `RecordingTracer`. So spans are **always** available in the API
response; Langfuse is purely additive.

```
 run_review(diff, provider, tracer)
        │
        │  tracer.begin_run(input=diff)
        ▼
  ┌───────────────────────────────────────────────────────────┐
  │  LangfuseTracer: start_as_current_observation("code-review")│  ◀── ROOT (chain)
  │                                                             │
  │   traced_node wraps each graph node:                        │
  │                                                             │
  │   with tracer.observe("ingest", kind="span"):        ───────┼──▶ span
  │   with tracer.observe("security", kind="generation"):───────┼──▶ generation
  │        └─ update_current_generation(model, usage_details)   │      (model +
  │   with tracer.observe("logic", kind="generation"): ─────────┼──▶   input/output
  │   with tracer.observe("test_coverage", kind="generation"):──┼──▶   tokens)
  │   with tracer.observe("aggregate", kind="span"): ───────────┼──▶ span
  │                                                             │
  │  tracer.finish(score, output):                              │
  │    set_current_trace_io(output=...)                         │
  │    score_current_trace(name="overall", value=score)  ───────┼──▶ trace score
  │    flush()                                                  │
  └───────────────────────────────────────────────────────────┘
                              │
                              ▼
                   Langfuse (nested trace:
                   1 chain → 5 child observations,
                   token cost + latency per generation)
```

Key detail: LLM nodes are emitted as **`generation`** observations carrying the
`model` and `usage_details` — that is what lets the Langfuse dashboard populate
the model column and compute token cost / latency. The deterministic
`ingest`/`aggregate` nodes are plain **`span`** observations. Everything nests
under one root observation so a review is a single readable trace, not five
fragmented top-level events.

**Config:** set `LANGFUSE_ENABLED=true`, `LANGFUSE_PUBLIC_KEY`,
`LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` (EU `https://cloud.langfuse.com`,
US `https://us.cloud.langfuse.com`).

---

## 4. Evaluation harness

The harness answers "is the agent actually good?" offline and repeatably. It
reuses the exact same `run_review()` the API calls, so what you evaluate is what
you ship.

### Golden dataset

`evals/golden/` holds 20 hand-authored cases (`security`, `logic`, and
`test-coverage` categories across Python / JS / Go). Each case is a pair:

- `NN-name.diff` — the pull-request diff to review.
- `NN-name.expected.json` — the golden `findings` (file, line range, severity,
  category, message) plus a `summary`.

`evals/dataset.py:load_golden()` loads every diff that has a sibling
`.expected.json`.

### Flow

```
 evals/golden/*.diff + *.expected.json
        │
        ▼
 load_golden() ──▶ [GoldenPR, …]
        │
        ▼
 build_records(goldens, provider)          evals/harness.py
   for each golden PR:
     run_review(diff, provider)  ◀── the real agent graph
     collect agent findings + golden findings
        │
        ▼
 [EvalRecord, …]  (agent_findings vs golden_findings, normalized)
        │
        ▼
 scorer(records)                            ← pluggable
   ├─ detection_scorer  (DEFAULT)  ──┐
   └─ ragas_scorer      (optional)   │
        │                            │
        ▼                            │
 aggregate_scores() ──▶ render_report(threshold=0.75)
        │
        ▼
 evals/reports/NNN.json  +  NNN.md         (zero-padded; CI reads the latest .md)
        │
        ▼
 exit 0 if passed else 1                    ← CI gate + PR comment
```

### The two scorers

**Detection scorer (`evals/detection_scorer.py`) — current default.**
For each golden finding it looks for an agent finding that matches
*deterministically*: same file, **overlapping** line range, same category. Any
golden not matched deterministically gets one **LLM "rescue"** attempt (a Groq
adjudicator asked "does any candidate describe the same underlying bug?"; any
error or unparseable reply is treated as no-match — fail-safe). Per case:

```
 recall        = matched_goldens / total_goldens
 fp_rate       = false_positives / total_agent_findings
 score         = clamp(recall − 0.2 · fp_rate)     # PRECISION_PENALTY = 0.2
```

The build is gated on the **aggregate `score` ≥ 0.75** (`evals/scoring.py`);
`recall` is reported alongside but not gated. Disable the LLM rescue with
`EVAL_LLM_FALLBACK=0` for a purely deterministic run.

**RAGAS scorer (`evals/ragas_scorer.py`) — optional alternative.**
Scores each record with RAGAS **faithfulness** + **answer correctness**, using a
Groq judge LLM (`RAGAS_JUDGE_MODEL`, default `llama-3.3-70b-versatile`) and local
`fastembed` embeddings. It is not wired into `run_eval` by default; the
detection scorer is preferred because it is deterministic (no judge variance) on
the parts that matter and far cheaper on tokens.

### Running it

```bash
# default detection scorer (needs GROQ_API_KEY for the agent + LLM rescue)
export LLM_PROVIDER=groq GROQ_API_KEY=...
uv run python -m evals.run_eval --provider groq

# purely deterministic (no LLM rescue)
EVAL_LLM_FALLBACK=0 uv run python -m evals.run_eval --provider groq
```

Reports land in `evals/reports/` and are also served to the dashboard via
`GET /eval/reports`.

---

## 5. CI pipeline

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

```
 push / PR
    │
    ├─▶ job: test   ── ruff check .  →  pytest -q   (LLM_PROVIDER=mock, offline, no keys)
    │
    └─▶ job: eval   ── needs: test
                       python -m evals.run_eval --provider groq   (secret: GROQ_API_KEY)
                       │
                       ├─ exit 1 if aggregate score < 0.75  →  fails the build
                       ├─ upload evals/reports/ as an artifact  (always)
                       └─ comment the latest report .md on the PR  (PRs only)
```

The `test` job is hermetic (mock provider, no network). The `eval` job needs the
`GROQ_API_KEY` repository secret because both the agent and the detection
scorer's rescue step call a real model.

---

## 6. Request lifecycle (end to end)

```
 client ──POST /review {diff | pr_url}──▶ api/main.py
    │
    │  _resolve_diff():  pr_url? → api/github.py fetch → prepend PR title/body
    │                    (diff --git lines stripped from prose)
    ▼
 make_provider()  +  make_tracer()
    ▼
 run_review(diff, provider, tracer)
    │   ingest → [security → logic → test_coverage]? → aggregate
    │   (each node wrapped in tracer.observe; token usage accumulated)
    ▼
 ReviewResponse { is_trivial, score, *_findings, token_usage, spans, errors }
    │
    └─▶ client   (+ one Langfuse trace, if LANGFUSE_ENABLED)
```

See `README.md` for setup and the exact commands.
