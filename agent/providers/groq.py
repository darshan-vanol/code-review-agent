from __future__ import annotations

import os
import time

import httpx

from agent.providers.base import LLMResponse

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_S = 60.0


class GroqProvider:
    """LLMProvider backed by Groq's OpenAI-compatible chat completions API."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = _DEFAULT_MODEL,
        client: httpx.Client | None = None,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self._model = model
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)

    def complete(self, system: str, user: str) -> LLMResponse:
        start = time.perf_counter()
        resp = self._client.post(
            _GROQ_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        latency_ms = (time.perf_counter() - start) * 1000
        usage = data.get("usage", {})
        return LLMResponse(
            text=data["choices"][0]["message"]["content"],
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            model=self._model,
        )
