# Project presentation — design

**Date:** 2026-07-02
**Status:** Approved

## Goal

An 8-10 slide presentation of the Code Review Assistant project for an
assignment review, emphasizing the two things the assignment is graded on:
the **evaluation harness** (including the RAGAS → detection-scorer pivot) and
**Langfuse observability**. Deliverable is a single self-contained HTML file,
hostable on GitHub Pages so it has a permanent shareable link.

## Format & delivery

- Single self-contained HTML file — inline CSS/JS, no external CDNs/fonts
  (matches Artifact constraints and keeps it portable to GitHub Pages).
- Slide-deck UX: arrow-key navigation, on-screen prev/next controls, slide
  counter (e.g. "3 / 10").
- `@media print` rules so it also exports cleanly to PDF as a fallback (one
  slide per printed page).
- Workflow: iterate via Claude Artifact preview for fast feedback, then commit
  the final file into the repo at `docs/presentation/index.html` so the user
  can enable GitHub Pages (serve from `/docs`) and get a permanent
  `https://<user>.github.io/<repo>/presentation/` link.

## Visual style

Dark, terminal/observability-themed — fits the subject matter (tracing,
metrics, CI gates). Monospace for code snippets, numbers, and metric values;
clean sans-serif for prose. Consistent accent palette reused across slides:
green = pass/recall/good, amber or red = gate failure / the problem being
described. Consistent header/footer treatment with the slide counter.

## Content outline (10 slides)

1. **Title** — "Code Review Assistant" — LangGraph agent, evaluation harness,
   Langfuse observability. Subtitle noting it's an AI code-review agent built
   on LangGraph + FastAPI.

2. **Problem statement** — Two problems framed explicitly:
   (a) How do you know an AI code-review agent is actually good — repeatably,
   offline, in a way that can gate CI?
   (b) How do you see inside a multi-step LLM agent — which step produced
   what, at what token cost and latency?

3. **The RAGAS detour** — Narrative: started with RAGAS, the standard
   LLM/RAG eval framework, since it's the established tool for this kind of
   problem. Show the real measured numbers verbatim:
   **faithfulness 0.270 / answer_correctness 0.400** against a **0.75** gate,
   with a strong judge model (`llama-3.3-70b-versatile`) — even though manual
   inspection confirmed the agent's findings were correct (SQL injection,
   hardcoded secret, null-deref, SSRF all detected and matching goldens).

4. **Root cause** — RAGAS is built for **RAG** systems:
   - `faithfulness` checks whether output claims are entailed by *retrieved
     context* — a code review is analytical inference, not extraction, so a
     strict NLI judge marks it unsupported (test-coverage suggestions like
     "missing test for X" are provably not present in the diff text at all).
   - `answer_correctness` compares against a **single canonical reference
     answer** — the agent correctly returns 3-4 findings per case, and each
     extra (correct) finding is counted as a false positive against a
     one-finding reference, tanking the F1-based score.
   Headline takeaway, quoted from the project's own design doc: *"A perfect
   reviewer cannot clear the gate. The eval measures the wrong thing."* Frame
   as the real lesson: match the eval to the task instead of defaulting to
   the most popular framework — and understand *why* a metric is failing
   before assuming the system under test is broken.

5. **Solution — detection-based eval harness** —
   - Deterministic match per golden finding: same file, overlapping line
     range, same category.
   - Hybrid LLM "rescue" fallback for anything left unmatched (one Groq call
     per residual golden; fail-safe — any error or non-parse treated as no
     match, so a flaky judge can only rescue a miss, never downgrade a
     deterministic match).
   - Score formula, shown verbatim: `recall = matched / total_goldens`,
     `score = clamp(recall − 0.2 × false_positive_rate, 0, 1)`.
   - 20 hand-authored golden cases spanning security / logic / test-coverage
     across Python, JS, and Go.
   - Gates CI at aggregate `score ≥ 0.75`; `recall` reported but not gated.

6. **Solution — Langfuse observability** —
   - One trace per review; one span per LangGraph node.
   - LLM nodes emit as `generation` observations carrying model name +
     input/output token counts, so Langfuse auto-populates the model column
     and computes cost + latency; deterministic nodes (`ingest`, `aggregate`)
     emit as plain `span`.
   - Three-tier tracer architecture — `NoOpTracer` → `RecordingTracer` →
     `LangfuseTracer` — so per-node spans are *always* returned inline in the
     API response even when Langfuse is disabled; Langfuse is purely
     additive, never a dependency for basic visibility.

7. **Key features** — golden dataset + CI gate with PR comment; resilient LLM
   nodes (retry once, degrade to empty findings rather than crash); a
   provider-agnostic adapter layer (`mock` / `groq` / `gemini` behind one
   `LLMProvider` protocol); a live dashboard (Review Playground +
   Eval Analytics with score trend charts).

8. **Tech stack** — grouped by layer:
   - Agent core: LangGraph, LangChain-core, Pydantic v2
   - API: FastAPI, Uvicorn
   - LLM providers: Groq, Gemini, mock (offline default)
   - Evaluation: custom detection scorer (default); RAGAS + fastembed kept in
     the repo as a documented, non-gating alternative
   - Observability: Langfuse SDK
   - Frontend: Vite, React, TypeScript
   - CI/tooling: GitHub Actions, `uv`

9. **Architecture at a glance** — one diagram: `ingest` → `[security → logic
   → test_coverage]` → `aggregate`, annotated with where the tracer attaches
   (span/generation per node) and where the eval harness hooks in (calls the
   same `run_review()` the API uses — what you evaluate is what you ship).

10. **Takeaways / what's next** — RAGAS code was deliberately *kept, not
    deleted* — a documented, reversible decision rather than a silent
    rewrite. Next steps called out in the project's own docs: dedupe
    overlapping security/logic findings (a known noise source), re-baseline
    the threshold against a stronger agent model.

## Data sources (for accuracy — pull verbatim where noted above)

- `README.md` — Evaluation and Observability-with-Langfuse sections
- `docs/ARCHITECTURE.md` — graph diagram, tracer architecture, eval harness
  flow diagram
- `docs/superpowers/specs/2026-07-01-detection-based-eval-scorer-design.md` —
  RAGAS failure numbers, root cause analysis, score formula, decisions table
- `pyproject.toml` — dependency list for the tech stack slide

## Out of scope

- Live demo / screen recordings / embedded video
- Actual .pptx or Google Slides export
- Speaker notes script
- Analytics/tracking on the hosted page

## Hosting

Final HTML lands at `docs/presentation/index.html` in this repo. A short note
(not part of the slide content) will remind the user how to flip on GitHub
Pages (Settings → Pages → deploy from `/docs`).
