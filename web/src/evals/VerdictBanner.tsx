import type { EvalReport } from "../api";
import { ScoreMeter } from "./ScoreMeter";

function VerdictMetric({
  name,
  value,
  threshold,
}: {
  name: string;
  value: number;
  threshold: number;
}) {
  return (
    <div className="vmetric">
      <div className="vmetric-label">
        <span className="vmetric-name">{name}</span>
        <span className="vmetric-val">{value.toFixed(2)}</span>
      </div>
      <ScoreMeter value={value} threshold={threshold} height={12} />
    </div>
  );
}

/**
 * The hero: does this run pass, and by how much? Leads with the verdict word and
 * the count of items that cleared the bar, then the two aggregate meters.
 * `controls` slots in the run picker / Langfuse link on the right.
 */
export function VerdictBanner({
  report,
  controls,
}: {
  report: EvalReport;
  controls?: React.ReactNode;
}) {
  const cleared = report.items.filter(
    (it) =>
      it.faithfulness !== null &&
      it.faithfulness >= report.threshold &&
      it.answer_correctness !== null &&
      it.answer_correctness >= report.threshold,
  ).length;
  const total = report.items.length;

  return (
    <section className="verdict" data-passed={report.passed} aria-label="run verdict">
      <div className="verdict-top">
        <div>
          <span className="eyebrow">Evaluation run</span>
          <div className="verdict-status">
            <span className="verdict-word">{report.passed ? "Passed" : "Failed"}</span>
            <span className="verdict-ratio">
              <strong>
                {cleared} / {total}
              </strong>{" "}
              diffs cleared the bar
            </span>
          </div>
        </div>
        {controls && <div className="run-meta">{controls}</div>}
      </div>

      <div className="verdict-metrics">
        <VerdictMetric
          name="Faithfulness"
          value={report.aggregate.faithfulness}
          threshold={report.threshold}
        />
        <VerdictMetric
          name="Answer correctness"
          value={report.aggregate.answer_correctness}
          threshold={report.threshold}
        />
      </div>
    </section>
  );
}
