// Plain-language explanation of what the eval actually measures, so the scores
// below aren't just an unlabelled wall of decimals.
export function MetricGuide({ threshold }: { threshold: number }) {
  return (
    <section className="guide" aria-label="what these scores mean">
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Score</h3>
        <p>
          Did the agent catch the known bug in each diff, with a small penalty for
          noisy extra findings? This is the number the pass bar gates on.
        </p>
      </div>
      <div className="guide-card">
        <span className="eyebrow">Metric</span>
        <h3>Recall</h3>
        <p>
          The share of the golden findings the agent detected — how many real issues
          it caught, ignoring any extra noise.
        </p>
      </div>
      <p className="guide-note">
        <span>
          <b>Pass bar {threshold.toFixed(2)}</b> — an item passes when its score
          reaches the bar; the run passes when the average score does.
        </span>
      </p>
    </section>
  );
}
