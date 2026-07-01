import type { ReviewScore } from "../api";

// Mirrors the backend penalty weights in agent/state.py so the tooltip explains
// exactly why the number moved.
const EXPLAINER =
  "Cleanliness starts at 100% and drops with each issue by severity " +
  "(low −10, medium −30, high −60, critical −100). It bottoms out at 0% once " +
  "issues are serious enough — read the counts for the full picture.";

export function ScoreGauge({ score }: { score: ReviewScore }) {
  const pct = Math.round(score.overall * 100);
  const band = pct >= 75 ? "pass" : pct >= 40 ? "near" : "low";
  return (
    <div className="gauge" title={EXPLAINER}>
      <div className="gauge-head">
        <span className="eyebrow">Cleanliness</span>
        <div className="gauge-value" aria-label="cleanliness score">
          {pct}%
        </div>
      </div>
      <div className="gauge-bar">
        <div className="gauge-fill" data-band={band} style={{ width: `${pct}%` }} />
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
      <p className="gauge-hint">
        100% = clean; each issue lowers it by severity. See the counts for detail.
      </p>
    </div>
  );
}
