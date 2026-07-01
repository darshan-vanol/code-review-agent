import type { EvalReport } from "../api";
import { ScoreMeter } from "./ScoreMeter";

const THRESHOLD = 0.75;

// A metric is null when the judge couldn't score that item (e.g. a truncated
// response). Show it as "n/a" and treat it as not meeting the threshold.
const fmt = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));
const meets = (v: number | null) => v !== null && v >= THRESHOLD;

function ScoreCell({ value }: { value: number | null }) {
  return (
    <div className="cell-score">
      <ScoreMeter value={value} threshold={THRESHOLD} height={8} />
      <span className={value === null ? "num na" : "num"}>{fmt(value)}</span>
    </div>
  );
}

export function ReportTable({ report }: { report: EvalReport }) {
  return (
    <table className="report-table">
      <thead>
        <tr>
          <th className="col-id">diff</th>
          <th className="col-metric">faithfulness</th>
          <th className="col-metric">answer correctness</th>
          <th>result</th>
        </tr>
      </thead>
      <tbody>
        {report.items.map((it) => {
          const pass = meets(it.faithfulness) && meets(it.answer_correctness);
          const status = pass ? "pass" : "fail";
          return (
            <tr key={it.id} className={status} data-status={status}>
              <td className="col-id">{it.id}</td>
              <td className="col-metric">
                <ScoreCell value={it.faithfulness} />
              </td>
              <td className="col-metric">
                <ScoreCell value={it.answer_correctness} />
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
