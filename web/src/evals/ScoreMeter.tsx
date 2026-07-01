type Band = "pass" | "near" | "low";

// Band by distance from the pass bar, so a 0.67 reads "almost" and a 0.00
// reads "way off" — richer than a flat pass/fail color.
function band(value: number, threshold: number): Band {
  if (value >= threshold) return "pass";
  if (value >= threshold * 0.66) return "near";
  return "low";
}

/**
 * A value riding on a track, with a notch marking the pass threshold.
 * The width shows the raw score; the color shows how far it is from the bar.
 * A null value (judge couldn't score the item) renders as an empty track.
 */
export function ScoreMeter({
  value,
  threshold,
  height = 10,
}: {
  value: number | null;
  threshold: number;
  height?: number;
}) {
  const pct = value === null ? 0 : Math.round(value * 100);
  return (
    <div className="meter" style={{ ["--meter-h" as string]: `${height}px` }}>
      {value !== null && (
        <div className="meter-fill" data-band={band(value, threshold)} style={{ width: `${pct}%` }} />
      )}
      <div className="meter-notch" style={{ left: `${threshold * 100}%` }} aria-hidden />
    </div>
  );
}
