from __future__ import annotations

THRESHOLD = 0.75
_METRICS = ("faithfulness", "answer_correctness")


def aggregate_scores(per_item: list[dict]) -> dict[str, float]:
    # A metric may be None for an item when the judge response was truncated /
    # failed to score; average over the items that did score (0.0 if none did).
    agg: dict[str, float] = {}
    for m in _METRICS:
        values = [item[m] for item in per_item if item.get(m) is not None]
        agg[m] = sum(values) / len(values) if values else 0.0
    return agg


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def passes_threshold(scores: dict[str, float], threshold: float = THRESHOLD) -> bool:
    return all(scores[m] >= threshold for m in _METRICS)


def render_report(
    scores: dict[str, float], per_item: list[dict], *, threshold: float = THRESHOLD
) -> tuple[dict, str]:
    passed = passes_threshold(scores, threshold)
    report = {
        "aggregate": scores,
        "threshold": threshold,
        "passed": passed,
        "items": per_item,
    }
    status = "PASS" if passed else "FAIL"
    lines = [
        f"# Eval Report — {status}",
        "",
        f"- Threshold: {threshold}",
        f"- Faithfulness: {_fmt(scores['faithfulness'])}",
        f"- Answer correctness: {_fmt(scores['answer_correctness'])}",
        "",
        "| id | faithfulness | answer_correctness |",
        "| --- | --- | --- |",
    ]
    for item in per_item:
        lines.append(
            f"| {item['id']} | {_fmt(item.get('faithfulness'))} "
            f"| {_fmt(item.get('answer_correctness'))} |"
        )
    return report, "\n".join(lines)
