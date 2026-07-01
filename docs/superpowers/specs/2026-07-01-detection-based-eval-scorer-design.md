# Detection-based eval scorer — design

**Date:** 2026-07-01
**Status:** Approved (pending spec review)
**Branch:** `fix/eval-groq-resilience`

## Problem

The RAGAS eval gate fails even though the agent produces correct reviews. With a
strong `llama-3.3-70b-versatile` judge, serialized (`RAGAS_MAX_WORKERS=1`), the
last run scored **faithfulness 0.270 / answer_correctness 0.400** against a 0.75
gate. Inspection of the actual agent output confirmed the reviews are correct
(SQL injection, hardcoded secret, null-deref, SSRF all detected and matching the
goldens).

Root cause is a **metric–task mismatch**, not agent quality or judge config:

- `faithfulness` measures whether response claims are *entailed by the retrieved
  context* (the raw diff). A review is analytical inference, not an extraction,
  so a strict NLI judge marks it unsupported. Worse, `build_records` concatenates
  the security + logic + **test-coverage** node outputs; "Missing test for X" is
  provably not in the diff, so every test suggestion scores as unfaithful.
- `answer_correctness` compares the multi-finding response (3–4 findings, incl.
  duplicated security/logic) against a reference with **one** canonical finding,
  so extra findings count as false positives → low F1 → ~0.4.

A perfect reviewer cannot clear the gate. The eval measures the wrong thing.

## Goal

Replace the gated metric with a **detection-based scorer** that measures what we
care about: *did the agent catch the golden bug, without excessive noise?* Keep
it reproducible and resilient to the Groq rate-limit flakiness that triggered the
original investigation.

## Decisions (from brainstorming)

| Decision | Choice |
| --- | --- |
| Match method | **Hybrid**: deterministic first, LLM fallback for unmatched goldens |
| Score formula | **Recall-weighted, light precision** |
| Threshold | **Dry-run then re-baseline** |
| RAGAS | **Remove as the gate, keep the code** (not wired to the gate) |
| Dashboard | **Update in scope** |

## Dataset facts

20 goldens, each with exactly **one** canonical finding. Categories align with
the agent's three graph nodes: 6 `security`, 8 `logic`, 6 `test`. Each finding
has `file`, `line_start`, `line_end`, `severity`, `category`, `message`.

## Architecture

### 1. Carry structured findings (harness change)

`EvalRecord` currently holds only serialized *strings* (`response`, `reference`),
discarding the structured file/line/category data needed for matching. Extend the
record to also carry structured findings:

```python
class EvalRecord(BaseModel):
    id: str
    user_input: str
    response: str            # kept, for report/debug
    retrieved_contexts: list[str]
    reference: str           # kept, for report/debug
    agent_findings: list[dict]   # NEW: normalized {file,line_start,line_end,category,severity,message}
    golden_findings: list[dict]  # NEW: the golden's findings, same shape
```

`build_records` normalizes both the agent's Pydantic findings and the golden
dicts into plain dicts via the existing `_finding_field` helper. The serialized
strings remain for human-readable reports.

### 2. New scorer: `evals/detection_scorer.py`

`score_by_detection(records: list[EvalRecord]) -> list[dict]`.

**Deterministic match.** An agent finding matches a golden finding when **all**
hold:
- same `file` (string-normalized: strip whitespace, compare exact)
- line-range overlap: `agent.line_start <= golden.line_end and golden.line_start <= agent.line_end`
- same `category`

Severity is **not** required for a match (recorded for debugging only).

**LLM fallback (hybrid).** For each golden finding still unmatched after the
deterministic pass, make **one** Groq call listing the remaining (unmatched)
agent findings and asking whether any describes the golden issue (yes/no + which).
Reuses the agent provider / `ChatGroq` with the existing `max_retries` handling.
On any error or non-parseable response, treat as **no match** (fail-safe: the
deterministic result stands; a flaky judge can never *lower* a deterministic
match, only rescue a miss). Configurable off via `EVAL_LLM_FALLBACK=0` for a
fully offline run.

**Per-item score (recall-weighted, light precision).**
```
recall   = matched_goldens / total_goldens                     # in [0,1]
fp_rate  = unmatched_agent_findings / max(total_agent_findings, 1)
score    = clamp(recall - PRECISION_PENALTY * fp_rate, 0, 1)    # PRECISION_PENALTY = 0.2
```
Returns per item: `{"id", "score", "recall", "matched", "total_goldens",
"false_positives", "total_agent_findings"}`. `score` and `recall` are always
finite (deterministic) — no NaN/null handling needed.

### 3. Scoring aggregation & gate (`evals/scoring.py`)

- `_METRICS` becomes `("score", "recall")`.
- Gate on **`score` only** (`passes_threshold` checks `scores["score"] >= threshold`);
  `recall` is reported but not gated.
- `render_report` emits both columns; drop the `n/a` path (values are always
  finite) but keep `_fmt` tolerant.
- Report JSON shape (backward-compatible structure, new field names):
  ```json
  {
    "aggregate": {"score": 0.9, "recall": 0.95},
    "threshold": 0.7,
    "passed": true,
    "items": [{"id": "...", "score": 0.9, "recall": 1.0, "matched": 1,
               "total_goldens": 1, "false_positives": 2, "total_agent_findings": 3}]
  }
  ```

### 4. Runner (`evals/run_eval.py`)

Default `scorer` becomes `score_by_detection` (imported lazily). `ragas_scorer.py`
stays in the repo but is no longer the default and no longer gates the build.
`--scorer ragas` may be added later if wanted (not required now).

### 5. Threshold re-baseline

Implement, then dry-run on all 20 goldens (agent = current Groq 8b). Observe the
mean `score` for the (known-correct) reviews and set `THRESHOLD` just below it
with headroom. Record the chosen value and the observed distribution in the PR /
report. Expectation: correct detection should land well above the RAGAS ~0.3.

### 6. Dashboard (`web/src/…`)

Two numeric metrics are preserved (`score`, `recall`), so the existing
two-column table / two-series chart / two-meter layout maps 1:1 with relabeling:

- `web/src/api.ts` — rename `EvalAggregate` + item fields to `score` / `recall`
  (both `number`, non-null).
- `ReportTable.tsx` — column headers → `score` / `recall`; per-row pass check →
  `meets(it.score)` only (recall informational).
- `VerdictBanner.tsx` — two meters → `score` / `recall`; `cleared` count →
  items with `score >= threshold`.
- `TrendChart.tsx` — series → `Score` / `Recall`.
- `MetricGuide.tsx` — rewrite copy to explain detection score & recall.
- Tests `EvalAnalytics.test.tsx`, `ReportTable.test.tsx` — update fixtures to the
  new field names.

## Error handling

- LLM fallback failures degrade to "no match" (never crash the eval, never lower
  a deterministic match).
- Missing/malformed golden or agent finding fields → normalization raises a clear
  error at `build_records` time (fail fast on bad data, before scoring).
- Deterministic path has no external dependency, so a fully offline dry-run
  (`EVAL_LLM_FALLBACK=0`, `LLM_PROVIDER=mock`) is possible for unit tests.

## Testing

- **Unit (scorer):** synthetic records — exact match, line-overlap match,
  category-mismatch (no match), off-by-lines rescued by fallback (mock the
  fallback), false-positive penalty math, empty-agent-findings (score 0),
  clamping. No network.
- **Unit (scoring/report):** aggregate mean, gate on `score` only, report JSON +
  markdown shape.
- **Dashboard:** update existing Vitest suites to new field names; assert the
  gate coloring keys off `score`.
- **Integration (manual):** the dry-run over 20 goldens (also serves as the
  re-baseline data).

## Out of scope

- Changing the agent (its output is already correct for these goldens).
- Deleting `ragas_scorer.py`.
- Deduplicating the agent's security/logic findings (a real quality issue, but
  the light precision penalty already accounts for the noise; separate work).

## Downstream / follow-ups

- The agent duplicating security findings into the logic node (items 01, 02) is
  genuine noise worth a separate fix.
- `.env` still runs the agent-under-test on `llama-3.1-8b-instant`; fine for the
  gate, but a stronger agent model would raise scores further.
