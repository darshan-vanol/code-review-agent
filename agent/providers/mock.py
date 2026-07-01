from __future__ import annotations

import json

from agent.providers.base import LLMResponse

# Deterministic synthetic latency (ms) so traces look realistic without a clock.
_FAKE_LATENCY_MS = 42.0
_MODEL_NAME = "mock-1"


def _estimate_tokens(text: str) -> int:
    # Rough, deterministic token estimate: ~4 chars per token, min 1.
    return max(1, len(text) // 4)


class MockProvider:
    """Deterministic provider for offline tests and CI.

    `scripted` maps a keyword -> list of finding dicts. When the user prompt
    contains the keyword, the mock returns {"findings": [...]} as JSON. Otherwise
    it returns an empty findings list. This lets node tests assert exact output.
    """

    def __init__(self, scripted: dict[str, list[dict]] | None = None):
        self._scripted = scripted or {}

    @property
    def model(self) -> str:
        return _MODEL_NAME

    def complete(self, system: str, user: str) -> LLMResponse:
        findings: list[dict] = []
        for keyword, value in self._scripted.items():
            if keyword in user.lower():
                findings = value
                break
        text = json.dumps({"findings": findings})
        return LLMResponse(
            text=text,
            input_tokens=_estimate_tokens(system + user),
            output_tokens=_estimate_tokens(text),
            latency_ms=_FAKE_LATENCY_MS,
            model=_MODEL_NAME,
        )
