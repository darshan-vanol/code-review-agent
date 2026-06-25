import pytest

from agent.providers.factory import make_provider
from agent.providers.gemini import GeminiProvider
from agent.providers.groq import GroqProvider
from agent.providers.mock import MockProvider


def test_factory_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert isinstance(make_provider(), MockProvider)


def test_factory_explicit_names():
    assert isinstance(make_provider("groq"), GroqProvider)
    assert isinstance(make_provider("gemini"), GeminiProvider)


def test_factory_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    assert isinstance(make_provider(), GroqProvider)


def test_factory_unknown_raises():
    with pytest.raises(ValueError):
        make_provider("nope")
