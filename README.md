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
