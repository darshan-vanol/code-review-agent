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
