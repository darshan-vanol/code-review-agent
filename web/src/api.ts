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
  score: number;
  recall: number;
}

export interface EvalReportSummary {
  id: string;
  passed: boolean;
  aggregate: EvalAggregate;
}

export interface EvalItem {
  id: string;
  score: number;
  recall: number;
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

// The stages the review streams back, in the order they run. "fetch" only
// appears when reviewing a PR URL.
export type ReviewStage =
  | "fetch"
  | "ingest"
  | "security"
  | "logic"
  | "test_coverage"
  | "aggregate";

/**
 * Stream a review, calling `onStage` as each stage finishes, and resolving with
 * the final result. Consumes the newline-delimited JSON emitted by
 * POST /review/stream.
 */
export async function postReviewStream(
  body: { diff?: string; pr_url?: string },
  onStage: (stage: ReviewStage) => void,
): Promise<ReviewResponse> {
  const res = await fetch(`${BASE}/review/stream`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    // A validation error (422) etc. arrives as a normal JSON error body.
    return asJson<ReviewResponse>(res);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: ReviewResponse | null = null;

  const handle = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const evt = JSON.parse(trimmed) as
      | { type: "progress"; stage: ReviewStage }
      | { type: "result"; data: ReviewResponse }
      | { type: "error"; detail: string };
    if (evt.type === "progress") onStage(evt.stage);
    else if (evt.type === "result") result = evt.data;
    else throw new Error(evt.detail);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) handle(line);
  }
  handle(buffer);

  if (!result) throw new Error("Review ended without a result.");
  return result;
}

export async function getReports(): Promise<EvalReportSummary[]> {
  const res = await fetch(`${BASE}/eval/reports`);
  return asJson<EvalReportSummary[]>(res);
}

export async function getReport(id: string): Promise<EvalReport> {
  const res = await fetch(`${BASE}/eval/reports/${id}`);
  return asJson<EvalReport>(res);
}
