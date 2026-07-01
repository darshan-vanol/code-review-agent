import type { ReviewStage } from "../api";

type StageDef = { key: ReviewStage; label: string; prOnly?: boolean };

const STAGES: StageDef[] = [
  { key: "fetch", label: "Fetching PR diff", prOnly: true },
  { key: "ingest", label: "Parsing changed files" },
  { key: "security", label: "Scanning for security issues" },
  { key: "logic", label: "Analyzing logic" },
  { key: "test_coverage", label: "Checking test coverage" },
  { key: "aggregate", label: "Scoring" },
];

type State = "done" | "running" | "pending";

/**
 * Live checklist of the review pipeline. A stage is `done` once its event has
 * arrived; the first stage after the last done one is `running`. When the run
 * finishes, everything still pending is marked done (trivial diffs skip the
 * analysis stages, so their events never arrive).
 */
export function ProgressChecklist({
  done,
  isPr,
  finished,
}: {
  done: Set<ReviewStage>;
  isPr: boolean;
  finished: boolean;
}) {
  const stages = STAGES.filter((s) => !s.prOnly || isPr);
  const firstPending = stages.find((s) => !done.has(s.key));

  return (
    <ul className="progress" aria-label="review progress" aria-live="polite">
      {stages.map((s) => {
        let state: State = "pending";
        if (done.has(s.key) || finished) state = "done";
        else if (s.key === firstPending?.key) state = "running";
        return (
          <li key={s.key} className="progress-step" data-state={state}>
            <span className="progress-icon" aria-hidden />
            <span className="progress-label">{s.label}</span>
            <span className="progress-state">
              {state === "done" ? "done" : state === "running" ? "working…" : ""}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
