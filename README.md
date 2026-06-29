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

## CI & Evaluation

GitHub Actions (`.github/workflows/ci.yml`) runs on every push to `main` and every PR:

1. **test** — ruff + pytest with the mock provider (no keys, fully offline).
2. **eval** — runs the RAGAS harness (`python -m evals.run_eval`) with a Groq
   judge. It **fails the build if faithfulness or answer correctness < 0.75**,
   uploads the report as an artifact, and comments the score table on the PR.

Set repository secret `GROQ_API_KEY` for the eval job. Run it locally with:

```bash
export LLM_PROVIDER=groq GROQ_API_KEY=...
uv run python -m evals.run_eval --provider groq
```

## Dashboard (web/)

A Vite + React + TS dashboard with two views:

- **Review Playground** — paste a diff or a GitHub PR URL, get annotated findings,
  an overall score gauge, and a per-node span table.
- **Eval Analytics** — RAGAS score trends across runs and a per-PR drill-down,
  gated visually at the 0.75 threshold.

```bash
# 1. Run the API populated with a real model (the mock returns empty findings):
export LLM_PROVIDER=groq GROQ_API_KEY=...   # or gemini / GEMINI_API_KEY
uv run uvicorn api.main:app

# 2. In another shell, run the dashboard dev server (proxies to the API on :8000):
cd web && npm install && npm run dev   # http://localhost:5173
```

The dashboard reads eval reports from the API (`GET /eval/reports`), which serves
the JSON written by `python -m evals.run_eval`. Set `VITE_LANGFUSE_URL` to show an
"Open in Langfuse" link in the analytics view. Run the frontend tests with
`cd web && npm test`.
