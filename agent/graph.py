from __future__ import annotations

from functools import partial

from langgraph.graph import END, StateGraph

from agent.nodes.aggregate import aggregate_node
from agent.nodes.ingest import ingest_node
from agent.nodes.logic_analysis import logic_node
from agent.nodes.security_scan import security_node
from agent.nodes.test_coverage import test_coverage_node
from agent.observability import NoOpTracer, traced_node
from agent.providers.base import LLMProvider
from agent.state import ReviewState


def _route_after_ingest(state: ReviewState) -> str:
    # Trivial diffs (whitespace/docs only) skip straight to aggregation.
    return "aggregate" if state.is_trivial else "security"


def build_graph(provider: LLMProvider, tracer=None):
    """Build and compile the review StateGraph.

    The provider is bound into each LLM node with functools.partial (LangGraph
    reconstructs the state between nodes, so it cannot travel on the state).
    Each node is wrapped with traced_node so the tracer gets one span per node.
    """
    tracer = tracer or NoOpTracer()
    g = StateGraph(ReviewState)
    g.add_node("ingest", traced_node(tracer, "ingest", ingest_node))
    g.add_node("security", traced_node(tracer, "security", partial(security_node, provider=provider)))
    g.add_node("logic", traced_node(tracer, "logic", partial(logic_node, provider=provider)))
    g.add_node("test_coverage", traced_node(tracer, "test_coverage", partial(test_coverage_node, provider=provider)))
    g.add_node("aggregate", traced_node(tracer, "aggregate", aggregate_node))

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


def run_review(diff: str, provider: LLMProvider, tracer=None) -> ReviewState:
    """Run the full review graph over a unified diff and return the final state.

    An optional tracer receives one span per node and a final score."""
    tracer = tracer or NoOpTracer()
    compiled = build_graph(provider, tracer)
    result = compiled.invoke(ReviewState(raw_diff=diff))
    final = ReviewState(
        **{k: v for k, v in dict(result).items() if k in ReviewState.model_fields}
    )
    tracer.finish(score=final.score.overall if final.score else None)
    return final
