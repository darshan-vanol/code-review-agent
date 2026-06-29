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


class EvalReportSummary(BaseModel):
    id: str
    passed: bool
    aggregate: dict[str, float]
