from __future__ import annotations

import json
import os
from pathlib import Path


def reports_dir() -> Path:
    return Path(os.environ.get("EVAL_REPORTS_DIR", "evals/reports"))


def _sort_key(path: Path) -> tuple[int, object]:
    # Reports are written as 1.json, 2.json, ...; sort numerically when possible
    # so 10 sorts after 2, falling back to lexical for non-numeric stems.
    return (0, int(path.stem)) if path.stem.isdigit() else (1, path.stem)


def _parse_report(path: Path) -> dict | None:
    """Return the parsed JSON dict, or None if the file is malformed / missing expected keys."""
    try:
        data = json.loads(path.read_text())
        if "passed" not in data or "aggregate" not in data:
            return None
        return data
    except json.JSONDecodeError:
        return None


def list_reports(directory: Path | None = None) -> list[dict]:
    directory = directory or reports_dir()
    if not directory.exists():
        return []
    summaries: list[dict] = []
    for path in sorted(directory.glob("*.json"), key=_sort_key):
        data = _parse_report(path)
        if data is None:
            continue
        summaries.append(
            {"id": path.stem, "passed": data["passed"], "aggregate": data["aggregate"]}
        )
    return summaries


def get_report(report_id: str, directory: Path | None = None) -> dict | None:
    directory = directory or reports_dir()
    path = directory / f"{report_id}.json"
    if not path.exists():
        return None
    return _parse_report(path)
