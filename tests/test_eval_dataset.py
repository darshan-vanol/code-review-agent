from evals.dataset import GoldenPR, load_golden

_VALID_CATEGORIES = {"security", "logic", "test"}
_REQUIRED_LANGUAGES = {"python", "javascript", "go"}
_FINDING_KEYS = {"file", "line_start", "line_end", "severity", "category",
                 "message", "suggestion"}


def test_loads_exactly_twenty_golden_prs():
    goldens = load_golden()
    assert len(goldens) == 20
    assert all(isinstance(g, GoldenPR) for g in goldens)


def test_ids_are_unique():
    ids = [g.id for g in load_golden()]
    assert len(ids) == len(set(ids))


def test_every_pr_is_well_formed():
    for g in load_golden():
        assert g.diff.strip(), f"{g.id} has empty diff"
        assert "diff --git" in g.diff, f"{g.id} is not a unified diff"
        assert g.category in _VALID_CATEGORIES, f"{g.id} bad category {g.category}"
        assert g.summary.strip(), f"{g.id} has empty summary"
        assert g.findings, f"{g.id} has no ground-truth findings"
        for f in g.findings:
            assert _FINDING_KEYS <= set(f), f"{g.id} finding missing keys"


def test_dataset_covers_all_categories_and_languages():
    goldens = load_golden()
    assert {g.category for g in goldens} == _VALID_CATEGORIES
    assert _REQUIRED_LANGUAGES <= {g.language for g in goldens}
