import type { EvalReport } from "../api";

const THRESHOLD = 0.75;

// A metric is null when the judge couldn't score that item (e.g. a truncated
// response). Show it as "n/a" and treat it as not meeting the threshold.
const fmt = (v: number | null) => (v === null ? "n/a" : v.toFixed(2));
const meets = (v: number | null) => v !== null && v >= THRESHOLD;

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
          const pass = meets(it.faithfulness) && meets(it.answer_correctness);
          const status = pass ? "pass" : "fail";
          return (
            <tr key={it.id} className={status} data-status={status}>
              <td>{it.id}</td>
              <td>{fmt(it.faithfulness)}</td>
              <td>{fmt(it.answer_correctness)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
