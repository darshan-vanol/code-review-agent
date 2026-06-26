from __future__ import annotations

THRESHOLD = 0.75
_METRICS = ("faithfulness", "answer_correctness")


def aggregate_scores(per_item: list[dict]) -> dict[str, float]:
    if not per_item:
        return {m: 0.0 for m in _METRICS}
    return {
        m: sum(item[m] for item in per_item) / len(per_item) for m in _METRICS
    }


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
        f"- Faithfulness: {scores['faithfulness']:.3f}",
        f"- Answer correctness: {scores['answer_correctness']:.3f}",
        "",
        "| id | faithfulness | answer_correctness |",
        "| --- | --- | --- |",
    ]
    for item in per_item:
        lines.append(
            f"| {item['id']} | {item['faithfulness']:.3f} "
            f"| {item['answer_correctness']:.3f} |"
        )
    return report, "\n".join(lines)
