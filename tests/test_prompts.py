import pytest

from agent.prompts import load_prompt


def test_load_known_prompt_returns_nonempty_text():
    text = load_prompt("security_scan")
    assert "findings" in text.lower()


def test_load_unknown_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
