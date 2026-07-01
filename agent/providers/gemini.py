from __future__ import annotations

import os
import time

import httpx

from agent.providers.base import LLMResponse

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_DEFAULT_MODEL = "gemini-2.0-flash"
_TIMEOUT_S = 60.0


class GeminiProvider:
    """LLMProvider backed by Google's Gemini generateContent REST API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)

    @property
    def model(self) -> str:
        return self._model

    def complete(self, system: str, user: str) -> LLMResponse:
        start = time.perf_counter()
        url = f"{_BASE}/{self._model}:generateContent?key={self._api_key}"
        resp = self._client.post(
            url,
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"parts": [{"text": user}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "temperature": 0,
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000
        usage = data.get("usageMetadata", {})
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return LLMResponse(
            text=text,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)),
            latency_ms=latency_ms,
            model=self._model,
        )
