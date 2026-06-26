from __future__ import annotations

from pydantic import BaseModel

from agent.graph import run_review
from evals.dataset import GoldenPR

_INSTRUCTION = (
    "Review this pull request diff and report security, logic, and test-coverage "
    "issues with file, line, severity, and a concrete suggestion."
)


class EvalRecord(BaseModel):
    id: str
    user_input: str
    response: str
    retrieved_contexts: list[str]
    reference: str


def _finding_field(finding, name: str):
    # Findings may be Pydantic models (from the agent) or plain dicts (golden).
    if isinstance(finding, dict):
        return finding[name]
    value = getattr(finding, name)
    return getattr(value, "value", value)  # unwrap enums like Severity


def serialize_findings(findings: list) -> str:
    if not findings:
        return "No issues found."
    lines = []
    for f in findings:
        sev = _finding_field(f, "severity")
        cat = _finding_field(f, "category")
        file = _finding_field(f, "file")
        start = _finding_field(f, "line_start")
        end = _finding_field(f, "line_end")
        msg = _finding_field(f, "message")
        lines.append(f"[{sev}][{cat}] {file}:{start}-{end} — {msg}")
    return "\n".join(lines)


def build_records(goldens: list[GoldenPR], provider) -> list[EvalRecord]:
    records: list[EvalRecord] = []
    for g in goldens:
        state = run_review(g.diff, provider)
        agent_findings = (
            state.security_findings + state.logic_findings + state.test_suggestions
        )
        reference = f"{g.summary}\n{serialize_findings(g.findings)}"
        records.append(
            EvalRecord(
                id=g.id,
                user_input=_INSTRUCTION,
                response=serialize_findings(agent_findings),
                retrieved_contexts=[g.diff],
                reference=reference,
            )
        )
    return records
