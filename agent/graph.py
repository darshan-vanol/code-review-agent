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
    # LLM nodes are traced as "generation" observations (model + token usage);
    # the deterministic ingest/aggregate nodes are plain "span" observations.
    g.add_node("ingest", traced_node(tracer, "ingest", ingest_node, kind="span"))
    g.add_node("security", traced_node(tracer, "security", partial(security_node, provider=provider), kind="generation"))
    g.add_node("logic", traced_node(tracer, "logic", partial(logic_node, provider=provider), kind="generation"))
    g.add_node("test_coverage", traced_node(tracer, "test_coverage", partial(test_coverage_node, provider=provider), kind="generation"))
    g.add_node("aggregate", traced_node(tracer, "aggregate", aggregate_node, kind="span"))

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


def _final_state(state_dict: dict) -> ReviewState:
    return ReviewState(
        **{k: v for k, v in state_dict.items() if k in ReviewState.model_fields}
    )


def _trace_output(final: ReviewState) -> dict:
    """Compact, readable trace output: the score and finding counts rather than
    the full finding bodies, so the trace stays scannable in the Langfuse UI."""
    return {
        "score": final.score.overall if final.score else None,
        "counts": final.score.counts if final.score else {},
        "findings": {
            "security": len(final.security_findings),
            "logic": len(final.logic_findings),
            "test": len(final.test_suggestions),
        },
        "errors": final.errors,
    }


def run_review(diff: str, provider: LLMProvider, tracer=None) -> ReviewState:
    """Run the full review graph over a unified diff and return the final state.

    An optional tracer receives one span per node and a final score."""
    tracer = tracer or NoOpTracer()
    compiled = build_graph(provider, tracer)
    tracer.begin_run(input=diff)
    result = compiled.invoke(ReviewState(raw_diff=diff))
    final = _final_state(dict(result))
    tracer.finish(
        score=final.score.overall if final.score else None,
        output=_trace_output(final),
    )
    return final


def stream_review(diff: str, provider: LLMProvider, tracer=None):
    """Run the review graph and yield progress as each node finishes.

    Yields ("progress", node_name) after every graph node completes, then a final
    ("result", ReviewState). Because each node returns the whole state, the last
    streamed update is the complete final state."""
    tracer = tracer or NoOpTracer()
    compiled = build_graph(provider, tracer)
    tracer.begin_run(input=diff)
    final_dict: dict = {}
    for chunk in compiled.stream(ReviewState(raw_diff=diff), stream_mode="updates"):
        for node_name, state_dict in chunk.items():
            if state_dict:
                final_dict = state_dict
            yield ("progress", node_name)
    final = _final_state(final_dict)
    tracer.finish(
        score=final.score.overall if final.score else None,
        output=_trace_output(final),
    )
    yield ("result", final)
