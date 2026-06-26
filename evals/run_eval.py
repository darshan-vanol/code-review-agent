from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent.providers.factory import make_provider
from evals.dataset import load_golden
from evals.harness import build_records
from evals.scoring import THRESHOLD, aggregate_scores, render_report


def run(out_dir: Path, *, provider=None, scorer=None, goldens=None,
        threshold: float = THRESHOLD) -> int:
    """Build records, score them, write reports, return 0 (pass) or 1 (fail)."""
    provider = provider if provider is not None else make_provider()
    if scorer is None:
        from evals.ragas_scorer import score_with_ragas
        scorer = score_with_ragas
    goldens = goldens if goldens is not None else load_golden()

    records = build_records(goldens, provider)
    per_item = scorer(records)
    scores = aggregate_scores(per_item)
    report, markdown = render_report(scores, per_item, threshold=threshold)

    out_dir.mkdir(parents=True, exist_ok=True)
    n = len(list(out_dir.glob("*.json"))) + 1
    (out_dir / f"{n}.json").write_text(json.dumps(report, indent=2))
    (out_dir / f"{n}.md").write_text(markdown)
    print(markdown)
    return 0 if report["passed"] else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RAGAS eval harness.")
    parser.add_argument("--out-dir", default="evals/reports", type=Path)
    parser.add_argument("--threshold", default=THRESHOLD, type=float)
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()
    provider = make_provider(args.provider) if args.provider else make_provider()
    sys.exit(run(args.out_dir, provider=provider, threshold=args.threshold))


if __name__ == "__main__":
    main()
