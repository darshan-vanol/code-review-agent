from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent / "golden"


@dataclass
class GoldenPR:
    id: str
    language: str
    category: str
    diff: str
    summary: str
    findings: list[dict]


def load_golden() -> list[GoldenPR]:
    """Load every <id>.diff that has a sibling <id>.expected.json, sorted by id."""
    goldens: list[GoldenPR] = []
    for diff_path in sorted(GOLDEN_DIR.glob("*.diff")):
        meta_path = diff_path.with_suffix(".expected.json")
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        goldens.append(
            GoldenPR(
                id=meta["id"],
                language=meta["language"],
                category=meta["category"],
                diff=diff_path.read_text(),
                summary=meta["summary"],
                findings=meta["findings"],
            )
        )
    return goldens
