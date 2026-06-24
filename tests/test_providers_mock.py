import json

from agent.providers.base import LLMProvider, LLMResponse
from agent.providers.mock import MockProvider


def test_mock_is_an_llm_provider():
    assert isinstance(MockProvider(), LLMProvider)


def test_mock_is_deterministic():
    p = MockProvider()
    a = p.complete("system", "user prompt about app.py")
    b = p.complete("system", "user prompt about app.py")
    assert a.text == b.text
    assert a.input_tokens == b.input_tokens


def test_mock_returns_token_and_latency_metadata():
    r = MockProvider().complete("sys", "hello")
    assert isinstance(r, LLMResponse)
    assert r.input_tokens > 0
    assert r.output_tokens > 0
    assert r.latency_ms >= 0


def test_mock_scripted_response_returns_valid_json():
    findings = [{
        "file": "app.py", "line_start": 5, "line_end": 5, "severity": "high",
        "category": "security", "message": "m", "suggestion": "s",
    }]
    p = MockProvider(scripted={"security": findings})
    r = p.complete("sys", "please do the security review")
    assert json.loads(r.text) == {"findings": findings}
