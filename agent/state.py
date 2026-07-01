from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Weight used to turn severity counts into a single 0..1 score.
_SEVERITY_WEIGHT = {
    Severity.INFO: 0.0,
    Severity.LOW: 0.1,
    Severity.MEDIUM: 0.3,
    Severity.HIGH: 0.6,
    Severity.CRITICAL: 1.0,
}


class FileDiff(BaseModel):
    path: str
    hunks: list[str] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0


class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int
    severity: Severity
    category: str
    message: str
    suggestion: str


class ReviewScore(BaseModel):
    overall: float
    counts: dict[str, int]

    @classmethod
    def from_findings(cls, findings: list[Finding]) -> "ReviewScore":
        counts = {s.value: 0 for s in Severity}
        penalty = 0.0
        for f in findings:
            counts[f.severity.value] += 1
            penalty += _SEVERITY_WEIGHT[f.severity]
        # `overall` is a 0..1 *cleanliness gauge*, not a severity-weighted sum:
        # 1.0 means clean and it saturates at 0.0 once findings are serious enough
        # (penalty >= 1.0). Callers needing to distinguish "bad" from "very bad"
        # should read `counts`, which preserves per-severity detail.
        overall = max(0.0, 1.0 - min(penalty, 1.0))
        return cls(overall=round(overall, 3), counts=counts)


class ReviewState(BaseModel):
    raw_diff: str
    files: list[FileDiff] = Field(default_factory=list)
    is_trivial: bool = False
    security_findings: list[Finding] = Field(default_factory=list)
    logic_findings: list[Finding] = Field(default_factory=list)
    test_suggestions: list[Finding] = Field(default_factory=list)
    score: ReviewScore | None = None
    errors: list[str] = Field(default_factory=list)
    # Model used by the LLM nodes this run (they all share one provider). Set by
    # the LLM nodes so the tracer can label generation spans with the model.
    model: str | None = None

    token_usage: dict[str, float] = Field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0}
    )
