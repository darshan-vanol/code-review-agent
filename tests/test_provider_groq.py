import json

import httpx
import pytest

from agent.providers.base import LLMProvider, LLMResponse
from agent.providers.groq import GroqProvider, _parse_duration


def _ok_json() -> dict:
    return {
        "choices": [{"message": {"content": '{"findings": []}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 5},
    }


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_ok_json())

    return httpx.Client(transport=httpx.MockTransport(handler))


def _sequence_client(statuses: list[int], reset_header: str | None = None) -> httpx.Client:
    """Return responses with the given status codes in order; the last status is
    repeated if more calls arrive. 429s carry a rate-limit reset header."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        i = min(calls["n"], len(statuses) - 1)
        calls["n"] += 1
        status = statuses[i]
        if status == 429:
            headers = {"x-ratelimit-reset-tokens": reset_header} if reset_header else {}
            return httpx.Response(429, json={"error": "rate limited"}, headers=headers)
        return httpx.Response(200, json=_ok_json())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client._call_count = calls  # type: ignore[attr-defined]
    return client


def test_groq_is_an_llm_provider():
    assert isinstance(GroqProvider(api_key="k", client=httpx.Client()), LLMProvider)


def test_groq_complete_parses_content_and_usage():
    captured: dict = {}
    p = GroqProvider(api_key="secret", client=_mock_client(captured))
    r = p.complete("system text", "user text")
    assert isinstance(r, LLMResponse)
    assert r.text == '{"findings": []}'
    assert r.input_tokens == 12
    assert r.output_tokens == 5
    assert r.latency_ms >= 0
    assert captured["auth"] == "Bearer secret"
    assert captured["body"]["messages"][0]["role"] == "system"
    assert captured["body"]["messages"][1]["content"] == "user text"


def test_groq_retries_on_429_then_succeeds():
    slept: list[float] = []
    client = _sequence_client([429, 429, 200], reset_header="0.5s")
    p = GroqProvider(api_key="k", client=client, max_retries=5, sleep=slept.append)
    r = p.complete("s", "u")
    assert r.text == '{"findings": []}'
    assert client._call_count["n"] == 3  # two 429s, then success
    assert slept == [0.5, 0.5]  # honored the reset header on each retry


def test_groq_raises_after_exhausting_retries():
    client = _sequence_client([429], reset_header="0.1s")
    p = GroqProvider(api_key="k", client=client, max_retries=2, sleep=lambda *_: None)
    with pytest.raises(httpx.HTTPStatusError):
        p.complete("s", "u")
    assert client._call_count["n"] == 3  # initial attempt + 2 retries


def test_groq_model_from_env(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "llama-3.1-8b-instant")
    captured: dict = {}
    p = GroqProvider(api_key="k", client=_mock_client(captured))
    p.complete("s", "u")
    assert captured["body"]["model"] == "llama-3.1-8b-instant"


def test_parse_duration_handles_groq_formats():
    assert _parse_duration("19.064s") == pytest.approx(19.064)
    assert _parse_duration("2m59.56s") == pytest.approx(179.56)
    assert _parse_duration("1h29m16.8s") == pytest.approx(5356.8)
    assert _parse_duration("") is None
    assert _parse_duration("garbage") is None
