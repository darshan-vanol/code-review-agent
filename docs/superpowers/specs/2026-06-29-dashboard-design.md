# Plan 4 — Dashboard (Review Playground + Eval Analytics)

**Date:** 2026-06-29
**Status:** Approved design (pre-implementation)
**Builds on:** `2026-06-24-code-review-agent-design.md` §8 (Dashboard). This is the
last of the four implementation plans; Plans 1–3 (agent core, API+GitHub+Langfuse,
eval harness+CI) are complete and merged to `main`.

## 1. Goal

A `web/` package — a **Vite + React + TypeScript** single-page app — that is the
demo surface for the Code Review Assistant. Two views:

1. **Review Playground** — paste a PR diff *or* enter a GitHub PR URL → call
   `POST /review` → render annotated findings, a score gauge, and per-node spans.
2. **Eval Analytics** — read RAGAS eval reports from the API → score trends across
   runs and a per-PR drill-down table, gated visually at the 0.75 threshold.

The dashboard reads as production-ready: clean component boundaries, honest data
(no faked links or stub data paths), graceful empty/error states.

## 2. Locked Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Stack | **Vite + React + TS** | Locked by parent spec §1. Fast dev loop, standard demo stack. |
| Eval data source | **New API endpoints** | `GET /eval/reports` + `GET /eval/reports/{id}` serve the existing `evals/reports/*.json`. Live and always current; one origin. Chosen over build-time copy (stale) or dev-only proxy. |
| Streaming | **No streaming** | Single `POST /review` + spinner. Spec §8 marks streaming nice-to-have; the agent/API don't stream today. YAGNI. |
| Styling | **Hand-rolled CSS + Recharts** | Plain CSS (CSS Modules) + Recharts for the one trend chart. Lean dep tree, distinctive look, no heavy UI framework. |
| Demo data | **Real provider for the demo** | Mock returns empty findings. The README/demo script runs the API with a real provider (Groq/Gemini) to populate the playground. No mock-data code path in `web/`. |
| Langfuse links | **Single project link, env-gated** | Report items carry only `{id, faithfulness, answer_correctness}` — no per-trace IDs today. Show one "Open in Langfuse" link (only when a base URL is configured) rather than 20 broken per-row deep-links. |

## 3. Backend Additions (the only changes outside `web/`)

The agent and eval harness are untouched. Three small additions to `api/`:

1. **CORS middleware** on the FastAPI app, allowing the Vite dev origin
   (`http://localhost:5173`), configurable via an env var with that default.
   Currently the API has no CORS, so the browser can't call it.
2. **`GET /eval/reports`** → `list[{id, passed, aggregate}]`. `id` is the report
   filename stem (reports are written as `{n}.json` by `evals/run_eval.py`).
   Returns `[]` when the reports dir is empty or missing — never 500s.
3. **`GET /eval/reports/{id}`** → the full report JSON
   (`{aggregate, threshold, passed, items}`). 404 on unknown id.

Both endpoints read from the existing reports directory (path configurable, default
`evals/reports`). They do not change the report file shape or the harness.

## 4. Data Contracts (authoritative, from Plans 1–3)

**`POST /review` → `ReviewResponse`:**
```
is_trivial: bool
score: { overall: float (0..1 cleanliness), counts: {info,low,medium,high,critical: int} } | null
security_findings:  Finding[]
logic_findings:     Finding[]
test_suggestions:   Finding[]
token_usage: { input_tokens, output_tokens, latency_ms }
spans: { name, latency_ms, input_tokens, output_tokens }[]
errors: string[]
```
**`Finding`:** `{ file, line_start, line_end, severity (info|low|medium|high|critical), category, message, suggestion }`

**`POST /review` request:** exactly one of `{ diff }` or `{ pr_url }` (the API's
`exactly_one_input` validator returns 422 otherwise).

**Eval report (`{n}.json`):** `{ aggregate: {faithfulness, answer_correctness}, threshold: 0.75, passed: bool, items: {id, faithfulness, answer_correctness}[] }`

## 5. Review Playground

- **Input card:** a segmented toggle (Diff | PR URL); a textarea for the diff or a
  text field for the URL. Submit sends exactly the selected one, matching the API
  contract. Disabled while in flight.
- **Loading:** spinner / skeleton while the single `POST /review` is pending.
- **Result:**
  - **Score gauge** — `score.overall` as a radial/bar gauge (1.0 = clean), with the
    per-severity `counts` as colored chips.
  - **Findings** grouped by file, then category. Each: severity badge (info→critical
    color scale), `file:line_start-line_end`, message, suggestion.
  - **Trivial diffs** — when `is_trivial`, show a "deep analysis skipped (trivial
    diff)" notice instead of empty finding sections.
  - **Spans panel** (collapsible) — `spans[]` as a per-node latency + token table;
    the in-page observability story when Langfuse isn't wired in the demo.
  - **Errors** — render `errors[]` as inline warnings; the page never blank-screens
    on a partial/failed review.

## 6. Eval Analytics

- **Trend chart** (Recharts line): `aggregate.faithfulness` and
  `aggregate.answer_correctness` across all reports, ordered by id, with the **0.75
  threshold drawn as a reference line**.
- **Per-PR drill-down table:** for a selected report, list `items[]` (id + both
  scores), each row colored pass/fail against 0.75.
- **Langfuse:** a single "Open in Langfuse" link, rendered only when a base URL is
  configured via a build-time env var (e.g. `VITE_LANGFUSE_URL`); hidden otherwise.
- **Empty state:** when `GET /eval/reports` returns `[]`, show a friendly "no eval
  runs yet — run `python -m evals.run_eval`" message, not a broken chart.

## 7. Project Shape

```
web/
├── index.html
├── package.json            # vite, react, react-dom, typescript, recharts; vitest + RTL (dev)
├── vite.config.ts          # dev server + proxy /review,/eval to the API (dev convenience)
├── tsconfig.json
├── src/
│   ├── main.tsx            # router: / (playground), /evals (analytics)
│   ├── api.ts              # typed fetch wrappers + TS types mirroring §4 contracts
│   ├── playground/
│   │   ├── Playground.tsx
│   │   ├── ReviewForm.tsx          # diff | pr_url toggle, one-of enforcement
│   │   ├── ScoreGauge.tsx
│   │   ├── FindingsList.tsx        # grouped by file -> category, severity badges
│   │   └── SpansPanel.tsx
│   ├── evals/
│   │   ├── EvalAnalytics.tsx
│   │   ├── TrendChart.tsx          # Recharts + 0.75 reference line
│   │   └── ReportTable.tsx
│   └── components/         # SeverityBadge, Spinner, EmptyState, shared CSS
└── src/**/*.test.tsx       # Vitest + React Testing Library
```

API side (existing files):
- `api/main.py` — add CORS middleware + the two `/eval/reports` routes.
- `api/schemas.py` — add `EvalReportSummary` response model.
- `tests/test_eval_endpoints.py` — new pytest for the endpoints + CORS header.

## 8. Testing Strategy

- **Frontend (Vitest + RTL):** `fetch` is stubbed — no live backend.
  - ReviewForm sends exactly one of diff/pr_url per the toggle.
  - FindingsList groups by file/category and maps severity → badge.
  - Trivial-diff and `errors[]` states render their notices.
  - ReportTable colors rows pass/fail at the 0.75 boundary; TrendChart draws the
    reference line.
  - EmptyState renders when the reports list is empty.
- **Backend (pytest):** `/eval/reports` lists summaries and 404s on unknown id,
  reading from a tmp reports dir; CORS header present on a preflight/response.

## 9. Out of Scope (YAGNI)

- Streaming node progress (confirmed out).
- Auth / multi-user.
- Building or gating `web/` in CI — it's the demo surface, built and run locally.
- Persisting reviews; per-item Langfuse trace IDs (would require an eval-harness
  change — note for a future iteration, not this plan).
- Bundling the SPA inside FastAPI for single-process serving (dev runs Vite + API
  separately; can be added later if a single-binary demo is wanted).

## 10. Deliverables Mapping

| Parent-spec item | Satisfied by |
|---|---|
| §8 Review playground (diff or PR URL, badges, grouping, score gauge) | §5 |
| §8 Eval analytics (trends, drill-down, faithfulness/correctness, Langfuse) | §6 |
| Walkthrough demo video (parent §10) | Real-provider demo run (§2 Demo data) drives both views |
