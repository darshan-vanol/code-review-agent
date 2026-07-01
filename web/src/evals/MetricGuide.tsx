// Plain-language explanation of what the eval actually measures, so the scores
// below aren't just an unlabelled wall of decimals.
export function MetricGuide({ threshold }: { threshold: number }) {
  return (
    <section className="guide" aria-label="what these scores mean">
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Faithfulness</h3>
        <p>
          Are the review's claims grounded in the actual diff? A high score means the
          agent flags issues that are really in the code — not hallucinated ones.
        </p>
      </div>
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Answer correctness</h3>
        <p>
          How closely the findings match the golden review for each diff — the right
          issues, described accurately, without missing the important ones.
        </p>
      </div>
      <p className="guide-note">
        <span>
          <b>Pass bar {threshold.toFixed(2)}</b> — an item passes only when both metrics
          reach the bar; the run passes only when both averages do.
        </span>
        <span>
          <b>n/a</b> — the judge couldn't score the item (usually a truncated or empty
          response). It counts as not passing.
        </span>
      </p>
    </section>
  );
}
