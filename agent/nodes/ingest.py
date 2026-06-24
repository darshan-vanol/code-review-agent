from __future__ import annotations

from agent.diff_parser import is_trivial, parse_diff
from agent.state import ReviewState


def ingest_node(state: ReviewState) -> ReviewState:
    files = parse_diff(state.raw_diff)
    state.files = files
    state.is_trivial = is_trivial(files)
    return state
