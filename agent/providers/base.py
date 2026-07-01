from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str


@runtime_checkable
class LLMProvider(Protocol):
    """Abstracts a chat-completion model. Implementations must be swappable
    behind this interface (mock, Groq, Gemini, OpenAI, Anthropic)."""

    @property
    def model(self) -> str:
        """The model name this provider is configured to call. Exposed so the
        API/UI can show it before any completion runs."""
        ...

    def complete(self, system: str, user: str) -> LLMResponse:
        ...
