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
  // null when the judge failed to score the item (e.g. a truncated response).
  faithfulness: number | null;
  answer_correctness: number | null;
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
