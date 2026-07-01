from evals.detection_scorer import (
    PRECISION_PENALTY,
    finding_matches,
    score_by_detection,
    score_record,
)


def _f(file="a.py", ls=5, le=6, cat="security", sev="high", msg="m"):
    return {"file": file, "line_start": ls, "line_end": le,
            "severity": sev, "category": cat, "message": msg}


class _Rec:
    def __init__(self, id, agent, golden):
        self.id, self.agent_findings, self.golden_findings = id, agent, golden


def test_precision_penalty_is_point_two():
    assert PRECISION_PENALTY == 0.2


def test_matches_on_file_line_overlap_and_category():
    assert finding_matches(_f(ls=5, le=5), _f(ls=5, le=6))  # overlap
    assert finding_matches(_f(ls=6, le=9), _f(ls=5, le=6))  # touching overlap


def test_no_match_on_category_mismatch():
    assert not finding_matches(_f(cat="logic"), _f(cat="security"))


def test_no_match_on_disjoint_lines():
    assert not finding_matches(_f(ls=1, le=2), _f(ls=5, le=6))


def test_no_match_on_different_file():
    assert not finding_matches(_f(file="a.py"), _f(file="b.py"))


def test_perfect_catch_no_noise_scores_one():
    rec = _Rec("x", [_f()], [_f()])
    out = score_record(rec)
    assert out == {"id": "x", "score": 1.0, "recall": 1.0, "matched": 1,
                   "total_goldens": 1, "false_positives": 0,
                   "total_agent_findings": 1}


def test_missed_bug_scores_zero():
    rec = _Rec("x", [_f(ls=1, le=1)], [_f(ls=5, le=6)])
    out = score_record(rec)
    assert out["recall"] == 0.0
    # recall 0, fp_rate 1.0 -> 0 - 0.2 -> clamped to 0.0
    assert out["score"] == 0.0


def test_light_precision_penalty_on_extra_findings():
    # 1 golden caught + 2 noise findings: recall 1, fp_rate 2/3
    rec = _Rec("x", [_f(), _f(cat="logic"), _f(cat="test")], [_f()])
    out = score_record(rec)
    assert out["recall"] == 1.0
    assert out["false_positives"] == 2
    assert round(out["score"], 4) == round(1.0 - 0.2 * (2 / 3), 4)


def test_empty_agent_findings_scores_zero():
    rec = _Rec("x", [], [_f()])
    out = score_record(rec)
    assert out == {"id": "x", "score": 0.0, "recall": 0.0, "matched": 0,
                   "total_goldens": 1, "false_positives": 0,
                   "total_agent_findings": 0}


def test_score_by_detection_maps_all_records():
    recs = [_Rec("a", [_f()], [_f()]), _Rec("b", [], [_f()])]
    out = score_by_detection(recs)
    assert [o["id"] for o in out] == ["a", "b"]
    assert out[0]["score"] == 1.0 and out[1]["score"] == 0.0
