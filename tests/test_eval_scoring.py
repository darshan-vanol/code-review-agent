from evals.scoring import (
    aggregate_scores,
    passes_threshold,
    render_report,
)

_ITEMS = [
    {"id": "a", "score": 0.9, "recall": 1.0},
    {"id": "b", "score": 0.7, "recall": 0.8},
]


def test_aggregate_means():
    agg = aggregate_scores(_ITEMS)
    assert round(agg["score"], 3) == 0.8
    assert round(agg["recall"], 3) == 0.9


def test_aggregate_empty_is_zero():
    assert aggregate_scores([]) == {"score": 0.0, "recall": 0.0}


def test_passes_threshold_gates_on_score_only():
    # recall below the bar must NOT fail the run; only score gates.
    assert passes_threshold({"score": 0.8, "recall": 0.1}, 0.75)
    assert not passes_threshold({"score": 0.5, "recall": 1.0}, 0.75)


def test_render_report_marks_pass_and_lists_items():
    agg = aggregate_scores(_ITEMS)
    report, md = render_report(agg, _ITEMS, threshold=0.7)
    assert report["threshold"] == 0.7
    assert report["passed"] is True
    assert len(report["items"]) == 2
    assert "PASS" in md
    assert "| a |" in md


def test_render_report_marks_fail():
    items = [{"id": "x", "score": 0.5, "recall": 0.5}]
    report, md = render_report(aggregate_scores(items), items, threshold=0.7)
    assert report["passed"] is False
    assert "FAIL" in md
