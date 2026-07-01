from __future__ import annotations

import json
import os
from collections.abc import Callable

PRECISION_PENALTY = 0.2

# rescue(golden_finding, unmatched_agent_findings) -> True if the LLM judges that
# one of the candidates describes the golden issue. None disables the fallback.
Rescue = Callable[[dict, list[dict]], bool]


def finding_matches(agent: dict, golden: dict) -> bool:
    """Deterministic match: same file, overlapping line range, same category."""
    if str(agent["file"]).strip() != str(golden["file"]).strip():
        return False
    if agent["category"] != golden["category"]:
        return False
    return (
        agent["line_start"] <= golden["line_end"]
        and golden["line_start"] <= agent["line_end"]
    )


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def score_record(record, *, rescue: Rescue | None = None) -> dict:
    agents = list(record.agent_findings)
    goldens = list(record.golden_findings)
    matched_agent_idx: set[int] = set()
    matched_goldens = 0

    for golden in goldens:
        hit = False
        for i, agent in enumerate(agents):
            if finding_matches(agent, golden):
                matched_agent_idx.add(i)
                hit = True
        if not hit and rescue is not None:
            candidates = [a for i, a in enumerate(agents) if i not in matched_agent_idx]
            if candidates and rescue(golden, candidates):
                hit = True
        if hit:
            matched_goldens += 1

    total_goldens = len(goldens)
    total_agents = len(agents)
    recall = matched_goldens / total_goldens if total_goldens else 0.0
    false_positives = total_agents - len(matched_agent_idx)
    fp_rate = false_positives / total_agents if total_agents else 0.0
    score = _clamp(recall - PRECISION_PENALTY * fp_rate)
    return {
        "id": record.id,
        "score": score,
        "recall": recall,
        "matched": matched_goldens,
        "total_goldens": total_goldens,
        "false_positives": false_positives,
        "total_agent_findings": total_agents,
    }


def score_by_detection(records, *, rescue: Rescue | None = None) -> list[dict]:
    return [score_record(r, rescue=rescue) for r in records]


def _rescue_prompt(golden: dict, candidates: list[dict]) -> str:
    lines = [
        "A golden code-review finding and some candidate findings are given.",
        "Does ANY candidate describe the SAME underlying issue as the golden "
        "(same bug, allowing for different wording or slightly different lines)?",
        'Reply with STRICT JSON only: {"match": true} or {"match": false}.',
        "",
        f"GOLDEN: [{golden['category']}] {golden['file']}:"
        f"{golden['line_start']}-{golden['line_end']} — {golden['message']}",
        "CANDIDATES:",
    ]
    for c in candidates:
        lines.append(
            f"- [{c['category']}] {c['file']}:{c['line_start']}-{c['line_end']} "
            f"— {c['message']}"
        )
    return "\n".join(lines)


def make_groq_rescue(provider) -> Rescue:
    """Build a rescue that asks the provider whether a candidate matches the
    golden. Any error / unparseable reply is treated as no-match (fail-safe)."""
    system = "You are a precise code-review adjudicator."

    def rescue(golden: dict, candidates: list[dict]) -> bool:
        try:
            resp = provider.complete(system, _rescue_prompt(golden, candidates))
            data = json.loads(resp.text)
            return bool(data.get("match") is True)
        except Exception:
            return False

    return rescue


def default_rescue() -> Rescue | None:
    """The runner's default: Groq-backed rescue unless EVAL_LLM_FALLBACK=0."""
    if os.environ.get("EVAL_LLM_FALLBACK", "1") == "0":
        return None
    from agent.providers.factory import make_provider  # noqa: PLC0415

    return make_groq_rescue(make_provider("groq"))
