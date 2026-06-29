import { useEffect, useState } from "react";

import { type EvalReport, type EvalReportSummary, getReport, getReports } from "../api";
import { EmptyState } from "../components/EmptyState";
import { ReportTable } from "./ReportTable";
import { TrendChart } from "./TrendChart";

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

  return (
    <div className="analytics">
      {LANGFUSE_URL && (
        <a className="langfuse-link" href={LANGFUSE_URL} target="_blank" rel="noreferrer">
          Open in Langfuse ↗
        </a>
      )}
      {reports.length > 1 && (
        <select
          aria-label="select report"
          className="report-picker"
          value={selectedId ?? ""}
          onChange={(e) => void selectReport(e.target.value)}
        >
          {reports.map((r) => (
            <option key={r.id} value={r.id}>
              {r.id} {r.passed ? "✓" : "✗"}
            </option>
          ))}
        </select>
      )}
      <TrendChart reports={reports} />
      {selected && <ReportTable report={selected} />}
    </div>
  );
}
