from __future__ import annotations

from pathlib import Path

_PROMPT_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template by name (without extension). Raises
    FileNotFoundError if the prompt does not exist."""
    path = _PROMPT_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt named {name!r}")
    return path.read_text()
