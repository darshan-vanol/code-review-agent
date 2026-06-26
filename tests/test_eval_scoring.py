from evals.scoring import (
    THRESHOLD,
    aggregate_scores,
    passes_threshold,
    render_report,
)

_ITEMS = [
    {"id": "a", "faithfulness": 0.9, "answer_correctness": 0.8},
    {"id": "b", "faithfulness": 0.7, "answer_correctness": 0.8},
]


def test_aggregate_means():
    agg = aggregate_scores(_ITEMS)
    assert round(agg["faithfulness"], 3) == 0.8
    assert round(agg["answer_correctness"], 3) == 0.8


def test_aggregate_empty_is_zero():
    assert aggregate_scores([]) == {"faithfulness": 0.0, "answer_correctness": 0.0}


def test_passes_threshold_requires_both():
    assert passes_threshold({"faithfulness": 0.8, "answer_correctness": 0.76})
    assert not passes_threshold({"faithfulness": 0.8, "answer_correctness": 0.74})


def test_threshold_constant_is_point_seven_five():
    assert THRESHOLD == 0.75


def test_render_report_marks_pass_and_lists_items():
    agg = aggregate_scores(_ITEMS)
    report, md = render_report(agg, _ITEMS)
    assert report["threshold"] == 0.75
    assert report["passed"] is True
    assert len(report["items"]) == 2
    assert "PASS" in md
    assert "| a |" in md


def test_render_report_marks_fail():
    items = [{"id": "x", "faithfulness": 0.5, "answer_correctness": 0.5}]
    report, md = render_report(aggregate_scores(items), items)
    assert report["passed"] is False
    assert "FAIL" in md
