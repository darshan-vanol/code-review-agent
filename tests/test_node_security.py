from agent.nodes.security_scan import security_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState, Severity

_FINDING = [{
    "file": "app.py", "line_start": 6, "line_end": 6, "severity": "high",
    "category": "security", "message": "SQL injection", "suggestion": "parameterize",
}]


def test_security_node_populates_security_findings():
    state = ReviewState(raw_diff="please run security review of app.py")
    state._provider = MockProvider(scripted={"security": _FINDING})
    out = security_node(state)
    assert len(out.security_findings) == 1
    assert out.security_findings[0].severity == Severity.HIGH
    assert out.token_usage["input_tokens"] > 0


def test_security_node_empty_when_no_findings():
    state = ReviewState(raw_diff="trivial change")
    state._provider = MockProvider(scripted={})
    out = security_node(state)
    assert out.security_findings == []
