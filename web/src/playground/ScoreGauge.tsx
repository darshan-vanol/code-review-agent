import type { ReviewScore } from "../api";

export function ScoreGauge({ score }: { score: ReviewScore }) {
  const pct = Math.round(score.overall * 100);
  return (
    <div className="gauge">
      <div className="gauge-value" aria-label="overall score">
        {pct}%
      </div>
      <div className="gauge-bar">
        <div className="gauge-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="counts">
        {Object.entries(score.counts)
          .filter(([, n]) => n > 0)
          .map(([sev, n]) => (
            <span key={sev} className={`chip sev-${sev}`}>
              {sev}: {n}
            </span>
          ))}
      </div>
    </div>
  );
}
