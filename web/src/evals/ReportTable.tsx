import type { EvalReport } from "../api";
import { ScoreMeter } from "./ScoreMeter";

const fmt = (v: number) => v.toFixed(2);

function ScoreCell({ value, threshold }: { value: number; threshold: number }) {
  return (
    <div className="cell-score">
      <ScoreMeter value={value} threshold={threshold} height={8} />
      <span className="num">{fmt(value)}</span>
    </div>
  );
}

export function ReportTable({ report }: { report: EvalReport }) {
  const threshold = report.threshold;
  return (
    <table className="report-table">
      <thead>
        <tr>
          <th className="col-id">diff</th>
          <th className="col-metric">score</th>
          <th className="col-metric">recall</th>
          <th>result</th>
        </tr>
      </thead>
      <tbody>
        {report.items.map((it) => {
          const pass = it.score >= threshold;
          const status = pass ? "pass" : "fail";
          return (
            <tr key={it.id} className={status} data-status={status}>
              <td className="col-id">{it.id}</td>
              <td className="col-metric">
                <ScoreCell value={it.score} threshold={threshold} />
              </td>
              <td className="col-metric">
                <ScoreCell value={it.recall} threshold={threshold} />
              </td>
              <td>
                <span className="pill" data-status={status}>
                  {pass ? "pass" : "fail"}
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
