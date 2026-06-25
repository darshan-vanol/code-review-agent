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
def version() -> dict:
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
