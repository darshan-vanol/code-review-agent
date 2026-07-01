# Detection-based Eval Scorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the RAGAS faithfulness/answer_correctness eval gate (which fails on correct reviews because QA metrics don't fit code review) with a detection-based scorer that measures whether the agent caught each golden bug, without excessive noise.

**Architecture:** A new `evals/detection_scorer.py` matches the agent's structured findings against each golden's structured findings — deterministically (same file + line-range overlap + category), with a single optional Groq LLM fallback per still-unmatched golden. Per item it computes `score = clamp(recall − 0.2·fp_rate, 0, 1)` plus `recall`. The runner gates on the aggregate `score`; the dashboard is updated to read the new `score`/`recall` fields.

**Tech Stack:** Python 3.11 (pydantic, pytest), the existing LangGraph agent + provider factory, React + TypeScript + Vite + Vitest dashboard, recharts.

## Global Constraints

- Match rule (deterministic): agent finding matches a golden finding iff **same `file`** (exact after `.strip()`) **and** line-range overlap (`a.line_start <= g.line_end and g.line_start <= a.line_end`) **and** **same `category`**. Severity is recorded but never required for a match.
- Per-item score formula: `recall = matched_goldens / total_goldens`; `fp_rate = unmatched_agent_findings / max(total_agent_findings, 1)`; `score = clamp(recall − PRECISION_PENALTY * fp_rate, 0.0, 1.0)` with `PRECISION_PENALTY = 0.2`. Both `score` and `recall` are always finite floats (never None/NaN).
- Gate on **`score` only**; `recall` is reported but not gated.
- LLM fallback: at most **one** Groq call per golden left unmatched by the deterministic pass. Any error or unparseable response → treat as **no match** (fail-safe; never lowers a deterministic match). Disabled when env `EVAL_LLM_FALLBACK=0`.
- Report JSON keeps its top-level shape: `{aggregate, threshold, passed, items}`. `aggregate` becomes `{"score": float, "recall": float}`; each item is `{"id", "score", "recall", "matched", "total_goldens", "false_positives", "total_agent_findings"}`.
- RAGAS: `evals/ragas_scorer.py` stays in the repo but is no longer the default scorer and no longer gates the build.
- Commit after every task. Run `uv run ruff check .` before Python commits; `cd web && npm test` before dashboard commit.

---

## File Structure

- **Create** `evals/detection_scorer.py` — matching + scoring (deterministic core + LLM fallback).
- **Modify** `evals/harness.py` — carry structured findings on `EvalRecord`.
- **Modify** `evals/scoring.py` — metrics `score`/`recall`, gate on `score`.
- **Modify** `evals/run_eval.py` — default scorer becomes detection; wire LLM fallback.
- **Modify** `web/src/api.ts` — `EvalAggregate` + `EvalItem` field names.
- **Modify** `web/src/evals/ReportTable.tsx`, `VerdictBanner.tsx`, `TrendChart.tsx`, `MetricGuide.tsx`.
- **Create/Modify tests**: `tests/test_detection_scorer.py` (new), `tests/test_eval_harness.py`, `tests/test_eval_scoring.py`, `tests/test_eval_runner.py`, `web/src/evals/ReportTable.test.tsx`, `web/src/evals/EvalAnalytics.test.tsx`.

---

## Task 1: Carry structured findings on EvalRecord

**Files:**
- Modify: `evals/harness.py`
- Test: `tests/test_eval_harness.py`

**Interfaces:**
- Produces: `EvalRecord` with two new fields `agent_findings: list[dict]` and `golden_findings: list[dict]`, each dict having keys `file, line_start, line_end, severity, category, message`. Helper `normalize_finding(finding) -> dict` (works on Pydantic finding objects and plain golden dicts).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_eval_harness.py`:

```python
def test_build_records_carries_structured_findings():
    golden = GoldenPR(
        id="g1", language="python", category="security", diff=_DIFF,
        summary="expected verdict", findings=[_EXPECTED_FINDING],
    )
    provider = MockProvider(scripted={"security": _SCRIPTED})
    r = build_records([golden], provider)[0]
    # golden findings normalized to plain dicts with the 6 fields
    assert r.golden_findings == [{
        "file": "app.py", "line_start": 1, "line_end": 1,
        "severity": "high", "category": "security", "message": "issue",
    }]
    # agent findings normalized the same way (from the scripted security node)
    assert r.agent_findings[0]["file"] == "app.py"
    assert r.agent_findings[0]["category"] == "security"
    assert r.agent_findings[0]["message"] == "SQLi"
    assert r.agent_findings[0]["line_start"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_eval_harness.py::test_build_records_carries_structured_findings -v`
Expected: FAIL — `EvalRecord` has no field `golden_findings` (pydantic validation / AttributeError).

- [ ] **Step 3: Write minimal implementation**

In `evals/harness.py`, add the two fields to `EvalRecord`:

```python
class EvalRecord(BaseModel):
    id: str
    user_input: str
    response: str
    retrieved_contexts: list[str]
    reference: str
    agent_findings: list[dict]
    golden_findings: list[dict]
```

Add a normalizer just below `_finding_field` (reuse it for each key):

```python
_FINDING_KEYS = ("file", "line_start", "line_end", "severity", "category", "message")


def normalize_finding(finding) -> dict:
    """Flatten a finding (agent Pydantic model or golden dict) to a plain dict
    with the fields the detection scorer matches on."""
    return {key: _finding_field(finding, key) for key in _FINDING_KEYS}
```

In `build_records`, populate the new fields:

```python
        records.append(
            EvalRecord(
                id=g.id,
                user_input=_INSTRUCTION,
                response=serialize_findings(agent_findings),
                retrieved_contexts=[g.diff],
                reference=reference,
                agent_findings=[normalize_finding(f) for f in agent_findings],
                golden_findings=[normalize_finding(f) for f in g.findings],
            )
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_eval_harness.py -v`
Expected: PASS (all harness tests, including the existing `test_build_records_shapes_one_record_per_golden`).

- [ ] **Step 5: Lint & commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
uv run ruff check evals/harness.py tests/test_eval_harness.py
git add evals/harness.py tests/test_eval_harness.py
git commit -m "feat(evals): carry structured findings on EvalRecord for detection scoring

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Detection scorer — deterministic core

**Files:**
- Create: `evals/detection_scorer.py`
- Test: `tests/test_detection_scorer.py`

**Interfaces:**
- Consumes: `EvalRecord.agent_findings` / `EvalRecord.golden_findings` (Task 1).
- Produces:
  - `PRECISION_PENALTY = 0.2`
  - `finding_matches(agent: dict, golden: dict) -> bool`
  - `score_record(record, *, rescue=None) -> dict` returning `{"id","score","recall","matched","total_goldens","false_positives","total_agent_findings"}`
  - `score_by_detection(records, *, rescue=None) -> list[dict]`
  - `rescue` is `Callable[[dict, list[dict]], bool] | None` (golden_finding, unmatched_agent_findings) → matched? Task 2 leaves it unused/None (deterministic only); Task 3 wires the default.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_detection_scorer.py`:

```python
from evals.detection_scorer import (
    PRECISION_PENALTY,
    finding_matches,
    score_by_detection,
    score_record,
)


def _f(file="a.py", ls=5, le=6, cat="security", sev="high", msg="m"):
    return {"file": file, "line_start": ls, "line_end": le,
            "severity": sev, "category": cat, "message": msg}


class _Rec:
    def __init__(self, id, agent, golden):
        self.id, self.agent_findings, self.golden_findings = id, agent, golden


def test_precision_penalty_is_point_two():
    assert PRECISION_PENALTY == 0.2


def test_matches_on_file_line_overlap_and_category():
    assert finding_matches(_f(ls=5, le=5), _f(ls=5, le=6))  # overlap
    assert finding_matches(_f(ls=6, le=9), _f(ls=5, le=6))  # touching overlap


def test_no_match_on_category_mismatch():
    assert not finding_matches(_f(cat="logic"), _f(cat="security"))


def test_no_match_on_disjoint_lines():
    assert not finding_matches(_f(ls=1, le=2), _f(ls=5, le=6))


def test_no_match_on_different_file():
    assert not finding_matches(_f(file="a.py"), _f(file="b.py"))


def test_perfect_catch_no_noise_scores_one():
    rec = _Rec("x", [_f()], [_f()])
    out = score_record(rec)
    assert out == {"id": "x", "score": 1.0, "recall": 1.0, "matched": 1,
                   "total_goldens": 1, "false_positives": 0,
                   "total_agent_findings": 1}


def test_missed_bug_scores_zero():
    rec = _Rec("x", [_f(ls=1, le=1)], [_f(ls=5, le=6)])
    out = score_record(rec)
    assert out["recall"] == 0.0
    # recall 0, fp_rate 1.0 -> 0 - 0.2 -> clamped to 0.0
    assert out["score"] == 0.0


def test_light_precision_penalty_on_extra_findings():
    # 1 golden caught + 2 noise findings: recall 1, fp_rate 2/3
    rec = _Rec("x", [_f(), _f(cat="logic"), _f(cat="test")], [_f()])
    out = score_record(rec)
    assert out["recall"] == 1.0
    assert out["false_positives"] == 2
    assert round(out["score"], 4) == round(1.0 - 0.2 * (2 / 3), 4)


def test_empty_agent_findings_scores_zero():
    rec = _Rec("x", [], [_f()])
    out = score_record(rec)
    assert out == {"id": "x", "score": 0.0, "recall": 0.0, "matched": 0,
                   "total_goldens": 1, "false_positives": 0,
                   "total_agent_findings": 0}


def test_score_by_detection_maps_all_records():
    recs = [_Rec("a", [_f()], [_f()]), _Rec("b", [], [_f()])]
    out = score_by_detection(recs)
    assert [o["id"] for o in out] == ["a", "b"]
    assert out[0]["score"] == 1.0 and out[1]["score"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_detection_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.detection_scorer'`.

- [ ] **Step 3: Write minimal implementation**

Create `evals/detection_scorer.py`:

```python
from __future__ import annotations

from collections.abc import Callable

PRECISION_PENALTY = 0.2

# rescue(golden_finding, unmatched_agent_findings) -> True if the LLM judges that
# one of the candidates describes the golden issue. None disables the fallback.
Rescue = Callable[[dict, list[dict]], bool]


def finding_matches(agent: dict, golden: dict) -> bool:
    """Deterministic match: same file, overlapping line range, same category."""
    if str(agent["file"]).strip() != str(golden["file"]).strip():
        return False
    if agent["category"] != golden["category"]:
        return False
    return (
        agent["line_start"] <= golden["line_end"]
        and golden["line_start"] <= agent["line_end"]
    )


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_record(record, *, rescue: Rescue | None = None) -> dict:
    agents = list(record.agent_findings)
    goldens = list(record.golden_findings)
    matched_agent_idx: set[int] = set()
    matched_goldens = 0

    for golden in goldens:
        hit = False
        for i, agent in enumerate(agents):
            if finding_matches(agent, golden):
                matched_agent_idx.add(i)
                hit = True
        if not hit and rescue is not None:
            candidates = [a for i, a in enumerate(agents) if i not in matched_agent_idx]
            if candidates and rescue(golden, candidates):
                hit = True
        if hit:
            matched_goldens += 1

    total_goldens = len(goldens)
    total_agents = len(agents)
    recall = matched_goldens / total_goldens if total_goldens else 0.0
    false_positives = total_agents - len(matched_agent_idx)
    fp_rate = false_positives / total_agents if total_agents else 0.0
    score = _clamp(recall - PRECISION_PENALTY * fp_rate)
    return {
        "id": record.id,
        "score": score,
        "recall": recall,
        "matched": matched_goldens,
        "total_goldens": total_goldens,
        "false_positives": false_positives,
        "total_agent_findings": total_agents,
    }


def score_by_detection(records, *, rescue: Rescue | None = None) -> list[dict]:
    return [score_record(r, rescue=rescue) for r in records]
```

Note: `false_positives` counts agent findings that never matched *any* golden (via `matched_agent_idx`), so an LLM rescue that identifies a candidate does not also decrement false positives — a rescued finding still counts as noise-free only if it deterministically matched. This is intentional and keeps the count deterministic-anchored.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_detection_scorer.py -v`
Expected: PASS (all 10 tests).

- [ ] **Step 5: Lint & commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
uv run ruff check evals/detection_scorer.py tests/test_detection_scorer.py
git add evals/detection_scorer.py tests/test_detection_scorer.py
git commit -m "feat(evals): add deterministic detection scorer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Detection scorer — LLM fallback (hybrid)

**Files:**
- Modify: `evals/detection_scorer.py`
- Test: `tests/test_detection_scorer.py`

**Interfaces:**
- Consumes: `score_record(..., rescue=...)` from Task 2; the agent provider protocol `provider.complete(system, user) -> LLMResponse` (has `.text`).
- Produces: `make_groq_rescue(provider) -> Rescue` and `default_rescue() -> Rescue | None` (returns None when `EVAL_LLM_FALLBACK=0`, else a Groq-backed rescue). Used by the runner in Task 5.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_detection_scorer.py`:

```python
import os

from evals.detection_scorer import default_rescue, make_groq_rescue


class _StubProvider:
    def __init__(self, text):
        self._text = text

    def complete(self, system, user):
        class _R:  # minimal LLMResponse stand-in
            pass
        r = _R()
        r.text = self._text
        return r


def test_rescue_rescues_line_drifted_finding():
    # deterministic miss (lines off by 2), rescued by the LLM saying yes
    rec = _Rec("x", [_f(ls=8, le=8)], [_f(ls=5, le=6)])
    rescue = make_groq_rescue(_StubProvider('{"match": true}'))
    out = score_record(rec, rescue=rescue)
    assert out["recall"] == 1.0


def test_rescue_no_when_llm_says_no():
    rec = _Rec("x", [_f(ls=8, le=8)], [_f(ls=5, le=6)])
    rescue = make_groq_rescue(_StubProvider('{"match": false}'))
    out = score_record(rec, rescue=rescue)
    assert out["recall"] == 0.0


def test_rescue_failsafe_on_unparseable_response():
    rec = _Rec("x", [_f(ls=8, le=8)], [_f(ls=5, le=6)])
    rescue = make_groq_rescue(_StubProvider("not json at all"))
    out = score_record(rec, rescue=rescue)
    assert out["recall"] == 0.0  # treated as no match, no crash


def test_rescue_failsafe_on_provider_error():
    class _Boom:
        def complete(self, system, user):
            raise RuntimeError("429 rate limit")

    rec = _Rec("x", [_f(ls=8, le=8)], [_f(ls=5, le=6)])
    out = score_record(rec, rescue=make_groq_rescue(_Boom()))
    assert out["recall"] == 0.0


def test_default_rescue_disabled_by_env(monkeypatch):
    monkeypatch.setenv("EVAL_LLM_FALLBACK", "0")
    assert default_rescue() is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_detection_scorer.py -k rescue -v`
Expected: FAIL — `ImportError: cannot import name 'make_groq_rescue'`.

- [ ] **Step 3: Write minimal implementation**

Add to `evals/detection_scorer.py` (imports at top: `import json`, `import os`):

```python
def _rescue_prompt(golden: dict, candidates: list[dict]) -> str:
    lines = [
        "A golden code-review finding and some candidate findings are given.",
        "Does ANY candidate describe the SAME underlying issue as the golden "
        "(same bug, allowing for different wording or slightly different lines)?",
        'Reply with STRICT JSON only: {"match": true} or {"match": false}.',
        "",
        f"GOLDEN: [{golden['category']}] {golden['file']}:"
        f"{golden['line_start']}-{golden['line_end']} — {golden['message']}",
        "CANDIDATES:",
    ]
    for c in candidates:
        lines.append(
            f"- [{c['category']}] {c['file']}:{c['line_start']}-{c['line_end']} "
            f"— {c['message']}"
        )
    return "\n".join(lines)


def make_groq_rescue(provider) -> Rescue:
    """Build a rescue that asks the provider whether a candidate matches the
    golden. Any error / unparseable reply is treated as no-match (fail-safe)."""
    system = "You are a precise code-review adjudicator."

    def rescue(golden: dict, candidates: list[dict]) -> bool:
        try:
            resp = provider.complete(system, _rescue_prompt(golden, candidates))
            data = json.loads(resp.text)
            return bool(data.get("match") is True)
        except Exception:
            return False

    return rescue


def default_rescue() -> Rescue | None:
    """The runner's default: Groq-backed rescue unless EVAL_LLM_FALLBACK=0."""
    if os.environ.get("EVAL_LLM_FALLBACK", "1") == "0":
        return None
    from agent.providers.factory import make_provider  # noqa: PLC0415

    return make_groq_rescue(make_provider("groq"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_detection_scorer.py -v`
Expected: PASS (all Task 2 + Task 3 tests).

- [ ] **Step 5: Lint & commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
uv run ruff check evals/detection_scorer.py tests/test_detection_scorer.py
git add evals/detection_scorer.py tests/test_detection_scorer.py
git commit -m "feat(evals): add hybrid LLM fallback to detection scorer

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Scoring aggregation & report → score/recall, gate on score

**Files:**
- Modify: `evals/scoring.py`
- Test: `tests/test_eval_scoring.py`

**Interfaces:**
- Consumes: per-item dicts with `score` and `recall` (Task 2).
- Produces: `_METRICS = ("score", "recall")`; `aggregate_scores` means over both; `passes_threshold(scores, threshold)` returns `scores["score"] >= threshold`; `render_report` emits both columns and gates on score. `THRESHOLD` unchanged here (set in Task 5).

- [ ] **Step 1: Rewrite the tests**

Replace the body of `tests/test_eval_scoring.py` with:

```python
from evals.scoring import (
    aggregate_scores,
    passes_threshold,
    render_report,
)

_ITEMS = [
    {"id": "a", "score": 0.9, "recall": 1.0},
    {"id": "b", "score": 0.7, "recall": 0.8},
]


def test_aggregate_means():
    agg = aggregate_scores(_ITEMS)
    assert round(agg["score"], 3) == 0.8
    assert round(agg["recall"], 3) == 0.9


def test_aggregate_empty_is_zero():
    assert aggregate_scores([]) == {"score": 0.0, "recall": 0.0}


def test_passes_threshold_gates_on_score_only():
    # recall below the bar must NOT fail the run; only score gates.
    assert passes_threshold({"score": 0.8, "recall": 0.1}, 0.75)
    assert not passes_threshold({"score": 0.5, "recall": 1.0}, 0.75)


def test_render_report_marks_pass_and_lists_items():
    agg = aggregate_scores(_ITEMS)
    report, md = render_report(agg, _ITEMS, threshold=0.7)
    assert report["threshold"] == 0.7
    assert report["passed"] is True
    assert len(report["items"]) == 2
    assert "PASS" in md
    assert "| a |" in md


def test_render_report_marks_fail():
    items = [{"id": "x", "score": 0.5, "recall": 0.5}]
    report, md = render_report(aggregate_scores(items), items, threshold=0.7)
    assert report["passed"] is False
    assert "FAIL" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_eval_scoring.py -v`
Expected: FAIL — `aggregate_scores` still keys on `faithfulness`, so `agg["score"]` raises `KeyError`.

- [ ] **Step 3: Write minimal implementation**

Rewrite `evals/scoring.py`:

```python
from __future__ import annotations

THRESHOLD = 0.75
_METRICS = ("score", "recall")


def aggregate_scores(per_item: list[dict]) -> dict[str, float]:
    agg: dict[str, float] = {}
    for m in _METRICS:
        values = [item[m] for item in per_item if item.get(m) is not None]
        agg[m] = sum(values) / len(values) if values else 0.0
    return agg


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def passes_threshold(scores: dict[str, float], threshold: float = THRESHOLD) -> bool:
    # Gate on detection score only; recall is reported but not gated.
    return scores["score"] >= threshold


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
        f"- Score: {_fmt(scores['score'])}",
        f"- Recall: {_fmt(scores['recall'])}",
        "",
        "| id | score | recall |",
        "| --- | --- | --- |",
    ]
    for item in per_item:
        lines.append(
            f"| {item['id']} | {_fmt(item.get('score'))} "
            f"| {_fmt(item.get('recall'))} |"
        )
    return report, "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_eval_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Lint & commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
uv run ruff check evals/scoring.py tests/test_eval_scoring.py
git add evals/scoring.py tests/test_eval_scoring.py
git commit -m "feat(evals): score/recall metrics, gate on detection score

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Runner default scorer + threshold re-baseline

**Files:**
- Modify: `evals/run_eval.py`
- Test: `tests/test_eval_runner.py`
- Modify (threshold value): `evals/scoring.py`

**Interfaces:**
- Consumes: `score_by_detection` + `default_rescue` (Tasks 2–3); `run(out_dir, *, provider, scorer, goldens, threshold)` signature unchanged.
- Produces: default scorer is detection-based; `THRESHOLD` re-baselined from the dry-run.

- [ ] **Step 1: Update the runner tests**

In `tests/test_eval_runner.py`, replace the two stub scorers so they return the new metric shape:

```python
def _passing_scorer(records):
    return [{"id": r.id, "score": 0.9, "recall": 0.9} for r in records]


def _failing_scorer(records):
    return [{"id": r.id, "score": 0.5, "recall": 0.5} for r in records]
```

Add an explicit `threshold=0.75` to both `run(...)` calls in that file so they don't depend on the re-baselined default:

```python
    code = run(
        tmp_path, provider=MockProvider(), scorer=_passing_scorer,
        goldens=[_golden("a"), _golden("b")], threshold=0.75,
    )
```
```python
    code = run(
        tmp_path, provider=MockProvider(), scorer=_failing_scorer,
        goldens=[_golden("a")], threshold=0.75,
    )
```

- [ ] **Step 2: Run tests to verify they still pass (shape change only)**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && uv run pytest tests/test_eval_runner.py -v`
Expected: PASS (the runner is scorer-agnostic; these use injected scorers).

- [ ] **Step 3: Switch the runner's default scorer**

In `evals/run_eval.py`, replace the lazy default (lines ~18–20):

```python
    if scorer is None:
        from evals.detection_scorer import default_rescue, score_by_detection

        rescue = default_rescue()
        scorer = lambda records: score_by_detection(records, rescue=rescue)  # noqa: E731
```

- [ ] **Step 4: Run the full Python suite (offline)**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && LLM_PROVIDER=mock uv run pytest -q`
Expected: PASS (no network; detection scorer default is only constructed when `scorer is None`, which the injected-scorer tests avoid).

- [ ] **Step 5: Dry-run over the 20 goldens to gather the score distribution**

Load `.env` (real Groq agent) and run the detection scorer end-to-end:

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
set -a && source .env && set +a
uv run python -m evals.run_eval --out-dir evals/reports --provider groq --threshold 0.0
```

Read the newest `evals/reports/NNN.md`. Record the aggregate **Score** and the per-item spread. (Using `--threshold 0.0` guarantees a pass so the run always writes a report to inspect.)

- [ ] **Step 6: Set the re-baselined threshold**

Pick `THRESHOLD` a little below the observed aggregate Score for these known-correct reviews, with headroom (e.g. if aggregate Score is ~0.85, set 0.75; if ~0.70, set 0.60). In `evals/scoring.py` set:

```python
THRESHOLD = <chosen value>
```

Document the observed distribution and the chosen value in the commit message.

- [ ] **Step 7: Verify the gate passes at the real threshold**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
set -a && source .env && set +a
uv run python -m evals.run_eval --out-dir evals/reports --provider groq
echo "exit=$?"
```
Expected: `exit=0` and the report header reads `# Eval Report — PASS`.

- [ ] **Step 8: Lint & commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
uv run ruff check evals/run_eval.py evals/scoring.py tests/test_eval_runner.py
git add evals/run_eval.py evals/scoring.py tests/test_eval_runner.py
git commit -m "feat(evals): default to detection scorer, re-baseline threshold

Dry-run over the 20 goldens with the Groq agent produced aggregate
score ~<X>; threshold set to <Y> with headroom.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Dashboard — read score/recall

**Files:**
- Modify: `web/src/api.ts`, `web/src/evals/ReportTable.tsx`, `web/src/evals/VerdictBanner.tsx`, `web/src/evals/TrendChart.tsx`, `web/src/evals/MetricGuide.tsx`
- Test: `web/src/evals/ReportTable.test.tsx`, `web/src/evals/EvalAnalytics.test.tsx`

**Interfaces:**
- Consumes: report JSON with `aggregate: {score, recall}` and items `{id, score, recall, ...}` (Task 4).
- Produces: dashboard components that render `score`/`recall`, gating visuals on `score`.

- [ ] **Step 1: Update the failing tests first**

In `web/src/evals/ReportTable.test.tsx`, replace the fixtures + null test:

```tsx
const report: EvalReport = {
  aggregate: { score: 0.8, recall: 0.9 },
  threshold: 0.75,
  passed: true,
  items: [
    { id: "ok", score: 0.75, recall: 1.0 },
    { id: "bad", score: 0.74, recall: 1.0 },
  ],
};

it("marks rows pass/fail at the threshold on score", () => {
  render(<ReportTable report={report} />);
  expect(screen.getByText("ok").closest("tr")).toHaveAttribute("data-status", "pass");
  expect(screen.getByText("bad").closest("tr")).toHaveAttribute("data-status", "fail");
});

it("passes a row on score even when recall is low", () => {
  const r: EvalReport = {
    aggregate: { score: 0.8, recall: 0.5 },
    threshold: 0.75,
    passed: true,
    items: [{ id: "hi", score: 0.9, recall: 0.2 }],
  };
  render(<ReportTable report={r} />);
  expect(screen.getByText("hi").closest("tr")).toHaveAttribute("data-status", "pass");
});
```

In `web/src/evals/EvalAnalytics.test.tsx`, replace every `{ faithfulness: X, answer_correctness: Y }` with `{ score: X, recall: Y }` (aggregate objects at lines 24, 27, 39, 40, 43; item objects at lines 30, 46).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment/web" && npm test -- --run`
Expected: FAIL — TS type errors (`score` not in `EvalAggregate`) / assertions on old fields.

- [ ] **Step 3: Update types in `web/src/api.ts`**

```ts
export interface EvalAggregate {
  score: number;
  recall: number;
}
```
```ts
export interface EvalItem {
  id: string;
  score: number;
  recall: number;
}
```

- [ ] **Step 4: Update `ReportTable.tsx`**

Use the report's own threshold, gate on score, drop the null path:

```tsx
import type { EvalReport } from "../api";
import { ScoreMeter } from "./ScoreMeter";

const fmt = (v: number) => v.toFixed(2);

function ScoreCell({ value, threshold }: { value: number; threshold: number }) {
  return (
    <div className="cell-score">
      <ScoreMeter value={value} threshold={threshold} height={8} />
      <span className="num">{fmt(value)}</span>
    </div>
  );
}

export function ReportTable({ report }: { report: EvalReport }) {
  const threshold = report.threshold;
  return (
    <table className="report-table">
      <thead>
        <tr>
          <th className="col-id">diff</th>
          <th className="col-metric">score</th>
          <th className="col-metric">recall</th>
          <th>result</th>
        </tr>
      </thead>
      <tbody>
        {report.items.map((it) => {
          const pass = it.score >= threshold;
          const status = pass ? "pass" : "fail";
          return (
            <tr key={it.id} className={status} data-status={status}>
              <td className="col-id">{it.id}</td>
              <td className="col-metric">
                <ScoreCell value={it.score} threshold={threshold} />
              </td>
              <td className="col-metric">
                <ScoreCell value={it.recall} threshold={threshold} />
              </td>
              <td>
                <span className="pill" data-status={status}>
                  {pass ? "pass" : "fail"}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 5: Update `VerdictBanner.tsx`**

Change the `cleared` filter and the two meters:

```tsx
  const cleared = report.items.filter((it) => it.score >= report.threshold).length;
```
```tsx
      <div className="verdict-metrics">
        <VerdictMetric
          name="Score"
          value={report.aggregate.score}
          threshold={report.threshold}
        />
        <VerdictMetric
          name="Recall"
          value={report.aggregate.recall}
          threshold={report.threshold}
        />
      </div>
```

- [ ] **Step 6: Update `TrendChart.tsx`**

```tsx
  const data = reports.map((r) => ({
    id: `run ${r.id}`,
    Score: r.aggregate.score,
    Recall: r.aggregate.recall,
  }));
```
Rename the two `<Line>` dataKeys to `"Score"` and `"Recall"` (keep the existing colors), e.g.:
```tsx
        <Line type="monotone" dataKey="Score" stroke={FAITHFULNESS} strokeWidth={2} dot={{ r: 4 }} />
        <Line type="monotone" dataKey="Recall" stroke={CORRECTNESS} strokeWidth={2} dot={{ r: 4 }} />
```
(The `FAITHFULNESS`/`CORRECTNESS` color consts may be renamed to `SCORE`/`RECALL` for clarity — optional.)

If the re-baselined `THRESHOLD` (Task 5) is not 0.75, update the `ReferenceLine y={0.75}` and its `"pass bar 0.75"` label in `TrendChart.tsx` to the chosen value so the dashed pass bar matches the backend gate.

- [ ] **Step 7: Update `MetricGuide.tsx` copy**

Replace the two metric cards and drop the `n/a` note:

```tsx
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Score</h3>
        <p>
          Did the agent catch the known bug in each diff, with a small penalty for
          noisy extra findings? This is the number the pass bar gates on.
        </p>
      </div>
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Recall</h3>
        <p>
          The share of the golden findings the agent detected — how many real issues
          it caught, ignoring any extra noise.
        </p>
      </div>
      <p className="guide-note">
        <span>
          <b>Pass bar {threshold.toFixed(2)}</b> — an item passes when its score
          reaches the bar; the run passes when the average score does.
        </span>
      </p>
```

- [ ] **Step 8: Run the dashboard suite + typecheck/build**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment/web" && npm test -- --run && npm run build`
Expected: all Vitest tests PASS and the Vite/tsc build succeeds with no type errors.

- [ ] **Step 9: Commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
git add web/src/api.ts web/src/evals/ReportTable.tsx web/src/evals/VerdictBanner.tsx web/src/evals/TrendChart.tsx web/src/evals/MetricGuide.tsx web/src/evals/ReportTable.test.tsx web/src/evals/EvalAnalytics.test.tsx
git commit -m "feat(web): dashboard reads detection score/recall

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Clean up stale reports & final full verification

**Files:**
- Delete: stale `evals/reports/*.json|*.md` from the old RAGAS format (keep only the fresh detection-format report from Task 5 Step 7).

**Interfaces:** none.

- [ ] **Step 1: Remove old-format reports**

The old `001`/`002` reports use `faithfulness`/`answer_correctness` and will render wrong in the updated dashboard. Delete every report except the newest (detection-format) one:

```bash
cd "/Users/ztlab104/demo projects/ai_assignment/evals/reports"
ls -t
# Remove old-format reports (inspect first); e.g.:
rm -f 001.json 001.md 002.json 002.md
```
Confirm the remaining report's JSON has `"aggregate": {"score": ..., "recall": ...}`.

- [ ] **Step 2: Full offline test sweep**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment" && LLM_PROVIDER=mock uv run pytest -q && uv run ruff check .`
Expected: all tests PASS, ruff clean.

- [ ] **Step 3: Dashboard sweep**

Run: `cd "/Users/ztlab104/demo projects/ai_assignment/web" && npm test -- --run`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
cd "/Users/ztlab104/demo projects/ai_assignment"
git add -A evals/reports
git commit -m "chore(evals): drop stale RAGAS-format reports

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review notes

- **Spec coverage:** structured findings (Task 1) ✓; hybrid deterministic+LLM match (Tasks 2–3) ✓; recall-weighted light-precision formula (Task 2) ✓; gate on score, RAGAS ungated (Tasks 4–5) ✓; dry-run re-baseline (Task 5) ✓; dashboard update (Task 6) ✓; RAGAS code retained (default swapped in Task 5, `ragas_scorer.py` untouched) ✓.
- **Downstream note from spec** (agent duplicating security→logic findings; 8b agent model) is explicitly out of scope and left as follow-ups.
- **Type consistency:** `finding_matches`, `score_record(record, *, rescue=None)`, `score_by_detection(records, *, rescue=None)`, `make_groq_rescue`, `default_rescue`, and the `{score,recall,...}` item shape are used identically across Python tasks; TS `EvalAggregate {score,recall}` / `EvalItem {id,score,recall}` are used identically across dashboard files.
