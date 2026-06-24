from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from agent.nodes.aggregate import aggregate_node
from agent.nodes.ingest import ingest_node
from agent.nodes.logic_analysis import logic_node
from agent.nodes.security_scan import security_node
from agent.nodes.test_coverage import test_coverage_node
from agent.providers.base import LLMProvider
from agent.state import ReviewState


def _route_after_ingest(state: ReviewState) -> str:
    # Trivial diffs (whitespace/docs only) skip straight to aggregation.
    return "aggregate" if state.is_trivial else "security"


def build_graph(provider: LLMProvider):
    """Build and compile the review StateGraph.

    The provider is bound into each LLM node via functools.partial at build time.
    LangGraph reconstructs the state object between nodes, so the provider cannot
    travel on the state itself — binding it to the node callable keeps it available
    without leaking a non-serializable object into the graph's state channels.
    """
    g = StateGraph(ReviewState)
    g.add_node("ingest", ingest_node)
    g.add_node("security", partial(security_node, provider=provider))
    g.add_node("logic", partial(logic_node, provider=provider))
    g.add_node("test_coverage", partial(test_coverage_node, provider=provider))
    g.add_node("aggregate", aggregate_node)

    g.set_entry_point("ingest")
    g.add_conditional_edges(
        "ingest", _route_after_ingest,
        {"security": "security", "aggregate": "aggregate"},
    )
    g.add_edge("security", "logic")
    g.add_edge("logic", "test_coverage")
    g.add_edge("test_coverage", "aggregate")
    g.add_edge("aggregate", END)
    return g.compile()


def run_review(diff: str, provider: LLMProvider) -> ReviewState:
    """Run the full review graph over a unified diff and return the final state."""
    compiled = build_graph(provider)
    result = compiled.invoke(ReviewState(raw_diff=diff))
    # LangGraph returns the state as a dict-like; rebuild a ReviewState for callers.
    return ReviewState(
        **{k: v for k, v in dict(result).items() if k in ReviewState.model_fields}
    )
