from agent.nodes.logic_analysis import logic_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState

_FINDING = [{
    "file": "app.py", "line_start": 3, "line_end": 4, "severity": "medium",
    "category": "logic", "message": "off by one", "suggestion": "use <=",
}]


def test_logic_node_populates_logic_findings():
    state = ReviewState(raw_diff="please run logic analysis of app.py")
    out = logic_node(state, MockProvider(scripted={"logic": _FINDING}))
    assert len(out.logic_findings) == 1
    assert out.logic_findings[0].category == "logic"
