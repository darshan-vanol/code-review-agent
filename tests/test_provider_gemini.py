import httpx

from agent.providers.base import LLMResponse
from agent.providers.gemini import GeminiProvider


def _mock_client(captured: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": '{"findings": []}'}]}}
                ],
                "usageMetadata": {"promptTokenCount": 20, "candidatesTokenCount": 7},
            },
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_gemini_complete_parses_content_and_usage():
    captured: dict = {}
    p = GeminiProvider(api_key="secret", client=_mock_client(captured))
    r = p.complete("system text", "user text")
    assert isinstance(r, LLMResponse)
    assert r.text == '{"findings": []}'
    assert r.input_tokens == 20
    assert r.output_tokens == 7
    assert "key=secret" in captured["url"]
