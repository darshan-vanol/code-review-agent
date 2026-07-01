# Code Review Assistant

An observable, multi-step AI code-review agent built on **LangGraph**, served
over **FastAPI**, with provider-agnostic LLM adapters and per-node **Langfuse**
tracing — plus an offline **evaluation harness** that scores the agent against a
golden dataset and gates CI.

> **Stack note:** the assignment names NestJS; this is built in Python/FastAPI
> because the LangGraph + RAGAS ecosystem is first-class there. The agent core
> (`agent/`) has no web dependency, so the same graph could be wrapped by a
> NestJS controller unchanged.

The two things this project is really about:

1. **Evaluating the harness** — a golden dataset + a detection scorer that tells
   you, repeatably and offline, whether the agent actually finds the bugs it
   should. This gates every PR in CI. → [jump to Evaluation](#evaluating-the-agent)
2. **Tracing with Langfuse** — one clean trace per review, a span per graph node
   with model + token + latency, and an overall score. → [jump to Observability](#observability-with-langfuse)

For the full design — component diagram, node sequence, tracing internals, and
the eval flow, all in ASCII — see **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## Getting started locally

### Prerequisites

- Python **3.11+**
- [`uv`](https://docs.astral.sh/uv/) (used for env + dependency management)
- Node 18+ **only** if you want to run the dashboard (`web/`)

### 1. Run it offline (no keys)

The default provider is `mock`, which runs fully offline and returns
deterministic, empty findings — enough to exercise the API, routing, and
tracing without any API keys.

```bash
uv venv && uv pip install -e ".[dev]"
uv run uvicorn api.main:app --reload
```

In another shell:

```bash
curl -s localhost:8000/health
curl -s localhost:8000/version          # shows the active provider + model

curl -s -X POST localhost:8000/review \
  -H 'content-type: application/json' \
  -d '{"diff": "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-x=1\n+y=eval(input())\n"}'
```

The response contains the findings, an overall `score`, `token_usage`, and a
per-node `spans` array (returned inline even when Langfuse is off).

### 2. Use a real model

```bash
cp .env.example .env         # then fill in ONE provider key
export LLM_PROVIDER=groq GROQ_API_KEY=...      # or: LLM_PROVIDER=gemini GEMINI_API_KEY=...
uv run uvicorn api.main:app
```

Providers are swappable behind one interface (`agent/providers/base.py`):
`mock` (default, offline), `groq`, and `gemini`.

### 3. Review a real GitHub PR

```bash
curl -s -X POST localhost:8000/review \
  -H 'content-type: application/json' \
  -d '{"pr_url": "https://github.com/<owner>/<repo>/pull/<n>"}'
```

Set `GITHUB_TOKEN` for private repos / higher rate limits.

### 4. Run the dashboard (optional)

A Vite + React + TS dashboard with a **Review Playground** (paste a diff or PR
URL → annotated findings, score gauge, per-node span table) and **Eval
Analytics** (score trends across runs, gated at the 0.75 threshold).

```bash
# Terminal 1 — API with a real model (mock returns empty findings):
export LLM_PROVIDER=groq GROQ_API_KEY=...
uv run uvicorn api.main:app

# Terminal 2 — dashboard dev server (proxies to the API on :8000):
cd web && npm install && npm run dev     # http://localhost:5173
```

Set `VITE_LANGFUSE_URL` to show an "Open in Langfuse" link in the analytics view.

### Tests & lint

```bash
uv run pytest -q          # unit tests, mock provider, fully offline
uv run ruff check .
cd web && npm test        # frontend tests
```

---

## How it works (30-second version)

A review is a LangGraph `StateGraph` over a single `ReviewState`:

```
ingest ──▶ [ security ──▶ logic ──▶ test_coverage ] ──▶ aggregate ──▶ score
   │                                                        ▲
   └──────────── trivial diff (whitespace/docs) ────────────┘   (skips the LLM nodes)
```

- **ingest** parses the diff and decides if it's trivial (deterministic).
- **security / logic / test_coverage** each call the LLM with a focused prompt
  and return strict-JSON findings; each retries once and degrades gracefully
  rather than crashing the review.
- **aggregate** turns severity counts into a single 0..1 cleanliness score.

Every node is wrapped so a tracer gets one span per node. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

---

## Evaluating the agent

The eval harness runs the **real** `run_review()` over a golden dataset and
scores how well the agent's findings match the expected ones — deterministic,
offline, and repeatable.

- **Dataset:** `evals/golden/` — 20 hand-authored cases (security / logic /
  test-coverage across Python, JS, Go). Each is a `NN-name.diff` +
  `NN-name.expected.json` pair.
- **Scorer (default):** `evals/detection_scorer.py`. A golden finding is matched
  when an agent finding has the **same file, overlapping lines, and same
  category**. Anything not matched deterministically gets one LLM "rescue" check
  (a Groq adjudicator; fail-safe on any error). Per case:

  ```
  recall = matched / total_goldens
  score  = clamp(recall − 0.2 × false_positive_rate)
  ```

- **Gate:** the build passes when the aggregate `score ≥ 0.75`
  (`evals/scoring.py`). `recall` is reported but not gated.

Run it locally:

```bash
export LLM_PROVIDER=groq GROQ_API_KEY=...
uv run python -m evals.run_eval --provider groq

# purely deterministic (skip the LLM rescue step):
EVAL_LLM_FALLBACK=0 uv run python -m evals.run_eval --provider groq
```

Reports (a `.json` + a Markdown table) land in `evals/reports/` and are served
to the dashboard via `GET /eval/reports`.

> A **RAGAS** scorer (`evals/ragas_scorer.py`, faithfulness + answer correctness
> with a Groq judge and local fastembed embeddings) is also included as an
> alternative. The detection scorer is the default because it's deterministic on
> the parts that matter and far cheaper on tokens.

---

## Observability with Langfuse

Each review emits **one trace** with a **span per graph node**:

- LLM nodes → `generation` observations carrying the **model** and
  **input/output token counts** (so Langfuse populates the model column and
  computes cost + latency).
- `ingest` / `aggregate` → plain `span` observations.
- The diff and final score attach as the trace's input/output and an `overall`
  score; everything nests under one root observation.

Enable it:

```bash
export LANGFUSE_ENABLED=true
export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=...
export LANGFUSE_BASE_URL=https://cloud.langfuse.com   # US: https://us.cloud.langfuse.com
```

When Langfuse is **disabled**, the same spans are still returned inline in the
`/review` response under `spans` — so you never lose per-node visibility.
Tracing details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#3-observability--one-langfuse-trace-per-review).

---

## CI

`.github/workflows/ci.yml` runs on every push to `main` and every PR:

1. **test** — `ruff` + `pytest` with the mock provider (offline, no keys).
2. **eval** — runs `python -m evals.run_eval` with a Groq judge. It **fails the
   build if the aggregate detection score < 0.75**, uploads the report as an
   artifact, and comments the score table on the PR.

Set the repository secret `GROQ_API_KEY` for the eval job.

---

## Configuration reference

| Variable                                   | Default                        | Purpose                                    |
| ------------------------------------------ | ------------------------------ | ------------------------------------------ |
| `LLM_PROVIDER`                             | `mock`                         | `mock` \| `groq` \| `gemini`               |
| `GROQ_API_KEY` / `GEMINI_API_KEY`          | —                              | provider key (not needed for `mock`)       |
| `GITHUB_TOKEN`                             | —                              | private repos + higher PR fetch rate limit |
| `LANGFUSE_ENABLED`                         | `false`                        | ship traces to Langfuse                    |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | —                           | Langfuse credentials                       |
| `LANGFUSE_BASE_URL`                        | `https://cloud.langfuse.com`   | Langfuse region host                       |
| `EVAL_LLM_FALLBACK`                        | `1`                            | set `0` to disable the eval LLM rescue     |
| `RAGAS_JUDGE_MODEL`                        | `llama-3.3-70b-versatile`      | judge model for the optional RAGAS scorer  |
| `WEB_ORIGIN`                               | `http://localhost:5173`        | CORS allow-list for the dashboard          |

See `.env.example` for the full list.

---

## Project layout

```
agent/          LangGraph core — graph, state, nodes, prompts, providers, tracing
  nodes/        ingest · security_scan · logic_analysis · test_coverage · aggregate
  providers/    mock · groq · gemini (behind one LLMProvider protocol)
  observability.py   NoOp / Recording / Langfuse tracers
api/            FastAPI app — /review, /review/stream, /eval/reports, GitHub fetch
evals/          golden dataset, harness, detection + RAGAS scorers, CI runner
web/            Vite + React dashboard (Review Playground + Eval Analytics)
docs/           ARCHITECTURE.md and design specs/plans
```
