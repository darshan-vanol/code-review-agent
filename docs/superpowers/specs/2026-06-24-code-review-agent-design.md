# Code Review Assistant — LangGraph + Langfuse + Eval Harness

**Date:** 2026-06-24
**Status:** Approved design (pre-implementation)
**Assignment:** LangGraph + Langfuse — Build an Observable AI Agent with Evaluation Harness

## 1. Goal

Build a *Code Review Assistant*: a multi-step AI agent that accepts a GitHub PR
diff, runs structured review steps (security check → logic analysis → test
coverage suggestion), and returns annotated feedback as JSON. The agent is
orchestrated with **LangGraph**, observed with **Langfuse**, and gated by a
**RAGAS** evaluation harness running in CI against a golden dataset of 20 PRs.

The project must read as *production-ready* to evaluators: clean separation of
concerns, real observability, a real eval gate, and a polished demo.

## 2. Locked Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Language / API | **Python + FastAPI** | Strongest LangGraph + RAGAS ecosystem. Brief says NestJS; we deviate intentionally and document it. Agent core is framework-agnostic so a NestJS shell could wrap it later. |
| LLM access | **Adapter layer** + deterministic **mock** | `LLMProvider` interface with Groq / Gemini / OpenAI / Anthropic implementations. Mock provider makes the whole system run offline and keeps CI cheap. Swap providers via one env var. |
| Demo surface | **Rich React dashboard** | Live review view + eval analytics. Highest wow-factor for the demo video. |
| Architecture | **Monorepo, 3 packages** (`agent/`, `api/`, `web/`) + `evals/` | Agent testable in isolation; API is a thin shell; textbook separation of concerns. |
| Timeline | ~1 week, all 5 deliverables | Comfortable pace with polish. |

### Note on the NestJS deviation
The brief specifies NestJS. We build in Python/FastAPI because LangGraph and
RAGAS are first-class there, which de-risks the eval deliverable (the hardest
one). The agent package has zero web-framework dependencies, so the same graph
could be exposed from a NestJS controller. This trade-off will be stated plainly
in the README.

## 3. Architecture

```
repo/
├── agent/                # pure Python, no web deps
│   ├── graph.py          # LangGraph StateGraph definition + wiring
│   ├── state.py          # ReviewState TypedDict / pydantic model
│   ├── nodes/            # one module per node
│   │   ├── ingest.py
│   │   ├── security_scan.py
│   │   ├── logic_analysis.py
│   │   ├── test_coverage.py
│   │   └── aggregate.py
│   ├── providers/        # LLM adapter layer
│   │   ├── base.py       # LLMProvider protocol
│   │   ├── groq.py  gemini.py  openai.py  anthropic.py
│   │   └── mock.py       # deterministic, offline, used in tests + CI unit stage
│   ├── prompts/          # versioned prompt templates (one file per node)
│   └── observability.py  # Langfuse setup + per-node span helpers
├── api/                  # thin FastAPI layer
│   ├── main.py           # app + routes
│   ├── github.py         # PR URL -> unified diff (GitHub REST API)
│   └── schemas.py        # request/response pydantic models
├── web/                  # Vite + React + TS dashboard
├── evals/
│   ├── golden/           # 20 PR diffs + ground-truth review JSON
│   ├── run_eval.py       # RAGAS harness CLI
│   └── reports/          # generated JSON + markdown reports
├── .github/workflows/ci.yml
├── docker-compose.yml    # local Langfuse (optional self-host) + app
└── README.md
```

**Data flow:** client → `POST /review` (FastAPI, accepts either a raw `diff` or a
`pr_url`) → if `pr_url`, `api/github.py` fetches the unified diff via the GitHub
REST API → `agent.graph.invoke(diff)` → LangGraph runs nodes, each wrapped in a
Langfuse span → annotated JSON returned → dashboard renders it. Eval harness
calls the same graph over the golden set and scores outputs with RAGAS.

## 4. The LangGraph Agent

**`ReviewState`** (carried through the graph):
- `raw_diff: str`
- `files: list[FileDiff]` (parsed hunks per file)
- `security_findings: list[Finding]`
- `logic_findings: list[Finding]`
- `test_suggestions: list[Finding]`
- `score: ReviewScore` (overall + per-category severity rollup)
- `meta` (model, tokens, latency accumulators, errors)

**`Finding`** schema: `{ file, line_start, line_end, severity (info|low|medium|high|critical), category, message, suggestion }`

**Nodes:**
1. `ingest` — parse unified diff into per-file hunks; classify diff size; short-circuit trivial diffs (whitespace/docs only) to a light path.
2. `security_scan` — LLM prompt focused on injection, authn/z, secrets, unsafe deserialization, etc. → `security_findings`.
3. `logic_analysis` — correctness, edge cases, error handling, complexity → `logic_findings`.
4. `test_coverage` — what tests are missing for the changed code → `test_suggestions`.
5. `aggregate` — merge findings, compute `ReviewScore`, emit final annotated JSON.

**Edges:** linear `ingest → security → logic → test → aggregate`, with a
conditional edge from `ingest` that skips `security/logic` deep analysis on
trivial diffs. Each LLM node validates output against the `Finding` schema and
**retries once** on malformed JSON before degrading gracefully.

## 5. Observability (Langfuse)

- Each graph run = one Langfuse **trace**; each node = a **span**.
- Per span: input/output, model name, **token counts**, **latency**, cost,
  and (in eval mode) the RAGAS scores attached to the trace.
- Toggled by `LANGFUSE_ENABLED`; when on without keys it falls back to console
  tracing so the dashboard demo is reproducible.
- The **mock provider still emits realistic spans** (synthetic tokens/latency)
  so the Langfuse dashboard is never empty in an offline demo.

## 5b. GitHub Integration (Fetch PR by URL)

Lets a user review a real PR without copy-pasting a diff.

- **Input:** a GitHub PR URL (`https://github.com/owner/repo/pull/123`) or the
  shorthand `owner/repo#123`. `api/github.py` parses it and fetches the unified
  diff from the GitHub REST API (`GET /repos/{owner}/{repo}/pulls/{n}` with the
  `application/vnd.github.v3.diff` media type).
- **Auth:** optional `GITHUB_TOKEN` env var — anonymous works for public repos
  (subject to rate limits); a token enables private repos and higher limits.
- **API shape:** `POST /review` accepts **either** `{ "diff": "..." }` **or**
  `{ "pr_url": "..." }`. Exactly one must be provided (422 otherwise). The PR
  title/description are also fetched and passed to the agent as extra context.
- **Errors:** clear messages for invalid URL, 404 (not found / private without
  token), and GitHub rate-limit responses.
- **Eval/CI unaffected:** the golden dataset stays as local diff files; GitHub
  fetch is a convenience input path, not part of the eval loop.

## 6. Evaluation Harness (RAGAS)

- **Golden dataset:** 20 synthetic PR diffs in `evals/golden/`, each with a
  ground-truth review JSON. Coverage spread across security / logic / test
  categories and across languages (Python, JS/TS, Go) and diff sizes.
- **Metrics:** RAGAS **faithfulness** + **answer correctness**. Gate at **≥ 0.75**.
- **Runner:** `evals/run_eval.py` runs the graph over the golden set, scores with
  RAGAS (using a configured judge provider), writes `reports/<timestamp>.json`
  and a human-readable markdown summary.
- A RAGAS judge needs a real LLM; CI uses a free **Groq** key from GitHub Secrets.

## 7. CI (GitHub Actions)

`.github/workflows/ci.yml` on push / PR / prompt change:
1. **Lint + unit tests** — uses the **mock provider**, no API key, fast.
2. **Eval stage** — runs `run_eval.py` with a free Groq key from secrets.
3. **Gate** — fail the build if faithfulness or correctness < 0.75.
4. **Report** — upload the eval report as an artifact and post a PR comment with
   the score table.

Prompt files live in `agent/prompts/`; a change there triggers the eval stage —
this literally implements "runs eval on every prompt change and fails below
threshold."

## 8. Dashboard (Vite + React + TS)

Two views:
1. **Review playground** — either **paste a PR diff** *or* **enter a GitHub PR
   URL** → calls `/review` → renders annotated findings with severity badges,
   per-file grouping, and the overall score gauge. Streams node progress if time
   permits (nice-to-have, not required).
2. **Eval analytics** — reads eval reports: score trends across runs (line
   chart), per-PR drill-down table, faithfulness/correctness breakdown, and
   deep-links to the corresponding Langfuse traces.

## 9. Deliverables Mapping

| Brief deliverable | Where satisfied |
|---|---|
| LangGraph agent, 3+ nodes, deployed as API endpoint | §4 agent (5 nodes) + §3 FastAPI `/review` |
| Langfuse full trace visibility | §5 |
| 20-PR eval dataset, RAGAS faithfulness+correctness ≥ 0.75 | §6 |
| CI runs eval on prompt change, fails below threshold | §7 |
| Walkthrough demo video | §10 |

## 10. Phased Plan (~1 week)

- **Day 1–2:** scaffold monorepo, LLM adapters + mock, LangGraph agent end-to-end returning JSON; unit tests on mock.
- **Day 2–3:** FastAPI `/review` (diff **or** PR-URL input) + GitHub fetch client + health/version endpoints; Langfuse wiring.
- **Day 3–4:** author 20 golden PRs + ground truth; `run_eval.py` reaching ≥0.75.
- **Day 4–5:** CI pipeline with gating + PR comment.
- **Day 5–6:** React dashboard (playground + analytics).
- **Day 7:** README, polish, record demo video.

## 11. Testing Strategy

- **Unit:** diff parser, each node's output schema validation, score aggregation, adapter contract tests (all via mock provider — deterministic, no network).
- **Integration:** full graph run on a fixture diff via mock provider.
- **Eval:** RAGAS harness is itself the system-level quality gate.
- **CI** runs unit + integration on mock (no keys), then eval on Groq.

## 12. Error Handling

- LLM nodes: validate against `Finding` schema, retry once, then degrade to an
  empty finding list with a logged warning (never crash the whole review).
- API: structured error responses; 422 on unparsable diff; 502 on provider
  failure after retry.
- Eval: a single failing PR is reported, not fatal; the gate is on aggregate scores.

## 13. Out of Scope (YAGNI)

- GitHub **webhook / App** auto-review bot (we support on-demand PR-URL fetch
  and raw diffs, but not event-driven auto-commenting).
- Auth / multi-user.
- Persisting reviews to a database (eval reports are flat files).
- Fine-tuning or custom models.
