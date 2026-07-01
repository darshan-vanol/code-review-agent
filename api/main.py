from __future__ import annotations

import json
import os
from collections.abc import Iterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from agent.graph import run_review, stream_review
from agent.observability import make_tracer
from agent.providers.factory import make_provider
from api.github import GitHubError, fetch_pull_request
from api.reports import get_report, list_reports
from api.schemas import EvalReportSummary, ReviewRequest, ReviewResponse

app = FastAPI(title="Code Review Assistant", version="0.1.0")

_web_origins = os.environ.get("WEB_ORIGIN", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _web_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _strip_diff_headers(text: str) -> str:
    """Remove `diff --git` lines from PR prose so the diff parser doesn't treat
    them as real file boundaries when the prose is prepended to the diff."""
    return "\n".join(
        line for line in text.splitlines() if not line.startswith("diff --git")
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version() -> dict:
    provider = os.environ.get("LLM_PROVIDER", "mock").lower()
    return {
        "version": app.version,
        "provider": provider,
        # The configured model for the active provider. Instantiating the
        # provider only reads env/config (no network call), so this is safe to
        # resolve here and lets the UI show the model before any review runs.
        "model": make_provider(provider).model,
        "langfuse_enabled": os.environ.get("LANGFUSE_ENABLED", "").lower()
        in {"1", "true", "yes"},
    }


@app.get("/eval/reports", response_model=list[EvalReportSummary])
def eval_reports() -> list[dict]:
    return list_reports()


@app.get("/eval/reports/{report_id}")
def eval_report(report_id: str) -> dict:
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No eval report '{report_id}'")
    return report


def _resolve_diff(req: ReviewRequest) -> str:
    """Turn a request into the unified diff to review, fetching the PR if needed.

    Raises ValueError for a bad PR URL and GitHubError for a fetch failure; callers
    translate those into HTTP status codes or stream error events."""
    if not req.pr_url:
        return req.diff or ""
    pr = fetch_pull_request(req.pr_url, token=os.environ.get("GITHUB_TOKEN"))
    # Prepend PR title/body as context. The diff parser starts a file on any
    # `diff --git` line, so strip such lines from the prose first to avoid a
    # PR description injecting a phantom file into the parse.
    context = _strip_diff_headers(f"PR: {pr.title}\n\n{pr.body}")
    return f"{context}\n\n{pr.diff}"


def _build_response(result, spans) -> ReviewResponse:
    return ReviewResponse(
        is_trivial=result.is_trivial,
        score=result.score,
        security_findings=result.security_findings,
        logic_findings=result.logic_findings,
        test_suggestions=result.test_suggestions,
        token_usage=result.token_usage,
        spans=spans,
        errors=result.errors,
    )


@app.post("/review", response_model=ReviewResponse)
def review(req: ReviewRequest) -> ReviewResponse:
    try:
        diff = _resolve_diff(req)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except GitHubError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    tracer = make_tracer()
    result = run_review(diff, make_provider(), tracer)
    return _build_response(result, tracer.spans)


@app.post("/review/stream")
def review_stream(req: ReviewRequest) -> StreamingResponse:
    """Same review as POST /review, but streams newline-delimited JSON progress
    events as each stage finishes, then a final result. One JSON object per line:
      {"type": "progress", "stage": "<fetch|ingest|security|logic|test_coverage|aggregate>"}
      {"type": "result", "data": { ...ReviewResponse... }}
      {"type": "error", "detail": "..."}
    """

    def emit(obj: dict) -> str:
        return json.dumps(obj) + "\n"

    def generate() -> Iterator[str]:
        try:
            diff = _resolve_diff(req)
        except (ValueError, GitHubError) as e:
            yield emit({"type": "error", "detail": str(e)})
            return
        if req.pr_url:
            yield emit({"type": "progress", "stage": "fetch"})

        tracer = make_tracer()
        try:
            for kind, payload in stream_review(diff, make_provider(), tracer):
                if kind == "progress":
                    yield emit({"type": "progress", "stage": payload})
                else:
                    resp = _build_response(payload, tracer.spans)
                    yield emit({"type": "result", "data": resp.model_dump()})
        except Exception as e:  # noqa: BLE001 - report mid-stream, not as a 500
            yield emit({"type": "error", "detail": str(e)})

    return StreamingResponse(generate(), media_type="application/x-ndjson")
