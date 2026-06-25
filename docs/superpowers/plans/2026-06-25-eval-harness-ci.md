# Eval Harness + CI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a RAGAS-based evaluation harness over a 20-PR golden dataset (faithfulness + answer correctness, gated at ≥0.75) and a GitHub Actions CI pipeline that runs unit tests offline and fails the build when eval scores drop below threshold.

**Architecture:** A new `evals/` package: a golden dataset of 20 PR diffs each paired with a ground-truth review JSON, a loader, a builder that runs the agent over each PR and shapes the result into RAGAS records, pure scoring/gating/report functions, and a `run_eval.py` CLI. The RAGAS call (Groq judge LLM + lightweight embeddings) is isolated behind one function and injectable, so the whole pipeline (build → score → gate → report) is unit-testable offline with a stub scorer. CI runs lint + unit tests with the mock provider (no keys), then an eval job that runs the real RAGAS scorer with a `GROQ_API_KEY` secret and fails below 0.75.

**Tech Stack:** Python 3.11+, RAGAS, langchain-groq (judge LLM), fastembed (local embeddings, no torch), pytest, ruff, GitHub Actions. Builds on `agent/`.

## Global Constraints

- Python `>=3.11`; manage deps + run via `uv` (`uv add ...`, `uv run ...`).
- ruff line-length 100; keep `uv run ruff check .` clean before every commit.
- Everything except the live RAGAS scoring call must run offline with no API keys. Unit tests use the `mock` provider and a stub scorer — never the network.
- The eval gate threshold is **0.75** for BOTH faithfulness and answer correctness.
- Reuse agent-core: `from agent.graph import run_review`, `from agent.providers.factory import make_provider`, `from agent.state import Finding, ReviewState`. Do not re-run nodes by hand.
- TDD: failing test → confirm fail → implement → confirm pass → commit.

### Agent-core interfaces this plan consumes (authoritative)

```python
# agent/graph.py
def run_review(diff: str, provider, tracer=None) -> ReviewState: ...
# agent/providers/factory.py
def make_provider(name: str | None = None) -> LLMProvider: ...   # default mock
# agent/providers/mock.py
class MockProvider:  # MockProvider(scripted: dict[str, list[dict]] | None = None)
# agent/state.py — ReviewState has: security_findings, logic_findings,
#   test_suggestions (each list[Finding]); Finding has file, line_start, line_end,
#   severity (enum -> .value str), category, message, suggestion.
```

---

## File Structure

```
evals/
├── __init__.py
├── golden/                 # 20 PRs: <id>.diff + <id>.expected.json (paired)
│   ├── 01-sql-injection-py.diff
│   ├── 01-sql-injection-py.expected.json
│   └── ... (20 pairs total)
├── dataset.py              # GoldenPR, load_golden()
├── harness.py              # serialize_review(), EvalRecord, build_records()
├── scoring.py              # aggregate_scores(), passes_threshold(), render_report()
├── ragas_scorer.py         # score_with_ragas() — isolated RAGAS call
└── run_eval.py             # CLI: load -> build -> score -> gate -> report

tests/
├── test_eval_dataset.py        # loader + 20-item integrity
├── test_eval_harness.py        # serialize + build_records (mock provider)
├── test_eval_scoring.py        # aggregate / gate / report (pure)
└── test_eval_runner.py         # end-to-end run() with a stub scorer

.github/workflows/ci.yml         # test job (offline) + eval job (Groq secret, gate)
```

---

## Task 1: Golden dataset + loader

**Files:**
- Create: `evals/__init__.py` (empty), `evals/dataset.py`
- Create: 20 pairs under `evals/golden/` (`<id>.diff` + `<id>.expected.json`)
- Test: `tests/test_eval_dataset.py`

**Interfaces:**
- Produces:
  - `GoldenPR` dataclass: `id: str`, `language: str`, `category: str`, `diff: str`, `summary: str`, `findings: list[dict]`.
  - `GOLDEN_DIR: Path` and `load_golden() -> list[GoldenPR]` — loads every `<id>.diff` that has a sibling `<id>.expected.json`, sorted by id.
- Each `<id>.expected.json` shape:
  ```json
  {"id": "01-sql-injection-py", "language": "python", "category": "security",
   "summary": "one-sentence expected verdict",
   "findings": [{"file": "app.py", "line_start": 6, "line_end": 6,
                 "severity": "high", "category": "security",
                 "message": "...", "suggestion": "..."}]}
  ```

- [ ] **Step 1: Write the failing test**

`tests/test_eval_dataset.py`:
```python
from evals.dataset import GoldenPR, load_golden

_VALID_CATEGORIES = {"security", "logic", "test"}
_REQUIRED_LANGUAGES = {"python", "javascript", "go"}
_FINDING_KEYS = {"file", "line_start", "line_end", "severity", "category",
                 "message", "suggestion"}


def test_loads_exactly_twenty_golden_prs():
    goldens = load_golden()
    assert len(goldens) == 20
    assert all(isinstance(g, GoldenPR) for g in goldens)


def test_ids_are_unique():
    ids = [g.id for g in load_golden()]
    assert len(ids) == len(set(ids))


def test_every_pr_is_well_formed():
    for g in load_golden():
        assert g.diff.strip(), f"{g.id} has empty diff"
        assert "diff --git" in g.diff, f"{g.id} is not a unified diff"
        assert g.category in _VALID_CATEGORIES, f"{g.id} bad category {g.category}"
        assert g.summary.strip(), f"{g.id} has empty summary"
        assert g.findings, f"{g.id} has no ground-truth findings"
        for f in g.findings:
            assert _FINDING_KEYS <= set(f), f"{g.id} finding missing keys"


def test_dataset_covers_all_categories_and_languages():
    goldens = load_golden()
    assert {g.category for g in goldens} == _VALID_CATEGORIES
    assert _REQUIRED_LANGUAGES <= {g.language for g in goldens}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_dataset.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals'`.

- [ ] **Step 3: Implement the loader**

`evals/__init__.py`: empty file.

`evals/dataset.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"


@dataclass
class GoldenPR:
    id: str
    language: str
    category: str
    diff: str
    summary: str
    findings: list[dict]


def load_golden() -> list[GoldenPR]:
    """Load every <id>.diff that has a sibling <id>.expected.json, sorted by id."""
    goldens: list[GoldenPR] = []
    for diff_path in sorted(GOLDEN_DIR.glob("*.diff")):
        meta_path = diff_path.with_suffix(".expected.json")
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        goldens.append(
            GoldenPR(
                id=meta["id"],
                language=meta["language"],
                category=meta["category"],
                diff=diff_path.read_text(),
                summary=meta["summary"],
                findings=meta["findings"],
            )
        )
    return goldens
```

- [ ] **Step 4: Author the 20 golden PRs**

Create 20 paired files in `evals/golden/`. Each pair is `<id>.diff` (a realistic unified diff that begins with a `diff --git a/... b/...` line) and `<id>.expected.json` (the ground-truth review in the shape shown in this task's Interfaces block).

Coverage requirements (enforced by Step 1's tests — they fail until met):
- Exactly 20 pairs, unique ids.
- `category` distribution: at least 6 `security`, 6 `logic`, 6 `test` (the remaining 2 free).
- `language` spread: at least 4 `python`, 4 `javascript`, 4 `go` (rest free; use the value `javascript` for both JS and TS files).
- Every diff parses to ≥1 file and contains real code changes (not whitespace-only), so the agent does not short-circuit as trivial.
- Every `findings` entry has all seven keys; `severity` ∈ {info,low,medium,high,critical}.

Two complete worked examples to follow exactly:

`evals/golden/01-sql-injection-py.diff`:
```diff
diff --git a/users/db.py b/users/db.py
index 1111111..2222222 100644
--- a/users/db.py
+++ b/users/db.py
@@ -1,4 +1,7 @@
 import sqlite3
 
-def get_user(conn, uid):
-    return conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
+def get_user(conn, uid):
+    # build query dynamically
+    query = "SELECT * FROM users WHERE id = '" + uid + "'"
+    return conn.execute(query).fetchone()
```

`evals/golden/01-sql-injection-py.expected.json`:
```json
{
  "id": "01-sql-injection-py",
  "language": "python",
  "category": "security",
  "summary": "Introduces a SQL injection by interpolating user input directly into the query string instead of using a parameterized query.",
  "findings": [
    {
      "file": "users/db.py",
      "line_start": 5,
      "line_end": 6,
      "severity": "high",
      "category": "security",
      "message": "User-controlled `uid` is concatenated into the SQL string, enabling SQL injection.",
      "suggestion": "Use a parameterized query: conn.execute(\"SELECT * FROM users WHERE id = ?\", (uid,))."
    }
  ]
}
```

`evals/golden/07-off-by-one-go.diff`:
```diff
diff --git a/pkg/window/slice.go b/pkg/window/slice.go
index 3333333..4444444 100644
--- a/pkg/window/slice.go
+++ b/pkg/window/slice.go
@@ -1,6 +1,6 @@
 package window
 
 func Last(xs []int, n int) []int {
-    if n > len(xs) {
+    if n >= len(xs) {
         n = len(xs)
     }
     return xs[len(xs)-n:]
 }
```

`evals/golden/07-off-by-one-go.expected.json`:
```json
{
  "id": "07-off-by-one-go",
  "language": "go",
  "category": "logic",
  "summary": "Changes a boundary check from `>` to `>=`, which is harmless here but the function still panics when n is negative.",
  "findings": [
    {
      "file": "pkg/window/slice.go",
      "line_start": 4,
      "line_end": 4,
      "severity": "low",
      "category": "logic",
      "message": "`n >= len(xs)` clamps one case earlier than needed; negative n still causes a slice out-of-range panic.",
      "suggestion": "Guard against n < 0 before slicing, e.g. if n < 0 { n = 0 }."
    }
  ]
}
```

Author the remaining 18 pairs following this format, meeting the coverage requirements above. Use realistic, varied scenarios (e.g. hardcoded secret, missing auth check, path traversal for security; nil/None deref, wrong operator, unhandled error, race for logic; new public function with no test, removed test, untested error branch for test-coverage).

- [ ] **Step 5: Run the dataset tests to verify they pass**

Run: `uv run pytest tests/test_eval_dataset.py -v`
Expected: PASS (4 passed) — only once all 20 valid, category- and language-covered pairs exist.

- [ ] **Step 6: Commit**

```bash
git add evals/__init__.py evals/dataset.py evals/golden/ tests/test_eval_dataset.py
git commit -m "feat: add 20-PR golden eval dataset and loader"
```

---

## Task 2: Review serialization + RAGAS record builder

**Files:**
- Create: `evals/harness.py`
- Test: `tests/test_eval_harness.py`

**Interfaces:**
- Consumes: `load_golden`/`GoldenPR`, `run_review`, `MockProvider`, `ReviewState`, `Finding`.
- Produces:
  - `serialize_findings(findings: list) -> str` — turns a list of findings (Pydantic `Finding` or dicts) into a stable newline-joined text, one line per finding: `[severity][category] file:line_start-line_end — message`. Returns `"No issues found."` when empty.
  - `EvalRecord` pydantic model: `id: str`, `user_input: str`, `response: str`, `retrieved_contexts: list[str]`, `reference: str`. (Field names match RAGAS `SingleTurnSample`.)
  - `build_records(goldens: list[GoldenPR], provider) -> list[EvalRecord]` — runs `run_review(g.diff, provider)` per golden, serializes the agent's combined findings as `response`, uses `g.diff` as the single retrieved context, and serializes the golden's expected findings + summary as `reference`. `user_input` is the fixed instruction string `_INSTRUCTION`.

- [ ] **Step 1: Write the failing test**

`tests/test_eval_harness.py`:
```python
from evals.dataset import GoldenPR
from evals.harness import EvalRecord, build_records, serialize_findings
from agent.providers.mock import MockProvider

_DIFF = (
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
    "@@ -1 +1 @@\n-x = 1\n+y = run_security_check()\n"
)

_EXPECTED_FINDING = {
    "file": "app.py", "line_start": 1, "line_end": 1, "severity": "high",
    "category": "security", "message": "issue", "suggestion": "fix it",
}

_SCRIPTED = [{
    "file": "app.py", "line_start": 1, "line_end": 1, "severity": "high",
    "category": "security", "message": "SQLi", "suggestion": "parameterize",
}]


def test_serialize_findings_empty():
    assert serialize_findings([]) == "No issues found."


def test_serialize_findings_formats_each_line():
    text = serialize_findings([_EXPECTED_FINDING])
    assert "[high][security]" in text
    assert "app.py:1-1" in text
    assert "issue" in text


def test_build_records_shapes_one_record_per_golden():
    golden = GoldenPR(
        id="g1", language="python", category="security", diff=_DIFF,
        summary="expected verdict", findings=[_EXPECTED_FINDING],
    )
    provider = MockProvider(scripted={"security": _SCRIPTED})
    records = build_records([golden], provider)
    assert len(records) == 1
    r = records[0]
    assert isinstance(r, EvalRecord)
    assert r.id == "g1"
    assert r.user_input          # non-empty instruction
    assert "SQLi" in r.response  # agent's finding
    assert r.retrieved_contexts == [_DIFF]
    assert "expected verdict" in r.reference
    assert "issue" in r.reference
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_harness.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.harness'`.

- [ ] **Step 3: Implement the harness**

`evals/harness.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eval_harness.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/harness.py tests/test_eval_harness.py
git commit -m "feat: add review serialization and RAGAS record builder"
```

---

## Task 3: Scoring aggregation, gating, and report rendering (pure)

**Files:**
- Create: `evals/scoring.py`
- Test: `tests/test_eval_scoring.py`

**Interfaces:**
- Produces:
  - `THRESHOLD = 0.75`.
  - `aggregate_scores(per_item: list[dict]) -> dict[str, float]` — given per-item dicts each with `faithfulness` and `answer_correctness` floats, returns `{"faithfulness": mean, "answer_correctness": mean}` (0.0 for an empty list).
  - `passes_threshold(scores: dict[str, float], threshold: float = THRESHOLD) -> bool` — True iff BOTH metrics ≥ threshold.
  - `render_report(scores, per_item, *, threshold=THRESHOLD) -> tuple[dict, str]` — returns a JSON-serializable dict and a markdown string. The dict has `aggregate`, `threshold`, `passed`, and `items`. The markdown has a header line with PASS/FAIL and a table of per-item scores.

- [ ] **Step 1: Write the failing test**

`tests/test_eval_scoring.py`:
```python
from evals.scoring import (
    THRESHOLD,
    aggregate_scores,
    passes_threshold,
    render_report,
)

_ITEMS = [
    {"id": "a", "faithfulness": 0.9, "answer_correctness": 0.8},
    {"id": "b", "faithfulness": 0.7, "answer_correctness": 0.8},
]


def test_aggregate_means():
    agg = aggregate_scores(_ITEMS)
    assert round(agg["faithfulness"], 3) == 0.8
    assert round(agg["answer_correctness"], 3) == 0.8


def test_aggregate_empty_is_zero():
    assert aggregate_scores([]) == {"faithfulness": 0.0, "answer_correctness": 0.0}


def test_passes_threshold_requires_both():
    assert passes_threshold({"faithfulness": 0.8, "answer_correctness": 0.76})
    assert not passes_threshold({"faithfulness": 0.8, "answer_correctness": 0.74})


def test_threshold_constant_is_point_seven_five():
    assert THRESHOLD == 0.75


def test_render_report_marks_pass_and_lists_items():
    agg = aggregate_scores(_ITEMS)
    report, md = render_report(agg, _ITEMS)
    assert report["threshold"] == 0.75
    assert report["passed"] is True
    assert len(report["items"]) == 2
    assert "PASS" in md
    assert "| a |" in md


def test_render_report_marks_fail():
    items = [{"id": "x", "faithfulness": 0.5, "answer_correctness": 0.5}]
    report, md = render_report(aggregate_scores(items), items)
    assert report["passed"] is False
    assert "FAIL" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_scoring.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.scoring'`.

- [ ] **Step 3: Implement scoring**

`evals/scoring.py`:
```python
from __future__ import annotations

THRESHOLD = 0.75
_METRICS = ("faithfulness", "answer_correctness")


def aggregate_scores(per_item: list[dict]) -> dict[str, float]:
    if not per_item:
        return {m: 0.0 for m in _METRICS}
    return {
        m: sum(item[m] for item in per_item) / len(per_item) for m in _METRICS
    }


def passes_threshold(scores: dict[str, float], threshold: float = THRESHOLD) -> bool:
    return all(scores[m] >= threshold for m in _METRICS)


def render_report(
    scores: dict[str, float], per_item: list[dict], *, threshold: float = THRESHOLD
) -> tuple[dict, str]:
    passed = passes_threshold(scores, threshold)
    report = {
        "aggregate": scores,
        "threshold": threshold,
        "passed": passed,
        "items": per_item,
    }
    status = "PASS" if passed else "FAIL"
    lines = [
        f"# Eval Report — {status}",
        "",
        f"- Threshold: {threshold}",
        f"- Faithfulness: {scores['faithfulness']:.3f}",
        f"- Answer correctness: {scores['answer_correctness']:.3f}",
        "",
        "| id | faithfulness | answer_correctness |",
        "| --- | --- | --- |",
    ]
    for item in per_item:
        lines.append(
            f"| {item['id']} | {item['faithfulness']:.3f} "
            f"| {item['answer_correctness']:.3f} |"
        )
    return report, "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_eval_scoring.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add evals/scoring.py tests/test_eval_scoring.py
git commit -m "feat: add eval scoring aggregation, gating, and report rendering"
```

---

## Task 4: RAGAS scorer + run_eval CLI

**Files:**
- Create: `evals/ragas_scorer.py`
- Create: `evals/run_eval.py`
- Test: `tests/test_eval_runner.py`

**Interfaces:**
- Consumes: `load_golden`, `build_records`, `aggregate_scores`, `render_report`, `passes_threshold`, `make_provider`, `EvalRecord`.
- Produces:
  - `score_with_ragas(records: list[EvalRecord]) -> list[dict]` (in `ragas_scorer.py`) — runs RAGAS faithfulness + answer correctness with a Groq judge LLM and fastembed embeddings; returns one dict per record `{"id", "faithfulness", "answer_correctness"}`. Isolated; exercised in CI/manual only.
  - `run(out_dir: Path, *, provider=None, scorer=None, goldens=None, threshold=THRESHOLD) -> int` (in `run_eval.py`) — builds records, scores (via injected `scorer`, default `score_with_ragas`), aggregates, writes `<out_dir>/<n>.json` and `<out_dir>/<n>.md`, prints the markdown, and returns exit code `0` if passed else `1`.
  - `main()` — argparse CLI (`--out-dir evals/reports`, `--threshold 0.75`, `--provider`), calls `run(...)`, `sys.exit`s its return code.

- [ ] **Step 1: Add dependencies**

Run: `uv add ragas langchain-groq langchain-community fastembed`
Expected: ragas + langchain-groq + langchain-community + fastembed installed (large
install; allow time). fastembed is used for embeddings (ONNX, no torch) to keep CI light.

- [ ] **Step 2: Write the failing test for the runner (with a stub scorer)**

`tests/test_eval_runner.py`:
```python
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
    return [{"id": r.id, "faithfulness": 0.9, "answer_correctness": 0.9}
            for r in records]


def _failing_scorer(records):
    return [{"id": r.id, "faithfulness": 0.5, "answer_correctness": 0.5}
            for r in records]


def test_run_passes_and_writes_reports(tmp_path: Path):
    code = run(
        tmp_path, provider=MockProvider(), scorer=_passing_scorer,
        goldens=[_golden("a"), _golden("b")],
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
        goldens=[_golden("a")],
    )
    assert code == 1
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["passed"] is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_runner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evals.run_eval'`.

- [ ] **Step 4: Implement the runner**

`evals/run_eval.py`:
```python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.providers.factory import make_provider
from evals.dataset import load_golden
from evals.harness import build_records
from evals.scoring import THRESHOLD, aggregate_scores, render_report


def run(out_dir: Path, *, provider=None, scorer=None, goldens=None,
        threshold: float = THRESHOLD) -> int:
    """Build records, score them, write reports, return 0 (pass) or 1 (fail)."""
    provider = provider if provider is not None else make_provider()
    if scorer is None:
        from evals.ragas_scorer import score_with_ragas
        scorer = score_with_ragas
    goldens = goldens if goldens is not None else load_golden()

    records = build_records(goldens, provider)
    per_item = scorer(records)
    scores = aggregate_scores(per_item)
    report, markdown = render_report(scores, per_item, threshold=threshold)

    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(out_dir.glob("*.json"))) + 1
    (out_dir / f"{n}.json").write_text(json.dumps(report, indent=2))
    (out_dir / f"{n}.md").write_text(markdown)
    print(markdown)
    return 0 if report["passed"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAGAS eval harness.")
    parser.add_argument("--out-dir", default="evals/reports", type=Path)
    parser.add_argument("--threshold", default=THRESHOLD, type=float)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()
    provider = make_provider(args.provider) if args.provider else make_provider()
    sys.exit(run(args.out_dir, provider=provider, threshold=args.threshold))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run runner test to verify it passes**

Run: `uv run pytest tests/test_eval_runner.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Implement the RAGAS scorer + verify the installed API**

First probe the installed RAGAS surface:
Run: `uv run python -c "import ragas; print('ragas', ragas.__version__); from ragas import evaluate, EvaluationDataset; from ragas.metrics import Faithfulness, AnswerCorrectness; print('ok 0.2+ API')"`
Expected: prints the ragas version and `ok 0.2+ API`.

> If that import line fails, the installed ragas uses a different surface. Adjust
> `score_with_ragas` to the installed version — this covers the metric/dataset
> imports AND the LLM/embeddings wrapper names (e.g. ragas 0.1 uses
> `from datasets import Dataset` + `from ragas.metrics import faithfulness,
> answer_correctness` + `evaluate(dataset, metrics=[...], llm=..., embeddings=...)`;
> the embeddings wrapper or `FastEmbedEmbeddings` import path may differ by version).
> Probe the embeddings path too:
> `uv run python -c "from langchain_community.embeddings.fastembed import FastEmbedEmbeddings; print('ok')"`
> and `uv run python -c "from ragas.embeddings import LangchainEmbeddingsWrapper; print('ok')"`.
> Keep the function's input (`list[EvalRecord]`) and output
> (`list[{"id","faithfulness","answer_correctness"}]`) identical so `run()` and all
> tests are unaffected. Note the exact API you used.

`evals/ragas_scorer.py` (targets ragas 0.2+; adapt per the probe if needed):
```python
from __future__ import annotations

import os

from evals.harness import EvalRecord


def score_with_ragas(records: list[EvalRecord]) -> list[dict]:
    """Score records with RAGAS faithfulness + answer correctness, using a Groq
    judge LLM and local fastembed embeddings. Requires GROQ_API_KEY in the env.

    Returns one {"id", "faithfulness", "answer_correctness"} dict per record."""
    from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
    from langchain_groq import ChatGroq
    from ragas import EvaluationDataset, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import AnswerCorrectness, Faithfulness

    model = os.environ.get("RAGAS_JUDGE_MODEL", "llama-3.3-70b-versatile")
    judge = LangchainLLMWrapper(ChatGroq(model=model, temperature=0))
    embeddings = LangchainEmbeddingsWrapper(
        FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    )

    dataset = EvaluationDataset.from_list([
        {
            "user_input": r.user_input,
            "response": r.response,
            "retrieved_contexts": r.retrieved_contexts,
            "reference": r.reference,
        }
        for r in records
    ])
    result = evaluate(
        dataset,
        metrics=[Faithfulness(), AnswerCorrectness()],
        llm=judge,
        embeddings=embeddings,
    )
    df = result.to_pandas()
    out: list[dict] = []
    for record, (_, row) in zip(records, df.iterrows()):
        out.append({
            "id": record.id,
            "faithfulness": float(row["faithfulness"]),
            "answer_correctness": float(row["answer_correctness"]),
        })
    return out
```

- [ ] **Step 7: Run full suite + lint**

Run: `uv run pytest -q && uv run ruff check .`
Expected: full suite PASS (the RAGAS call itself is not unit-tested — only the runner with a stub scorer is); ruff clean.

- [ ] **Step 8: Commit**

```bash
git add evals/ragas_scorer.py evals/run_eval.py tests/test_eval_runner.py pyproject.toml uv.lock
git commit -m "feat: add RAGAS scorer and eval runner CLI with threshold gate"
```

---

## Task 5: GitHub Actions CI pipeline

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `evals/reports/.gitkeep` (so the reports dir exists in CI)
- Modify: `README.md` (add a short CI + eval section)

**Interfaces:** none (CI configuration + docs).

- [ ] **Step 1: Create the reports dir placeholder**

Create empty file `evals/reports/.gitkeep`.

- [ ] **Step 2: Write the workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    name: Lint + unit tests (offline)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.11
      - name: Install dependencies
        run: uv pip install --system -e ".[dev]"
      - name: Ruff
        run: uv run ruff check .
      - name: Pytest (mock provider, no keys)
        env:
          LLM_PROVIDER: mock
        run: uv run pytest -q

  eval:
    name: RAGAS eval gate
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v5
      - name: Set up Python
        run: uv python install 3.11
      - name: Install dependencies
        run: uv pip install --system -e ".[dev]"
      - name: Run eval (fails build if faithfulness or correctness < 0.75)
        env:
          LLM_PROVIDER: groq
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
        run: uv run python -m evals.run_eval --out-dir evals/reports --provider groq
      - name: Upload eval report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: eval-report
          path: evals/reports/
      - name: Comment scores on PR
        if: always() && github.event_name == 'pull_request'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const path = require('path');
            const dir = 'evals/reports';
            const md = fs.readdirSync(dir).filter(f => f.endsWith('.md')).sort();
            if (md.length === 0) return;
            const body = fs.readFileSync(path.join(dir, md[md.length - 1]), 'utf8');
            await github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body,
            });
```

- [ ] **Step 3: Validate the workflow YAML parses**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('valid yaml')"`
Expected: prints `valid yaml`. (If pyyaml is missing, run `uv run --with pyyaml python -c "..."`.)

- [ ] **Step 4: Add a CI section to `README.md`**

Append to `README.md`:
````markdown
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
````

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml evals/reports/.gitkeep README.md
git commit -m "ci: add GitHub Actions test + RAGAS eval gate workflow"
```

---

## Self-review notes (spec coverage)

- Spec §6 — 20 golden PRs with ground-truth → Task 1; RAGAS faithfulness + answer correctness → Task 4 (`score_with_ragas`); ≥0.75 gate → Tasks 3 (`passes_threshold`) + 4 (runner exit code); JSON + markdown reports → Tasks 3 + 4.
- Spec §7 — CI runs eval suite → Task 5 `eval` job; fails below threshold → runner returns 1, job fails; runs on prompt change → triggers on every PR/push (prompt files live in `agent/prompts/`, so any prompt edit triggers it); report artifact + PR comment → Task 5 steps.
- Offline guarantee — unit tests use mock provider + stub scorer (Tasks 2–4); only CI's eval job and manual runs hit the network. RAGAS API uncertainty handled with a probe step (Task 4 Step 6), mirroring the LangGraph/Langfuse approach.

## Done criteria

- `uv run pytest -q` fully green (agent + api + evals tests), offline, no keys.
- `uv run ruff check .` clean.
- `uv run python -m evals.run_eval --provider mock` runs end-to-end and writes a report (scores will be low with the mock, but the pipeline works); with `--provider groq` + `GROQ_API_KEY` it produces real RAGAS scores and gates at 0.75.
- `.github/workflows/ci.yml` is valid YAML with a `test` job (offline) and an `eval` job (Groq secret) that fails the build below threshold and comments on PRs.
