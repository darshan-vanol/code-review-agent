# Dashboard (Review Playground + Eval Analytics) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `web/` Vite + React + TS dashboard — a Review Playground (paste a diff or PR URL → `POST /review` → annotated findings, score gauge, node spans) and an Eval Analytics view (RAGAS report trends + per-PR drill-down) — backed by two new read-only API endpoints and CORS.

**Architecture:** The dashboard is a pure client of the existing FastAPI app. The only backend change is additive: CORS middleware plus `GET /eval/reports` and `GET /eval/reports/{id}` that read the existing `evals/reports/*.json` files. The frontend is a single-page app with a two-tab shell (no router dependency), hand-rolled CSS, and Recharts for one trend chart. The agent and eval harness are untouched.

**Tech Stack:** Backend — Python 3.11+, FastAPI (CORSMiddleware), pytest. Frontend — Vite, React 18, TypeScript, Recharts, Vitest + React Testing Library + jsdom. Node 20 / npm 10 (verified present).

## Global Constraints

- Python `>=3.11`; manage deps + run via `uv` (`uv run ...`). ruff line-length **100**; keep `uv run ruff check .` clean before every backend commit.
- The backend changes are **additive and read-only**: do not modify the agent, the eval harness, or the eval report file shape. Endpoints must never 500 on a missing/empty reports dir — return `[]` / 404.
- Eval reports dir is configurable via env `EVAL_REPORTS_DIR` (default `evals/reports`), read **at request time** so tests can point it at a tmp dir.
- CORS allowed origin is env `WEB_ORIGIN` (default `http://localhost:5173`, comma-separated for multiple).
- Frontend: no UI-framework dependency; styling is hand-rolled CSS / CSS modules. Recharts is the only chart dep. Tests stub `fetch`/mock the `api` module — never hit a live backend.
- TDD throughout: failing test → confirm fail → minimal implementation → confirm pass → commit. Frequent commits.
- Authoritative API contracts (from Plans 1–3, do not change):
  - `POST /review` body = exactly one of `{diff}` or `{pr_url}` (422 otherwise).
  - `ReviewResponse` = `{is_trivial: bool, score: {overall: float, counts: Record<severity,int>} | null, security_findings: Finding[], logic_findings: Finding[], test_suggestions: Finding[], token_usage: Record<string,number>, spans: {name, latency_ms, input_tokens, output_tokens}[], errors: string[]}`.
  - `Finding` = `{file, line_start, line_end, severity (info|low|medium|high|critical), category, message, suggestion}`.
  - Eval report (`{n}.json`) = `{aggregate: {faithfulness, answer_correctness}, threshold: 0.75, passed: bool, items: {id, faithfulness, answer_correctness}[]}`.

---

## File Structure

```
api/
├── main.py            # MODIFY: add CORS middleware + /eval/reports routes
├── schemas.py         # MODIFY: add EvalReportSummary
└── reports.py         # CREATE: list_reports() / get_report() over evals/reports

tests/
└── test_eval_endpoints.py   # CREATE: endpoints + CORS (pytest)

web/                   # CREATE: Vite + React + TS SPA
├── index.html
├── package.json
├── vite.config.ts     # dev proxy to :8000 + vitest config
├── tsconfig.json / tsconfig.node.json
├── src/
│   ├── main.tsx
│   ├── App.tsx                 # two-tab shell
│   ├── app.css
│   ├── setupTests.ts
│   ├── api.ts                  # typed fetch wrappers + TS types
│   ├── api.test.ts
│   ├── components/
│   │   ├── SeverityBadge.tsx
│   │   └── EmptyState.tsx
│   ├── playground/
│   │   ├── Playground.tsx      + Playground.test.tsx
│   │   ├── ReviewForm.tsx      + ReviewForm.test.tsx
│   │   ├── ScoreGauge.tsx
│   │   ├── FindingsList.tsx    + FindingsList.test.tsx
│   │   └── SpansPanel.tsx
│   └── evals/
│       ├── EvalAnalytics.tsx   + EvalAnalytics.test.tsx
│       ├── TrendChart.tsx
│       └── ReportTable.tsx     + ReportTable.test.tsx
└── README section (in repo README.md)
```

---

## Task 1: Backend — CORS + eval report endpoints

**Files:**
- Create: `api/reports.py`
- Modify: `api/schemas.py` (add `EvalReportSummary`)
- Modify: `api/main.py` (add CORS middleware + two routes)
- Test: `tests/test_eval_endpoints.py`

**Interfaces:**
- Consumes: existing `app` in `api/main.py`; existing report JSON shape.
- Produces:
  - `api/reports.py`: `reports_dir() -> Path` (reads `EVAL_REPORTS_DIR`, default `evals/reports`); `list_reports(directory: Path | None = None) -> list[dict]` returning `{"id", "passed", "aggregate"}` per `*.json`, numeric-stem sorted, `[]` if dir missing; `get_report(report_id: str, directory: Path | None = None) -> dict | None`.
  - `api/schemas.py`: `EvalReportSummary(BaseModel)` with `id: str`, `passed: bool`, `aggregate: dict[str, float]`.
  - `api/main.py`: `GET /eval/reports -> list[EvalReportSummary]`, `GET /eval/reports/{report_id}` (404 if unknown), and CORS allowing `WEB_ORIGIN`.

- [ ] **Step 1: Write the failing test**

`tests/test_eval_endpoints.py`:
```python
import json

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_REPORT = {
    "aggregate": {"faithfulness": 0.9, "answer_correctness": 0.85},
    "threshold": 0.75,
    "passed": True,
    "items": [{"id": "01-x", "faithfulness": 0.9, "answer_correctness": 0.85}],
}


def _seed(tmp_path, monkeypatch, n=1):
    monkeypatch.setenv("EVAL_REPORTS_DIR", str(tmp_path))
    for i in range(1, n + 1):
        (tmp_path / f"{i}.json").write_text(json.dumps(_REPORT))


def test_list_reports_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EVAL_REPORTS_DIR", str(tmp_path / "nope"))
    r = client.get("/eval/reports")
    assert r.status_code == 200
    assert r.json() == []


def test_list_reports_returns_summaries(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch, n=2)
    r = client.get("/eval/reports")
    body = r.json()
    assert len(body) == 2
    assert body[0]["id"] == "1"
    assert body[0]["passed"] is True
    assert body[0]["aggregate"]["faithfulness"] == 0.9


def test_get_report_returns_full(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    r = client.get("/eval/reports/1")
    assert r.status_code == 200
    assert r.json()["items"][0]["id"] == "01-x"


def test_get_report_unknown_is_404(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    r = client.get("/eval/reports/999")
    assert r.status_code == 404


def test_cors_header_present_for_web_origin():
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_eval_endpoints.py -v`
Expected: FAIL — `/eval/reports` 404s (route missing) and no CORS header.

- [ ] **Step 3: Implement the reports reader**

`api/reports.py`:
```python
from __future__ import annotations

import json
import os
from pathlib import Path


def reports_dir() -> Path:
    return Path(os.environ.get("EVAL_REPORTS_DIR", "evals/reports"))


def _sort_key(path: Path) -> tuple[int, object]:
    # Reports are written as 1.json, 2.json, ...; sort numerically when possible
    # so 10 sorts after 2, falling back to lexical for non-numeric stems.
    return (0, int(path.stem)) if path.stem.isdigit() else (1, path.stem)


def list_reports(directory: Path | None = None) -> list[dict]:
    directory = directory or reports_dir()
    if not directory.exists():
        return []
    summaries: list[dict] = []
    for path in sorted(directory.glob("*.json"), key=_sort_key):
        data = json.loads(path.read_text())
        summaries.append(
            {"id": path.stem, "passed": data["passed"], "aggregate": data["aggregate"]}
        )
    return summaries


def get_report(report_id: str, directory: Path | None = None) -> dict | None:
    directory = directory or reports_dir()
    path = directory / f"{report_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
```

- [ ] **Step 4: Add the `EvalReportSummary` schema**

In `api/schemas.py`, append after the existing models:
```python
class EvalReportSummary(BaseModel):
    id: str
    passed: bool
    aggregate: dict[str, float]
```

- [ ] **Step 5: Wire CORS + routes into `api/main.py`**

Add imports near the top (after the existing `from fastapi import ...` line):
```python
from fastapi.middleware.cors import CORSMiddleware

from api.reports import get_report, list_reports
from api.schemas import EvalReportSummary
```
(Extend the existing `from api.schemas import ReviewRequest, ReviewResponse` line to also import `EvalReportSummary`, or add the separate import above — either is fine; keep one import per symbol set and ruff-clean.)

Immediately after `app = FastAPI(...)` (line 13), add the middleware:
```python
_web_origins = os.environ.get("WEB_ORIGIN", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _web_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Add the two routes (e.g. just before the `/review` route):
```python
@app.get("/eval/reports", response_model=list[EvalReportSummary])
def eval_reports() -> list[dict]:
    return list_reports()


@app.get("/eval/reports/{report_id}")
def eval_report(report_id: str) -> dict:
    report = get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No eval report '{report_id}'")
    return report
```

- [ ] **Step 6: Run tests + lint to verify they pass**

Run: `uv run pytest tests/test_eval_endpoints.py -v && uv run ruff check .`
Expected: 5 passed; ruff clean.

- [ ] **Step 7: Run the full backend suite (no regressions)**

Run: `uv run pytest -q`
Expected: all existing tests still pass.

- [ ] **Step 8: Commit**

```bash
git add api/reports.py api/schemas.py api/main.py tests/test_eval_endpoints.py
git commit -m "feat: add CORS + read-only eval report endpoints for dashboard"
```

---

## Task 2: Scaffold the web app + typed API client

**Files:**
- Create: `web/` (Vite react-ts scaffold), pruned
- Create/Modify: `web/vite.config.ts`, `web/package.json` (scripts + deps), `web/src/setupTests.ts`
- Create: `web/src/api.ts`
- Test: `web/src/api.test.ts`

**Interfaces:**
- Produces (`web/src/api.ts`):
  - Types: `Severity`, `Finding`, `ReviewScore`, `Span`, `ReviewResponse`, `EvalAggregate`, `EvalReportSummary`, `EvalItem`, `EvalReport` (mirroring the Global Constraints contracts).
  - `postReview(body: {diff?: string; pr_url?: string}): Promise<ReviewResponse>`
  - `getReports(): Promise<EvalReportSummary[]>`
  - `getReport(id: string): Promise<EvalReport>`

- [ ] **Step 1: Scaffold and install**

Run from the repo root:
```bash
npm create vite@latest web -- --template react-ts
cd web
npm install
npm install recharts
npm install -D vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event
```
Expected: `web/` created with a React+TS scaffold; deps installed.

- [ ] **Step 2: Prune scaffold boilerplate**

Delete the demo assets so they don't leak into the app:
```bash
rm -f web/src/App.css web/src/index.css web/src/assets/react.svg web/public/vite.svg
```
(`web/src/App.tsx` and `web/src/main.tsx` will be replaced in Task 5; leave them for now — the build still works.)

- [ ] **Step 3: Configure Vite dev proxy + Vitest**

Replace `web/vite.config.ts` with:
```ts
/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/review": "http://localhost:8000",
      "/eval": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/version": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/setupTests.ts",
  },
});
```

Create `web/src/setupTests.ts`:
```ts
import "@testing-library/jest-dom";
```

In `web/package.json`, add a `test` script to the `"scripts"` block:
```json
"test": "vitest run"
```

- [ ] **Step 4: Write the failing API-client test**

`web/src/api.test.ts`:
```ts
import { beforeEach, expect, it, vi } from "vitest";

import { getReports, postReview } from "./api";

beforeEach(() => {
  vi.restoreAllMocks();
});

it("postReview POSTs the body to /review and returns json", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ is_trivial: false }) });
  vi.stubGlobal("fetch", fetchMock);

  const res = await postReview({ diff: "d" });

  expect(fetchMock).toHaveBeenCalledWith(
    "/review",
    expect.objectContaining({ method: "POST" }),
  );
  const [, init] = fetchMock.mock.calls[0];
  expect(JSON.parse(init.body)).toEqual({ diff: "d" });
  expect(res).toEqual({ is_trivial: false });
});

it("getReports GETs /eval/reports", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
  vi.stubGlobal("fetch", fetchMock);

  await getReports();

  expect(fetchMock).toHaveBeenCalledWith("/eval/reports");
});

it("postReview throws on a non-ok response", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: "bad" }) });
  vi.stubGlobal("fetch", fetchMock);

  await expect(postReview({ diff: "" })).rejects.toThrow();
});
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd web && npm test`
Expected: FAIL — `./api` cannot be resolved.

- [ ] **Step 6: Implement the API client**

`web/src/api.ts`:
```ts
export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface Finding {
  file: string;
  line_start: number;
  line_end: number;
  severity: Severity;
  category: string;
  message: string;
  suggestion: string;
}

export interface ReviewScore {
  overall: number;
  counts: Record<Severity, number>;
}

export interface Span {
  name: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
}

export interface ReviewResponse {
  is_trivial: boolean;
  score: ReviewScore | null;
  security_findings: Finding[];
  logic_findings: Finding[];
  test_suggestions: Finding[];
  token_usage: Record<string, number>;
  spans: Span[];
  errors: string[];
}

export interface EvalAggregate {
  faithfulness: number;
  answer_correctness: number;
}

export interface EvalReportSummary {
  id: string;
  passed: boolean;
  aggregate: EvalAggregate;
}

export interface EvalItem {
  id: string;
  faithfulness: number;
  answer_correctness: number;
}

export interface EvalReport {
  aggregate: EvalAggregate;
  threshold: number;
  passed: boolean;
  items: EvalItem[];
}

// Dev: requests are proxied to the API by Vite (see vite.config.ts). In a build,
// set VITE_API_URL to the API origin.
const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "";

async function asJson<T>(res: { ok: boolean; status: number; json: () => Promise<unknown> }): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function postReview(body: { diff?: string; pr_url?: string }): Promise<ReviewResponse> {
  const res = await fetch(`${BASE}/review`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return asJson<ReviewResponse>(res);
}

export async function getReports(): Promise<EvalReportSummary[]> {
  const res = await fetch(`${BASE}/eval/reports`);
  return asJson<EvalReportSummary[]>(res);
}

export async function getReport(id: string): Promise<EvalReport> {
  const res = await fetch(`${BASE}/eval/reports/${id}`);
  return asJson<EvalReport>(res);
}
```

Note: with `BASE = ""`, the test's expected URL is exactly `/review` and `/eval/reports`.

- [ ] **Step 7: Run test + typecheck to verify pass**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: 3 tests pass; no type errors.

- [ ] **Step 8: Commit**

```bash
git add web/ && git commit -m "feat: scaffold web dashboard + typed API client"
```
(Note: `web/node_modules` should be ignored. If the repo `.gitignore` doesn't already exclude it, create `web/.gitignore` with `node_modules` and `dist` before committing.)

---

## Task 3: Review Playground

**Files:**
- Create: `web/src/components/SeverityBadge.tsx`
- Create: `web/src/playground/ReviewForm.tsx` + `ReviewForm.test.tsx`
- Create: `web/src/playground/FindingsList.tsx` + `FindingsList.test.tsx`
- Create: `web/src/playground/ScoreGauge.tsx`
- Create: `web/src/playground/SpansPanel.tsx`
- Create: `web/src/playground/Playground.tsx` + `Playground.test.tsx`

**Interfaces:**
- Consumes: `Finding`, `ReviewScore`, `Span`, `ReviewResponse`, `postReview` from `../api`.
- Produces:
  - `SeverityBadge({ severity: Severity })`
  - `ReviewForm({ onSubmit: (b: {diff?: string; pr_url?: string}) => void, loading: boolean })`
  - `FindingsList({ findings: Finding[] })`
  - `ScoreGauge({ score: ReviewScore })`
  - `SpansPanel({ spans: Span[] })`
  - `Playground()` — composes the above, owns fetch state.

- [ ] **Step 1: Write the failing ReviewForm test**

`web/src/playground/ReviewForm.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { ReviewForm } from "./ReviewForm";

it("submits a diff in diff mode", async () => {
  const onSubmit = vi.fn();
  render(<ReviewForm onSubmit={onSubmit} loading={false} />);
  await userEvent.type(screen.getByLabelText("diff"), "my diff");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(onSubmit).toHaveBeenCalledWith({ diff: "my diff" });
});

it("submits a pr_url in URL mode", async () => {
  const onSubmit = vi.fn();
  render(<ReviewForm onSubmit={onSubmit} loading={false} />);
  await userEvent.click(screen.getByRole("tab", { name: "PR URL" }));
  await userEvent.type(screen.getByLabelText("pr_url"), "http://x/pull/1");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(onSubmit).toHaveBeenCalledWith({ pr_url: "http://x/pull/1" });
});

it("disables submit while loading", () => {
  render(<ReviewForm onSubmit={vi.fn()} loading={true} />);
  expect(screen.getByRole("button", { name: /Reviewing/ })).toBeDisabled();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npm test -- ReviewForm`
Expected: FAIL — `./ReviewForm` not found.

- [ ] **Step 3: Implement ReviewForm**

`web/src/playground/ReviewForm.tsx`:
```tsx
import { type FormEvent, useState } from "react";

type Mode = "diff" | "pr_url";

export function ReviewForm({
  onSubmit,
  loading,
}: {
  onSubmit: (body: { diff?: string; pr_url?: string }) => void;
  loading: boolean;
}) {
  const [mode, setMode] = useState<Mode>("diff");
  const [diff, setDiff] = useState("");
  const [prUrl, setPrUrl] = useState("");

  function submit(e: FormEvent) {
    e.preventDefault();
    onSubmit(mode === "diff" ? { diff } : { pr_url: prUrl });
  }

  return (
    <form className="review-form" onSubmit={submit}>
      <div role="tablist" className="mode-toggle">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "diff"}
          onClick={() => setMode("diff")}
        >
          Diff
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "pr_url"}
          onClick={() => setMode("pr_url")}
        >
          PR URL
        </button>
      </div>

      {mode === "diff" ? (
        <textarea
          aria-label="diff"
          rows={12}
          value={diff}
          onChange={(e) => setDiff(e.target.value)}
          placeholder="Paste a unified diff (diff --git ...)"
        />
      ) : (
        <input
          aria-label="pr_url"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
          placeholder="https://github.com/owner/repo/pull/123"
        />
      )}

      <button type="submit" disabled={loading}>
        {loading ? "Reviewing…" : "Review"}
      </button>
    </form>
  );
}
```

- [ ] **Step 4: Run to verify ReviewForm passes**

Run: `cd web && npm test -- ReviewForm`
Expected: 3 pass.

- [ ] **Step 5: Write the failing FindingsList test**

`web/src/playground/FindingsList.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { Finding } from "../api";
import { FindingsList } from "./FindingsList";

const finding = (over: Partial<Finding> = {}): Finding => ({
  file: "a.py",
  line_start: 1,
  line_end: 2,
  severity: "high",
  category: "security",
  message: "bad thing",
  suggestion: "fix it",
  ...over,
});

it("groups findings by file and renders badge + location + message", () => {
  render(
    <FindingsList
      findings={[finding(), finding({ file: "b.py", category: "logic", severity: "low" })]}
    />,
  );
  expect(screen.getByText("a.py:1-2")).toBeInTheDocument();
  expect(screen.getByText("high")).toBeInTheDocument();
  expect(screen.getByText("bad thing")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "b.py" })).toBeInTheDocument();
});

it("renders an empty message when there are no findings", () => {
  render(<FindingsList findings={[]} />);
  expect(screen.getByText("No issues found.")).toBeInTheDocument();
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd web && npm test -- FindingsList`
Expected: FAIL — `./FindingsList` and `../components/SeverityBadge` not found.

- [ ] **Step 7: Implement SeverityBadge + FindingsList**

`web/src/components/SeverityBadge.tsx`:
```tsx
import type { Severity } from "../api";

const COLORS: Record<Severity, string> = {
  info: "#6b7280",
  low: "#2563eb",
  medium: "#d97706",
  high: "#dc2626",
  critical: "#7f1d1d",
};

export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="badge" style={{ background: COLORS[severity] }}>
      {severity}
    </span>
  );
}
```

`web/src/playground/FindingsList.tsx`:
```tsx
import type { Finding } from "../api";
import { SeverityBadge } from "../components/SeverityBadge";

function groupByFile(findings: Finding[]): Record<string, Finding[]> {
  const groups: Record<string, Finding[]> = {};
  for (const f of findings) {
    (groups[f.file] ??= []).push(f);
  }
  return groups;
}

export function FindingsList({ findings }: { findings: Finding[] }) {
  if (findings.length === 0) {
    return <p className="empty">No issues found.</p>;
  }
  const groups = groupByFile(findings);
  return (
    <div className="findings">
      {Object.entries(groups).map(([file, items]) => (
        <section key={file} className="file-group">
          <h3>{file}</h3>
          <ul>
            {items.map((f, i) => (
              <li key={i} className={`finding cat-${f.category}`}>
                <div className="finding-head">
                  <SeverityBadge severity={f.severity} />
                  <span className="loc">
                    {f.file}:{f.line_start}-{f.line_end}
                  </span>
                  <span className="cat">{f.category}</span>
                </div>
                <p className="msg">{f.message}</p>
                <p className="suggestion">{f.suggestion}</p>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
```

- [ ] **Step 8: Run to verify FindingsList passes**

Run: `cd web && npm test -- FindingsList`
Expected: 2 pass.

- [ ] **Step 9: Implement ScoreGauge + SpansPanel (no separate test; covered via Playground)**

`web/src/playground/ScoreGauge.tsx`:
```tsx
import type { ReviewScore } from "../api";

export function ScoreGauge({ score }: { score: ReviewScore }) {
  const pct = Math.round(score.overall * 100);
  return (
    <div className="gauge">
      <div className="gauge-value" aria-label="overall score">
        {pct}%
      </div>
      <div className="gauge-bar">
        <div className="gauge-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="counts">
        {Object.entries(score.counts)
          .filter(([, n]) => n > 0)
          .map(([sev, n]) => (
            <span key={sev} className={`chip sev-${sev}`}>
              {sev}: {n}
            </span>
          ))}
      </div>
    </div>
  );
}
```

`web/src/playground/SpansPanel.tsx`:
```tsx
import type { Span } from "../api";

export function SpansPanel({ spans }: { spans: Span[] }) {
  if (spans.length === 0) return null;
  return (
    <details className="spans">
      <summary>Node spans ({spans.length})</summary>
      <table>
        <thead>
          <tr>
            <th>node</th>
            <th>latency (ms)</th>
            <th>in tok</th>
            <th>out tok</th>
          </tr>
        </thead>
        <tbody>
          {spans.map((s) => (
            <tr key={s.name}>
              <td>{s.name}</td>
              <td>{s.latency_ms.toFixed(1)}</td>
              <td>{s.input_tokens}</td>
              <td>{s.output_tokens}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
```

- [ ] **Step 10: Write the failing Playground test**

`web/src/playground/Playground.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { postReview } from "../api";
import { Playground } from "./Playground";

vi.mock("../api", () => ({ postReview: vi.fn() }));

const baseResponse = {
  is_trivial: false,
  score: { overall: 0.7, counts: { info: 0, low: 0, medium: 0, high: 1, critical: 0 } },
  security_findings: [
    {
      file: "a.py",
      line_start: 1,
      line_end: 1,
      severity: "high",
      category: "security",
      message: "sql injection",
      suggestion: "parameterize",
    },
  ],
  logic_findings: [],
  test_suggestions: [],
  token_usage: {},
  spans: [],
  errors: [],
};

beforeEach(() => {
  vi.mocked(postReview).mockReset();
});

it("renders findings after a successful review", async () => {
  vi.mocked(postReview).mockResolvedValue(baseResponse as never);
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByText("sql injection")).toBeInTheDocument();
});

it("shows the trivial notice for a trivial diff", async () => {
  vi.mocked(postReview).mockResolvedValue({
    ...baseResponse,
    is_trivial: true,
    security_findings: [],
  } as never);
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByText(/Trivial diff/)).toBeInTheDocument();
});

it("shows an error message when the request fails", async () => {
  vi.mocked(postReview).mockRejectedValue(new Error("Provide exactly one of"));
  render(<Playground />);
  await userEvent.type(screen.getByLabelText("diff"), "d");
  await userEvent.click(screen.getByRole("button", { name: "Review" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Provide exactly one of");
});
```

- [ ] **Step 11: Run to verify it fails**

Run: `cd web && npm test -- Playground`
Expected: FAIL — `./Playground` not found.

- [ ] **Step 12: Implement Playground**

`web/src/playground/Playground.tsx`:
```tsx
import { useState } from "react";

import { postReview, type ReviewResponse } from "../api";
import { FindingsList } from "./FindingsList";
import { ReviewForm } from "./ReviewForm";
import { ScoreGauge } from "./ScoreGauge";
import { SpansPanel } from "./SpansPanel";

export function Playground() {
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(body: { diff?: string; pr_url?: string }) {
    setLoading(true);
    setError(null);
    try {
      setResult(await postReview(body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const findings = result
    ? [...result.security_findings, ...result.logic_findings, ...result.test_suggestions]
    : [];

  return (
    <div className="playground">
      <ReviewForm onSubmit={run} loading={loading} />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="result">
          {result.is_trivial && (
            <p className="notice">Trivial diff — deep analysis skipped.</p>
          )}
          {result.score && <ScoreGauge score={result.score} />}
          {result.errors.length > 0 && (
            <ul className="warnings">
              {result.errors.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
          <FindingsList findings={findings} />
          <SpansPanel spans={result.spans} />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 13: Run the full web suite + typecheck**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all playground + form + findings + api tests pass; no type errors.

- [ ] **Step 14: Commit**

```bash
git add web/src && git commit -m "feat: review playground (form, findings, score gauge, spans)"
```

---

## Task 4: Eval Analytics

**Files:**
- Create: `web/src/components/EmptyState.tsx`
- Create: `web/src/evals/ReportTable.tsx` + `ReportTable.test.tsx`
- Create: `web/src/evals/TrendChart.tsx`
- Create: `web/src/evals/EvalAnalytics.tsx` + `EvalAnalytics.test.tsx`

**Interfaces:**
- Consumes: `EvalReport`, `EvalReportSummary`, `getReports`, `getReport` from `../api`.
- Produces:
  - `EmptyState({ message: string })`
  - `ReportTable({ report: EvalReport })` — rows get `data-status="pass"|"fail"` (both metrics ≥ 0.75 = pass).
  - `TrendChart({ reports: EvalReportSummary[] })` — Recharts line chart with a `y=0.75` reference line.
  - `EvalAnalytics()` — loads reports on mount; shows EmptyState when none.

Note: `TrendChart` is a thin Recharts wrapper; Recharts' `ResponsiveContainer` renders nothing in jsdom (zero size), so it is **not** unit-tested directly — it is mocked out in the `EvalAnalytics` test. This is intentional, not a gap.

- [ ] **Step 1: Write the failing ReportTable test**

`web/src/evals/ReportTable.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import type { EvalReport } from "../api";
import { ReportTable } from "./ReportTable";

const report: EvalReport = {
  aggregate: { faithfulness: 0.8, answer_correctness: 0.8 },
  threshold: 0.75,
  passed: true,
  items: [
    { id: "ok", faithfulness: 0.75, answer_correctness: 0.9 },
    { id: "bad", faithfulness: 0.74, answer_correctness: 0.9 },
  ],
};

it("marks rows pass/fail at the 0.75 boundary", () => {
  render(<ReportTable report={report} />);
  expect(screen.getByText("ok").closest("tr")).toHaveAttribute("data-status", "pass");
  expect(screen.getByText("bad").closest("tr")).toHaveAttribute("data-status", "fail");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npm test -- ReportTable`
Expected: FAIL — `./ReportTable` not found.

- [ ] **Step 3: Implement ReportTable**

`web/src/evals/ReportTable.tsx`:
```tsx
import type { EvalReport } from "../api";

const THRESHOLD = 0.75;

export function ReportTable({ report }: { report: EvalReport }) {
  return (
    <table className="report-table">
      <thead>
        <tr>
          <th>id</th>
          <th>faithfulness</th>
          <th>answer correctness</th>
        </tr>
      </thead>
      <tbody>
        {report.items.map((it) => {
          const pass =
            it.faithfulness >= THRESHOLD && it.answer_correctness >= THRESHOLD;
          const status = pass ? "pass" : "fail";
          return (
            <tr key={it.id} className={status} data-status={status}>
              <td>{it.id}</td>
              <td>{it.faithfulness.toFixed(2)}</td>
              <td>{it.answer_correctness.toFixed(2)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run to verify ReportTable passes**

Run: `cd web && npm test -- ReportTable`
Expected: 1 pass.

- [ ] **Step 5: Implement EmptyState + TrendChart**

`web/src/components/EmptyState.tsx`:
```tsx
export function EmptyState({ message }: { message: string }) {
  return <div className="empty-state">{message}</div>;
}
```

`web/src/evals/TrendChart.tsx`:
```tsx
import {
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { EvalReportSummary } from "../api";

export function TrendChart({ reports }: { reports: EvalReportSummary[] }) {
  const data = reports.map((r) => ({
    id: r.id,
    faithfulness: r.aggregate.faithfulness,
    answer_correctness: r.aggregate.answer_correctness,
  }));
  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data}>
        <XAxis dataKey="id" />
        <YAxis domain={[0, 1]} />
        <Tooltip />
        <Legend />
        <ReferenceLine y={0.75} stroke="#dc2626" strokeDasharray="4 4" label="0.75" />
        <Line type="monotone" dataKey="faithfulness" stroke="#2563eb" />
        <Line type="monotone" dataKey="answer_correctness" stroke="#059669" />
      </LineChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 6: Write the failing EvalAnalytics test**

`web/src/evals/EvalAnalytics.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { getReport, getReports } from "../api";
import { EvalAnalytics } from "./EvalAnalytics";

vi.mock("../api", () => ({ getReports: vi.fn(), getReport: vi.fn() }));
vi.mock("./TrendChart", () => ({ TrendChart: () => <div data-testid="trend" /> }));

beforeEach(() => {
  vi.mocked(getReports).mockReset();
  vi.mocked(getReport).mockReset();
});

it("shows an empty state when there are no reports", async () => {
  vi.mocked(getReports).mockResolvedValue([]);
  render(<EvalAnalytics />);
  expect(await screen.findByText(/No eval runs yet/)).toBeInTheDocument();
});

it("renders the table for the latest report", async () => {
  vi.mocked(getReports).mockResolvedValue([
    { id: "1", passed: true, aggregate: { faithfulness: 0.9, answer_correctness: 0.9 } },
  ]);
  vi.mocked(getReport).mockResolvedValue({
    aggregate: { faithfulness: 0.9, answer_correctness: 0.9 },
    threshold: 0.75,
    passed: true,
    items: [{ id: "pr-x", faithfulness: 0.9, answer_correctness: 0.9 }],
  });
  render(<EvalAnalytics />);
  expect(await screen.findByText("pr-x")).toBeInTheDocument();
  expect(screen.getByTestId("trend")).toBeInTheDocument();
});
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd web && npm test -- EvalAnalytics`
Expected: FAIL — `./EvalAnalytics` not found.

- [ ] **Step 8: Implement EvalAnalytics**

`web/src/evals/EvalAnalytics.tsx`:
```tsx
import { useEffect, useState } from "react";

import { type EvalReport, type EvalReportSummary, getReport, getReports } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ReportTable } from "./ReportTable";
import { TrendChart } from "./TrendChart";

const LANGFUSE_URL = import.meta.env.VITE_LANGFUSE_URL as string | undefined;

export function EvalAnalytics() {
  const [reports, setReports] = useState<EvalReportSummary[]>([]);
  const [selected, setSelected] = useState<EvalReport | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getReports()
      .then(async (rs) => {
        setReports(rs);
        if (rs.length > 0) {
          setSelected(await getReport(rs[rs.length - 1].id));
        }
      })
      .catch(() => {
        /* leave empty; the empty state covers it */
      })
      .finally(() => setLoaded(true));
  }, []);

  if (loaded && reports.length === 0) {
    return <EmptyState message="No eval runs yet — run `python -m evals.run_eval`." />;
  }

  return (
    <div className="analytics">
      {LANGFUSE_URL && (
        <a className="langfuse-link" href={LANGFUSE_URL} target="_blank" rel="noreferrer">
          Open in Langfuse ↗
        </a>
      )}
      <TrendChart reports={reports} />
      {selected && <ReportTable report={selected} />}
    </div>
  );
}
```

- [ ] **Step 9: Run the full web suite + typecheck**

Run: `cd web && npm test && npx tsc --noEmit`
Expected: all tests pass; no type errors.

- [ ] **Step 10: Commit**

```bash
git add web/src && git commit -m "feat: eval analytics view (trend chart + per-PR table)"
```

---

## Task 5: App shell, styling, and README

**Files:**
- Modify: `web/src/App.tsx` (two-tab shell) + create `web/src/App.test.tsx`
- Modify: `web/src/main.tsx`
- Create: `web/src/app.css`
- Modify: repo `README.md` (dashboard + demo section)

**Interfaces:**
- Consumes: `Playground`, `EvalAnalytics`.
- Produces: `App()` — renders a header with two nav buttons that switch between the Playground and Eval Analytics views.

- [ ] **Step 1: Write the failing App test**

`web/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { App } from "./App";

vi.mock("./playground/Playground", () => ({ Playground: () => <div>PLAYGROUND</div> }));
vi.mock("./evals/EvalAnalytics", () => ({ EvalAnalytics: () => <div>ANALYTICS</div> }));

it("shows the playground by default and switches to analytics", async () => {
  render(<App />);
  expect(screen.getByText("PLAYGROUND")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Eval Analytics" }));
  expect(screen.getByText("ANALYTICS")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd web && npm test -- App`
Expected: FAIL — current scaffold `App` renders the Vite demo, not the tabs.

- [ ] **Step 3: Implement the App shell**

Replace `web/src/App.tsx`:
```tsx
import { useState } from "react";

import "./app.css";
import { EvalAnalytics } from "./evals/EvalAnalytics";
import { Playground } from "./playground/Playground";

type Tab = "playground" | "evals";

export function App() {
  const [tab, setTab] = useState<Tab>("playground");
  return (
    <div className="app">
      <header className="app-header">
        <h1>Code Review Assistant</h1>
        <nav className="tabs">
          <button
            aria-current={tab === "playground"}
            onClick={() => setTab("playground")}
          >
            Playground
          </button>
          <button aria-current={tab === "evals"} onClick={() => setTab("evals")}>
            Eval Analytics
          </button>
        </nav>
      </header>
      <main className="app-main">
        {tab === "playground" ? <Playground /> : <EvalAnalytics />}
      </main>
    </div>
  );
}
```

Replace `web/src/main.tsx` (the scaffold may use a default-export `App`; this plan uses a named export):
```tsx
import React from "react";
import ReactDOM from "react-dom/client";

import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
```

- [ ] **Step 4: Add baseline styles**

`web/src/app.css` (hand-rolled; keep it lean and legible):
```css
:root {
  --bg: #0b0f17;
  --panel: #141a24;
  --text: #e6edf3;
  --muted: #93a1b0;
  --accent: #2563eb;
  --pass: #059669;
  --fail: #dc2626;
  font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
}
body { margin: 0; background: var(--bg); color: var(--text); }
.app-header { display: flex; align-items: baseline; gap: 1.5rem; padding: 1rem 1.5rem; border-bottom: 1px solid #222b38; }
.app-header h1 { font-size: 1.1rem; margin: 0; }
.tabs button, .mode-toggle button { background: transparent; color: var(--muted); border: 0; padding: .4rem .75rem; cursor: pointer; border-radius: 6px; }
.tabs button[aria-current="true"], .mode-toggle button[aria-selected="true"] { background: var(--panel); color: var(--text); }
.app-main { padding: 1.5rem; max-width: 960px; margin: 0 auto; }
.review-form textarea, .review-form input { width: 100%; box-sizing: border-box; background: var(--panel); color: var(--text); border: 1px solid #2a3442; border-radius: 6px; padding: .6rem; font-family: ui-monospace, monospace; }
.review-form button[type="submit"] { margin-top: .75rem; background: var(--accent); color: #fff; border: 0; padding: .55rem 1.1rem; border-radius: 6px; cursor: pointer; }
.review-form button[type="submit"]:disabled { opacity: .6; cursor: default; }
.badge { color: #fff; font-size: .7rem; text-transform: uppercase; padding: .1rem .4rem; border-radius: 4px; letter-spacing: .03em; }
.finding { background: var(--panel); border: 1px solid #222b38; border-radius: 8px; padding: .75rem; margin: .5rem 0; list-style: none; }
.finding-head { display: flex; gap: .6rem; align-items: center; }
.loc { font-family: ui-monospace, monospace; color: var(--muted); font-size: .85rem; }
.cat { font-size: .75rem; color: var(--muted); }
.suggestion { color: var(--muted); }
.gauge { display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin: 1rem 0; }
.gauge-value { font-size: 1.6rem; font-weight: 700; }
.gauge-bar { flex: 1; min-width: 120px; height: 8px; background: #2a3442; border-radius: 4px; overflow: hidden; }
.gauge-fill { height: 100%; background: var(--pass); }
.chip { font-size: .75rem; padding: .15rem .5rem; border-radius: 999px; background: #2a3442; }
.notice, .error, .empty-state { padding: .6rem .8rem; border-radius: 6px; margin: .75rem 0; }
.notice { background: #1f2a1a; }
.error { background: #2a1416; color: #fca5a5; }
.empty-state { background: var(--panel); color: var(--muted); }
.report-table, .spans table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
.report-table th, .report-table td, .spans th, .spans td { text-align: left; padding: .4rem .6rem; border-bottom: 1px solid #222b38; }
.report-table tr[data-status="pass"] td:first-child { color: var(--pass); }
.report-table tr[data-status="fail"] td:first-child { color: var(--fail); }
.langfuse-link { color: var(--accent); }
```

- [ ] **Step 5: Run the full web suite, typecheck, and production build**

Run: `cd web && npm test && npx tsc --noEmit && npm run build`
Expected: all tests pass; no type errors; `dist/` builds cleanly.

- [ ] **Step 6: Add a dashboard section to the repo `README.md`**

Append to `README.md`:
````markdown
## Dashboard (web/)

A Vite + React + TS dashboard with two views:

- **Review Playground** — paste a diff or a GitHub PR URL, get annotated findings,
  an overall score gauge, and a per-node span table.
- **Eval Analytics** — RAGAS score trends across runs and a per-PR drill-down,
  gated visually at the 0.75 threshold.

```bash
# 1. Run the API populated with a real model (the mock returns empty findings):
export LLM_PROVIDER=groq GROQ_API_KEY=...   # or gemini / GEMINI_API_KEY
uv run uvicorn api.main:app

# 2. In another shell, run the dashboard dev server (proxies to the API on :8000):
cd web && npm install && npm run dev   # http://localhost:5173
```

The dashboard reads eval reports from the API (`GET /eval/reports`), which serves
the JSON written by `python -m evals.run_eval`. Set `VITE_LANGFUSE_URL` to show an
"Open in Langfuse" link in the analytics view. Run the frontend tests with
`cd web && npm test`.
````

- [ ] **Step 7: Commit**

```bash
git add web/src/App.tsx web/src/App.test.tsx web/src/main.tsx web/src/app.css README.md
git commit -m "feat: dashboard app shell, styling, and README"
```

---

## Self-review notes (spec coverage)

- **Spec §1 / §5 Review Playground** → Task 3 (ReviewForm one-of toggle, FindingsList grouped + badges, ScoreGauge, SpansPanel, trivial + error states) + Task 2 (`postReview`).
- **Spec §1 / §6 Eval Analytics** → Task 4 (TrendChart with 0.75 reference line, ReportTable pass/fail at boundary, EmptyState) + Task 1 endpoints + Task 2 (`getReports`/`getReport`). Langfuse single env-gated link in `EvalAnalytics`.
- **Spec §2 decisions** — API endpoints (Task 1), no streaming (single `postReview`), hand-rolled CSS + Recharts (Tasks 3–5), real-provider demo (README in Task 5).
- **Spec §3 Backend additions** — CORS + `GET /eval/reports` + `GET /eval/reports/{id}`, read-only over existing files → Task 1, with tests for empty dir, summaries, full report, 404, and CORS header.
- **Spec §7 Project shape** — covered file-for-file (router replaced by a lighter two-tab shell, noted in §2 of this plan; no behavior lost).
- **Spec §8 Testing** — frontend Vitest/RTL with stubbed fetch / mocked api (Tasks 2–5); backend pytest (Task 1). TrendChart's non-test is explained inline (Recharts + jsdom).
- **Spec §9 Out of scope** — no streaming, no auth, `web/` not in CI, no per-item trace IDs. Honored.

## Done criteria

- `uv run pytest -q` green (incl. new `tests/test_eval_endpoints.py`); `uv run ruff check .` clean.
- `cd web && npm test` green; `npx tsc --noEmit` clean; `npm run build` produces `dist/`.
- `uv run uvicorn api.main:app` + `cd web && npm run dev`: Playground returns annotated findings against a real provider; Eval Analytics shows the trend + table after `python -m evals.run_eval` has written a report (and a friendly empty state before that).
