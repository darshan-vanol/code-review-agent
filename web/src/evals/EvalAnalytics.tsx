import { useEffect, useState } from "react";

import { type EvalReport, type EvalReportSummary, getReport, getReports } from "../api";
import { EmptyState } from "../components/EmptyState";
import { MetricGuide } from "./MetricGuide";
import { ReportTable } from "./ReportTable";
import { TrendChart } from "./TrendChart";
import { VerdictBanner } from "./VerdictBanner";

const LANGFUSE_URL = import.meta.env.VITE_LANGFUSE_URL as string | undefined;

export function EvalAnalytics() {
  const [reports, setReports] = useState<EvalReportSummary[]>([]);
  const [selected, setSelected] = useState<EvalReport | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  async function selectReport(id: string) {
    setSelectedId(id);
    try {
      setSelected(await getReport(id));
    } catch {
      setSelected(null);
    }
  }

  useEffect(() => {
    getReports()
      .then(async (rs) => {
        setReports(rs);
        if (rs.length > 0) {
          await selectReport(rs[rs.length - 1].id);
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

  const controls = (
    <>
      {reports.length > 1 && (
        <select
          aria-label="select report"
          className="report-picker"
          value={selectedId ?? ""}
          onChange={(e) => void selectReport(e.target.value)}
        >
          {reports.map((r) => (
            <option key={r.id} value={r.id}>
              run {r.id} · {r.passed ? "passed" : "failed"}
            </option>
          ))}
        </select>
      )}
      {LANGFUSE_URL && (
        <a className="langfuse-link" href={LANGFUSE_URL} target="_blank" rel="noreferrer">
          Traces in Langfuse ↗
        </a>
      )}
    </>
  );

  return (
    <div className="eval">
      {selected && <VerdictBanner report={selected} controls={controls} />}
      {selected && <MetricGuide threshold={selected.threshold} />}
      {selected && (
        <section>
          <div className="section-head">
            <h2>Per-diff scores</h2>
            <span className="hint">
              bar marks the {selected.threshold.toFixed(2)} pass threshold
            </span>
          </div>
          <ReportTable report={selected} />
        </section>
      )}
      <section>
        <div className="section-head">
          <h2>Score history</h2>
          <span className="hint">
            {reports.length > 1 ? `${reports.length} runs` : "one run so far"}
          </span>
        </div>
        <div className="trend-card">
          <TrendChart reports={reports} />
        </div>
      </section>
    </div>
  );
}
