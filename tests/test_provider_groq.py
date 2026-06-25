import json

import httpx

from agent.providers.base import LLMProvider, LLMResponse
from agent.providers.groq import GroqProvider


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"findings": []}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


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
