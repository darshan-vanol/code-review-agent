from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

import httpx

from agent.providers.base import LLMResponse

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_DEFAULT_MODEL = "llama-3.3-70b-versatile"
_TIMEOUT_S = 60.0
_MAX_RETRIES = 6
_MAX_BACKOFF_S = 60.0

_DURATION_RE = re.compile(r"(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$")


def _parse_duration(value: str | None) -> float | None:
    """Parse Groq's rate-limit reset strings ("19.064s", "2m59.56s", "1h29m16.8s")
    into seconds. Returns None when the value is empty or unrecognized."""
    if not value:
        return None
    m = _DURATION_RE.fullmatch(value.strip())
    if not m or not any(m.groups()):
        return None
    h, mins, s = (float(g) if g else 0.0 for g in m.groups())
    return h * 3600 + mins * 60 + s


class GroqProvider:
    """LLMProvider backed by Groq's OpenAI-compatible chat completions API.

    Retries on 429 (rate limit) and 5xx, backing off by the duration Groq
    reports (Retry-After or x-ratelimit-reset-tokens) and falling back to
    exponential backoff. Groq's free tier caps tokens-per-minute aggressively,
    so a batch job (like the eval harness) will routinely exhaust the budget
    and must wait for the window to refill rather than crash."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
        max_retries: int = _MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self._api_key = api_key if api_key is not None else os.environ.get("GROQ_API_KEY", "")
        self._model = model or os.environ.get("GROQ_MODEL", _DEFAULT_MODEL)
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)
        self._max_retries = max_retries
        self._sleep = sleep

    def _retry_wait(self, resp: httpx.Response, attempt: int) -> float:
        """How long to wait before the next attempt: prefer the server's own
        hint, else exponential backoff. Capped so a stale header can't stall us."""
        hinted = _parse_duration(resp.headers.get("retry-after")) or _parse_duration(
            resp.headers.get("x-ratelimit-reset-tokens")
        )
        wait = hinted if hinted is not None else 2.0**attempt
        return min(wait, _MAX_BACKOFF_S)

    def complete(self, system: str, user: str) -> LLMResponse:
        attempt = 0
        while True:
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
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt < self._max_retries:
                    self._sleep(self._retry_wait(resp, attempt))
                    attempt += 1
                    continue
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
