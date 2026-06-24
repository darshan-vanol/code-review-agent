from agent.nodes._llm_node import run_llm_findings
from agent.providers.base import LLMResponse
from agent.state import Severity


class _ScriptedProvider:
    """Returns a queued list of raw strings, one per call, to test retry."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        text = self._outputs.pop(0)
        return LLMResponse(text=text, input_tokens=1, output_tokens=1,
                           latency_ms=1.0, model="scripted")


_VALID = ('{"findings": [{"file": "a.py", "line_start": 1, "line_end": 1, '
          '"severity": "high", "category": "security", "message": "m", '
          '"suggestion": "s"}]}')


def test_parses_valid_findings():
    p = _ScriptedProvider([_VALID])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert p.calls == 1
    assert meta["input_tokens"] == 1


def test_retries_once_on_malformed_then_succeeds():
    p = _ScriptedProvider(["not json", _VALID])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert len(findings) == 1
    assert p.calls == 2


def test_returns_empty_and_records_error_after_two_failures():
    p = _ScriptedProvider(["bad", "still bad"])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert findings == []
    assert p.calls == 2
    assert meta["error"] is not None
