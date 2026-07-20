from __future__ import annotations

from agent.diff_parser import is_trivial, parse_diff
from agent.state import ReviewState


def ingest_node(state: ReviewState) -> ReviewState:
    files = parse_diff(state.raw_diff)
    state.files = files
    if not files:
        # Raw code pasted without `diff --git` headers does not parse into files,
        # but the LLM nodes still review state.raw_diff — do not skip them.
        state.is_trivial = not state.raw_diff.strip()
    else:
        state.is_trivial = is_trivial(files)
    return state
