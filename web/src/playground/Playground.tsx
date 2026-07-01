import { useState } from "react";

import { postReviewStream, type ReviewResponse, type ReviewStage } from "../api";
import { FindingsList } from "./FindingsList";
import { ProgressChecklist } from "./ProgressChecklist";
import { ReviewForm } from "./ReviewForm";
import { ScoreGauge } from "./ScoreGauge";
import { SpansPanel } from "./SpansPanel";

export function Playground() {
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<Set<ReviewStage>>(new Set());
  const [isPr, setIsPr] = useState(false);

  async function run(body: { diff?: string; pr_url?: string }) {
    setLoading(true);
    setError(null);
    setResult(null);
    setDone(new Set());
    setIsPr(Boolean(body.pr_url));
    try {
      const res = await postReviewStream(body, (stage) =>
        setDone((prev) => new Set(prev).add(stage)),
      );
      setResult(res);
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
      {loading && <ProgressChecklist done={done} isPr={isPr} finished={false} />}
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
