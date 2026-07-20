from pathlib import Path

from agent.nodes.ingest import ingest_node
from agent.state import ReviewState

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_populates_files_and_trivial_flag():
    state = ReviewState(raw_diff=(FIXTURES / "simple_python.diff").read_text())
    out = ingest_node(state)
    assert len(out.files) == 1
    assert out.files[0].path == "app.py"
    assert out.is_trivial is False


def test_ingest_marks_whitespace_diff_trivial():
    state = ReviewState(raw_diff=(FIXTURES / "trivial_whitespace.diff").read_text())
    out = ingest_node(state)
    assert out.is_trivial is True


def test_ingest_unparsed_code_is_not_trivial():
    state = ReviewState(raw_diff='def foo():\n    return eval(input())\n')
    out = ingest_node(state)
    assert out.files == []
    assert out.is_trivial is False


def test_ingest_empty_input_is_trivial():
    out = ingest_node(ReviewState(raw_diff=""))
    assert out.files == []
    assert out.is_trivial is True
