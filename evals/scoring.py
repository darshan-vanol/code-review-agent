from __future__ import annotations

THRESHOLD = 0.75
_METRICS = ("score", "recall")


def aggregate_scores(per_item: list[dict]) -> dict[str, float]:
    agg: dict[str, float] = {}
    for m in _METRICS:
        values = [item[m] for item in per_item if item.get(m) is not None]
        agg[m] = sum(values) / len(values) if values else 0.0
    return agg


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def passes_threshold(scores: dict[str, float], threshold: float = THRESHOLD) -> bool:
    # Gate on detection score only; recall is reported but not gated.
    return scores["score"] >= threshold


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
        f"- Score: {_fmt(scores['score'])}",
        f"- Recall: {_fmt(scores['recall'])}",
        "",
        "| id | score | recall |",
        "| --- | --- | --- |",
    ]
    for item in per_item:
        lines.append(
            f"| {item['id']} | {_fmt(item.get('score'))} "
            f"| {_fmt(item.get('recall'))} |"
        )
    return report, "\n".join(lines)
