import json
from pathlib import Path

from evals.dataset import GoldenPR
from evals.run_eval import run
from agent.providers.mock import MockProvider

_DIFF = (
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
    "@@ -1 +1 @@\n-x = 1\n+y = 2\n"
)


def _golden(gid):
    return GoldenPR(
        id=gid, language="python", category="logic", diff=_DIFF,
        summary="s", findings=[{
            "file": "app.py", "line_start": 1, "line_end": 1, "severity": "low",
            "category": "logic", "message": "m", "suggestion": "x"}],
    )


def _passing_scorer(records):
    return [{"id": r.id, "score": 0.9, "recall": 0.9} for r in records]


def _failing_scorer(records):
    return [{"id": r.id, "score": 0.5, "recall": 0.5} for r in records]


def test_run_passes_and_writes_reports(tmp_path: Path):
    code = run(
        tmp_path, provider=MockProvider(), scorer=_passing_scorer,
        goldens=[_golden("a"), _golden("b")], threshold=0.75,
    )
    assert code == 0
    json_files = list(tmp_path.glob("*.json"))
    md_files = list(tmp_path.glob("*.md"))
    assert len(json_files) == 1 and len(md_files) == 1
    report = json.loads(json_files[0].read_text())
    assert report["passed"] is True
    assert len(report["items"]) == 2


def test_run_fails_below_threshold(tmp_path: Path):
    code = run(
        tmp_path, provider=MockProvider(), scorer=_failing_scorer,
        goldens=[_golden("a")], threshold=0.75,
    )
    assert code == 1
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["passed"] is False
