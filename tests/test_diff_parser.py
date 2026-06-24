from pathlib import Path

from agent.diff_parser import is_trivial, parse_diff

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_diff_extracts_file_and_counts():
    files = parse_diff(_read("simple_python.diff"))
    assert len(files) == 1
    assert files[0].path == "app.py"
    assert files[0].added_lines == 4
    assert files[0].removed_lines == 1
    assert any("sqlite3" in h for h in files[0].hunks)


def test_parse_empty_diff_returns_empty_list():
    assert parse_diff("") == []


def test_is_trivial_true_for_whitespace_and_docs():
    files = parse_diff(_read("trivial_whitespace.diff"))
    assert is_trivial(files) is True


def test_is_trivial_false_for_code_changes():
    files = parse_diff(_read("simple_python.diff"))
    assert is_trivial(files) is False


def test_parse_deletion_diff_is_captured_and_not_trivial():
    # A pure deletion uses `+++ /dev/null`; the file must still be parsed
    # (path from the `diff --git` header) so code removals get reviewed.
    files = parse_diff(_read("deleted_file.diff"))
    assert len(files) == 1
    assert files[0].path == "old_helper.py"
    assert files[0].removed_lines == 3
    assert files[0].added_lines == 0
    assert is_trivial(files) is False
