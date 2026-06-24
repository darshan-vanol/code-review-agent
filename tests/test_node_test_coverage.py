from agent.nodes.test_coverage import test_coverage_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState

_FINDING = [{
    "file": "app.py", "line_start": 1, "line_end": 8, "severity": "low",
    "category": "test", "message": "no tests for get_user", "suggestion": "add unit test",
}]


def test_coverage_node_populates_test_suggestions():
    state = ReviewState(raw_diff="please suggest test coverage for app.py")
    out = test_coverage_node(state, MockProvider(scripted={"test": _FINDING}))
    assert len(out.test_suggestions) == 1
    assert out.test_suggestions[0].category == "test"
