from __future__ import annotations

import os

from agent.providers.base import LLMProvider
from agent.providers.gemini import GeminiProvider
from agent.providers.groq import GroqProvider
from agent.providers.mock import MockProvider


def make_provider(name: str | None = None) -> LLMProvider:
    """Build an LLMProvider by name, falling back to $LLM_PROVIDER then "mock".

    Real providers read their own key from the environment (GROQ_API_KEY /
    GEMINI_API_KEY); the mock needs nothing, so the system runs offline by
    default."""
    name = (name or os.environ.get("LLM_PROVIDER", "mock")).lower()
    if name == "mock":
        return MockProvider()
    if name == "groq":
        return GroqProvider()
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"Unknown LLM provider {name!r}; expected mock|groq|gemini")
