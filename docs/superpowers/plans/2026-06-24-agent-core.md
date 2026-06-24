# Agent Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable, fully unit-tested LangGraph code-review agent — LLM provider adapters (with a deterministic mock), a typed review state, five graph nodes, and the wired graph — with no web framework and no API keys required.

**Architecture:** A pure-Python `agent/` package. An `LLMProvider` protocol abstracts the model so a deterministic `MockProvider` drives all tests offline. A LangGraph `StateGraph` carries a Pydantic `ReviewState` through five nodes (ingest → security_scan → logic_analysis → test_coverage → aggregate), with a conditional edge that skips deep analysis on trivial diffs. Each LLM node validates output against a Pydantic schema and retries once on malformed JSON.

**Tech Stack:** Python 3.11+, LangGraph, LangChain core, Pydantic v2, pytest, ruff. Package + dependency management via `uv`.

---

## File Structure

```
agent/
├── __init__.py
├── state.py              # ReviewState, FileDiff, Finding, ReviewScore (Pydantic)
├── diff_parser.py        # unified-diff string -> list[FileDiff]
├── providers/
│   ├── __init__.py
│   ├── base.py           # LLMProvider protocol + LLMResponse
│   └── mock.py           # deterministic MockProvider
├── prompts/
│   ├── __init__.py       # load_prompt(name) helper
│   ├── security_scan.txt
│   ├── logic_analysis.txt
│   └── test_coverage.txt
├── nodes/
│   ├── __init__.py
│   ├── ingest.py
│   ├── _llm_node.py       # shared LLM-call + validate + retry helper
│   ├── security_scan.py
│   ├── logic_analysis.py
│   ├── test_coverage.py
│   └── aggregate.py
└── graph.py               # build_graph() -> compiled StateGraph

tests/
├── __init__.py
├── conftest.py            # fixtures: sample diffs, mock provider
├── fixtures/
│   ├── simple_python.diff
│   └── trivial_whitespace.diff
├── test_diff_parser.py
├── test_state.py
├── test_providers_mock.py
├── test_node_ingest.py
├── test_node_llm_helper.py
├── test_node_security.py
├── test_node_logic.py
├── test_node_test_coverage.py
├── test_node_aggregate.py
└── test_graph.py

pyproject.toml
.gitignore
```

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `agent/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "code-review-agent"
version = "0.1.0"
description = "Observable LangGraph code-review agent"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain-core>=0.3.0",
    "pydantic>=2.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.5",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["agent"]
```

- [ ] **Step 2: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
*.egg-info/
.env
dist/
```

- [ ] **Step 3: Create empty package markers**

`agent/__init__.py`:
```python
"""Observable LangGraph code-review agent."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 4: Create the environment and install**

Run: `uv venv && uv pip install -e ".[dev]"`
Expected: completes without error; `.venv/` created.

- [ ] **Step 5: Verify pytest runs (no tests yet)**

Run: `uv run pytest`
Expected: "no tests ran" (exit code 5 is fine at this stage).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore agent/__init__.py tests/__init__.py
git commit -m "chore: scaffold agent package"
```

---

## Task 2: State and domain models

**Files:**
- Create: `agent/state.py`
- Test: `tests/test_state.py`

- [ ] **Step 1: Write the failing test**

`tests/test_state.py`:
```python
from agent.state import Finding, FileDiff, ReviewScore, ReviewState, Severity


def test_finding_defaults_and_fields():
    f = Finding(
        file="app.py",
        line_start=10,
        line_end=12,
        severity=Severity.HIGH,
        category="security",
        message="SQL injection risk",
        suggestion="Use parameterized queries",
    )
    assert f.severity == Severity.HIGH
    assert f.line_end == 12


def test_review_score_rollup_counts():
    findings = [
        Finding(file="a", line_start=1, line_end=1, severity=Severity.HIGH,
                category="security", message="m", suggestion="s"),
        Finding(file="a", line_start=2, line_end=2, severity=Severity.LOW,
                category="logic", message="m", suggestion="s"),
    ]
    score = ReviewScore.from_findings(findings)
    assert score.counts["high"] == 1
    assert score.counts["low"] == 1
    assert 0.0 <= score.overall <= 1.0


def test_review_state_starts_empty():
    state = ReviewState(raw_diff="diff")
    assert state.files == []
    assert state.security_findings == []
    assert state.is_trivial is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.state'`.

- [ ] **Step 3: Write minimal implementation**

`agent/state.py`:
```python
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Weight used to turn severity counts into a single 0..1 score.
_SEVERITY_WEIGHT = {
    Severity.INFO: 0.0,
    Severity.LOW: 0.1,
    Severity.MEDIUM: 0.3,
    Severity.HIGH: 0.6,
    Severity.CRITICAL: 1.0,
}


class FileDiff(BaseModel):
    path: str
    hunks: list[str] = Field(default_factory=list)
    added_lines: int = 0
    removed_lines: int = 0


class Finding(BaseModel):
    file: str
    line_start: int
    line_end: int
    severity: Severity
    category: str
    message: str
    suggestion: str


class ReviewScore(BaseModel):
    overall: float
    counts: dict[str, int]

    @classmethod
    def from_findings(cls, findings: list[Finding]) -> "ReviewScore":
        counts = {s.value: 0 for s in Severity}
        penalty = 0.0
        for f in findings:
            counts[f.severity.value] += 1
            penalty += _SEVERITY_WEIGHT[f.severity]
        # Clamp penalty so overall stays in [0, 1]; 1.0 == clean.
        overall = max(0.0, 1.0 - min(penalty, 1.0))
        return cls(overall=round(overall, 3), counts=counts)


class ReviewState(BaseModel):
    raw_diff: str
    files: list[FileDiff] = Field(default_factory=list)
    is_trivial: bool = False
    security_findings: list[Finding] = Field(default_factory=list)
    logic_findings: list[Finding] = Field(default_factory=list)
    test_suggestions: list[Finding] = Field(default_factory=list)
    score: ReviewScore | None = None
    errors: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_state.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/state.py tests/test_state.py
git commit -m "feat: add review state and domain models"
```

---

## Task 3: Diff parser

**Files:**
- Create: `agent/diff_parser.py`
- Create: `tests/fixtures/simple_python.diff`
- Create: `tests/fixtures/trivial_whitespace.diff`
- Test: `tests/test_diff_parser.py`

- [ ] **Step 1: Create fixtures**

`tests/fixtures/simple_python.diff`:
```diff
diff --git a/app.py b/app.py
index 1111111..2222222 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,5 @@
 import os
+import sqlite3
+
 def get_user(uid):
-    return None
+    conn = sqlite3.connect("db")
+    return conn.execute("SELECT * FROM users WHERE id = " + uid)
```

`tests/fixtures/trivial_whitespace.diff`:
```diff
diff --git a/notes.md b/notes.md
index 3333333..4444444 100644
--- a/notes.md
+++ b/notes.md
@@ -1,2 +1,2 @@
-hello
+hello 
 world
```

- [ ] **Step 2: Write the failing test**

`tests/test_diff_parser.py`:
```python
from pathlib import Path

from agent.diff_parser import is_trivial, parse_diff

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_parse_diff_extracts_file_and_counts():
    files = parse_diff(_read("simple_python.diff"))
    assert len(files) == 1
    assert files[0].path == "app.py"
    assert files[0].added_lines == 4
    assert files[0].removed_lines == 1
    assert any("sqlite3" in h for h in files[0].hunks)


def test_parse_empty_diff_returns_empty_list():
    assert parse_diff("") == []


def test_is_trivial_true_for_whitespace_and_docs():
    files = parse_diff(_read("trivial_whitespace.diff"))
    assert is_trivial(files) is True


def test_is_trivial_false_for_code_changes():
    files = parse_diff(_read("simple_python.diff"))
    assert is_trivial(files) is False
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_diff_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.diff_parser'`.

- [ ] **Step 4: Write minimal implementation**

`agent/diff_parser.py`:
```python
from __future__ import annotations

import re

from agent.state import FileDiff

# File extensions we treat as non-code (docs / config prose).
_DOC_EXTENSIONS = {".md", ".rst", ".txt"}
_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$")
_HUNK_HEADER = re.compile(r"^@@ ")


def parse_diff(raw: str) -> list[FileDiff]:
    if not raw.strip():
        return []

    files: list[FileDiff] = []
    current: FileDiff | None = None

    for line in raw.splitlines():
        header = _FILE_HEADER.match(line)
        if header:
            current = FileDiff(path=header.group(1), hunks=[])
            files.append(current)
            continue
        if current is None:
            continue
        if _HUNK_HEADER.match(line):
            current.hunks.append(line + "\n")
            continue
        if current.hunks:
            current.hunks[-1] += line + "\n"
        if line.startswith("+") and not line.startswith("+++"):
            current.added_lines += 1
        elif line.startswith("-") and not line.startswith("---"):
            current.removed_lines += 1

    return files


def _is_doc(path: str) -> bool:
    return any(path.endswith(ext) for ext in _DOC_EXTENSIONS)


def _is_whitespace_only_change(hunk_text: str) -> bool:
    for line in hunk_text.splitlines():
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---")):
            if line[1:].strip() != "":
                # A change with real content on a non-doc line -> not whitespace-only.
                return False
    return True


def is_trivial(files: list[FileDiff]) -> bool:
    if not files:
        return True
    for f in files:
        if _is_doc(f.path):
            continue
        for hunk in f.hunks:
            if not _is_whitespace_only_change(hunk):
                return False
    return True
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_diff_parser.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add agent/diff_parser.py tests/test_diff_parser.py tests/fixtures/
git commit -m "feat: add unified diff parser with trivial-change detection"
```

---

## Task 4: LLM provider protocol + mock

**Files:**
- Create: `agent/providers/__init__.py`
- Create: `agent/providers/base.py`
- Create: `agent/providers/mock.py`
- Test: `tests/test_providers_mock.py`

- [ ] **Step 1: Write the failing test**

`tests/test_providers_mock.py`:
```python
import json

from agent.providers.base import LLMProvider, LLMResponse
from agent.providers.mock import MockProvider


def test_mock_is_an_llm_provider():
    assert isinstance(MockProvider(), LLMProvider)


def test_mock_is_deterministic():
    p = MockProvider()
    a = p.complete("system", "user prompt about app.py")
    b = p.complete("system", "user prompt about app.py")
    assert a.text == b.text
    assert a.input_tokens == b.input_tokens


def test_mock_returns_token_and_latency_metadata():
    r = MockProvider().complete("sys", "hello")
    assert isinstance(r, LLMResponse)
    assert r.input_tokens > 0
    assert r.output_tokens > 0
    assert r.latency_ms >= 0


def test_mock_scripted_response_returns_valid_json():
    findings = [{
        "file": "app.py", "line_start": 5, "line_end": 5, "severity": "high",
        "category": "security", "message": "m", "suggestion": "s",
    }]
    p = MockProvider(scripted={"security": findings})
    r = p.complete("sys", "please do the security review")
    assert json.loads(r.text) == {"findings": findings}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_providers_mock.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.providers'`.

- [ ] **Step 3: Write the protocol**

`agent/providers/__init__.py`:
```python
```

`agent/providers/base.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    model: str


@runtime_checkable
class LLMProvider(Protocol):
    """Abstracts a chat-completion model. Implementations must be swappable
    behind this interface (mock, Groq, Gemini, OpenAI, Anthropic)."""

    def complete(self, system: str, user: str) -> LLMResponse:
        ...
```

- [ ] **Step 4: Write the mock**

`agent/providers/mock.py`:
```python
from __future__ import annotations

import json

from agent.providers.base import LLMResponse

# Deterministic synthetic latency (ms) so traces look realistic without a clock.
_FAKE_LATENCY_MS = 42.0
_MODEL_NAME = "mock-1"


def _estimate_tokens(text: str) -> int:
    # Rough, deterministic token estimate: ~4 chars per token, min 1.
    return max(1, len(text) // 4)


class MockProvider:
    """Deterministic provider for offline tests and CI.

    `scripted` maps a keyword -> list of finding dicts. When the user prompt
    contains the keyword, the mock returns {"findings": [...]} as JSON. Otherwise
    it returns an empty findings list. This lets node tests assert exact output.
    """

    def __init__(self, scripted: dict[str, list[dict]] | None = None):
        self._scripted = scripted or {}

    def complete(self, system: str, user: str) -> LLMResponse:
        findings: list[dict] = []
        for keyword, value in self._scripted.items():
            if keyword in user.lower():
                findings = value
                break
        text = json.dumps({"findings": findings})
        return LLMResponse(
            text=text,
            input_tokens=_estimate_tokens(system + user),
            output_tokens=_estimate_tokens(text),
            latency_ms=_FAKE_LATENCY_MS,
            model=_MODEL_NAME,
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_providers_mock.py -v`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add agent/providers/ tests/test_providers_mock.py
git commit -m "feat: add LLM provider protocol and deterministic mock"
```

---

## Task 5: Prompts + prompt loader

**Files:**
- Create: `agent/prompts/__init__.py`
- Create: `agent/prompts/security_scan.txt`
- Create: `agent/prompts/logic_analysis.txt`
- Create: `agent/prompts/test_coverage.txt`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Write the failing test**

`tests/test_prompts.py`:
```python
import pytest

from agent.prompts import load_prompt


def test_load_known_prompt_returns_nonempty_text():
    text = load_prompt("security_scan")
    assert "findings" in text.lower()


def test_load_unknown_prompt_raises():
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.prompts'`.

- [ ] **Step 3: Write the prompt files**

`agent/prompts/security_scan.txt`:
```
You are a senior security engineer reviewing a code diff.
Identify security vulnerabilities ONLY: injection, auth/authz flaws, secrets in
code, unsafe deserialization, SSRF, path traversal, and similar.

Return STRICT JSON, no prose, in exactly this shape:
{"findings": [{"file": str, "line_start": int, "line_end": int,
"severity": "info|low|medium|high|critical", "category": "security",
"message": str, "suggestion": str}]}

If there are no issues, return {"findings": []}.

DIFF:
{diff}
```

`agent/prompts/logic_analysis.txt`:
```
You are a senior software engineer reviewing a code diff for correctness.
Identify logic bugs ONLY: wrong conditions, off-by-one, unhandled errors,
edge cases, race conditions, and incorrect control flow.

Return STRICT JSON, no prose, in exactly this shape:
{"findings": [{"file": str, "line_start": int, "line_end": int,
"severity": "info|low|medium|high|critical", "category": "logic",
"message": str, "suggestion": str}]}

If there are no issues, return {"findings": []}.

DIFF:
{diff}
```

`agent/prompts/test_coverage.txt`:
```
You are a senior engineer reviewing a code diff for test coverage gaps.
Identify missing tests for the changed code ONLY.

Return STRICT JSON, no prose, in exactly this shape:
{"findings": [{"file": str, "line_start": int, "line_end": int,
"severity": "info|low|medium|high|critical", "category": "test",
"message": str, "suggestion": str}]}

If there are no gaps, return {"findings": []}.

DIFF:
{diff}
```

- [ ] **Step 4: Write the loader**

`agent/prompts/__init__.py`:
```python
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
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add agent/prompts/ tests/test_prompts.py
git commit -m "feat: add review prompts and loader"
```

---

## Task 6: Ingest node

**Files:**
- Create: `agent/nodes/__init__.py`
- Create: `agent/nodes/ingest.py`
- Test: `tests/test_node_ingest.py`

- [ ] **Step 1: Write the failing test**

`tests/test_node_ingest.py`:
```python
from pathlib import Path

from agent.nodes.ingest import ingest_node
from agent.state import ReviewState

FIXTURES = Path(__file__).parent / "fixtures"


def test_ingest_populates_files_and_trivial_flag():
    state = ReviewState(raw_diff=(FIXTURES / "simple_python.diff").read_text())
    out = ingest_node(state)
    assert len(out.files) == 1
    assert out.files[0].path == "app.py"
    assert out.is_trivial is False


def test_ingest_marks_whitespace_diff_trivial():
    state = ReviewState(raw_diff=(FIXTURES / "trivial_whitespace.diff").read_text())
    out = ingest_node(state)
    assert out.is_trivial is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_node_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.nodes'`.

- [ ] **Step 3: Write the node**

`agent/nodes/__init__.py`:
```python
```

`agent/nodes/ingest.py`:
```python
from __future__ import annotations

from agent.diff_parser import is_trivial, parse_diff
from agent.state import ReviewState


def ingest_node(state: ReviewState) -> ReviewState:
    files = parse_diff(state.raw_diff)
    state.files = files
    state.is_trivial = is_trivial(files)
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_node_ingest.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/__init__.py agent/nodes/ingest.py tests/test_node_ingest.py
git commit -m "feat: add ingest node"
```

---

## Task 7: Shared LLM-node helper (parse + validate + retry)

**Files:**
- Create: `agent/nodes/_llm_node.py`
- Test: `tests/test_node_llm_helper.py`

- [ ] **Step 1: Write the failing test**

`tests/test_node_llm_helper.py`:
```python
from agent.nodes._llm_node import run_llm_findings
from agent.providers.base import LLMResponse
from agent.state import Severity


class _ScriptedProvider:
    """Returns a queued list of raw strings, one per call, to test retry."""

    def __init__(self, outputs):
        self._outputs = list(outputs)
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        text = self._outputs.pop(0)
        return LLMResponse(text=text, input_tokens=1, output_tokens=1,
                           latency_ms=1.0, model="scripted")


_VALID = ('{"findings": [{"file": "a.py", "line_start": 1, "line_end": 1, '
          '"severity": "high", "category": "security", "message": "m", '
          '"suggestion": "s"}]}')


def test_parses_valid_findings():
    p = _ScriptedProvider([_VALID])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert p.calls == 1
    assert meta["input_tokens"] == 1


def test_retries_once_on_malformed_then_succeeds():
    p = _ScriptedProvider(["not json", _VALID])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert len(findings) == 1
    assert p.calls == 2


def test_returns_empty_and_records_error_after_two_failures():
    p = _ScriptedProvider(["bad", "still bad"])
    findings, meta = run_llm_findings(p, "sys", "user", category="security")
    assert findings == []
    assert p.calls == 2
    assert meta["error"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_node_llm_helper.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.nodes._llm_node'`.

- [ ] **Step 3: Write the helper**

`agent/nodes/_llm_node.py`:
```python
from __future__ import annotations

import json

from pydantic import ValidationError

from agent.providers.base import LLMProvider
from agent.state import Finding

# One retry: an LLM occasionally returns prose or trailing commas. We re-ask once
# before degrading to an empty list so a single node never crashes the review.
_MAX_ATTEMPTS = 2


def _parse_findings(text: str, category: str) -> list[Finding]:
    data = json.loads(text)
    raw = data["findings"]
    findings = [Finding(**item) for item in raw]
    # Trust the node's category over whatever the model labelled.
    for f in findings:
        f.category = category
    return findings


def run_llm_findings(
    provider: LLMProvider, system: str, user: str, *, category: str
) -> tuple[list[Finding], dict]:
    """Call the provider, parse + validate findings, retry once on failure.

    Returns (findings, meta) where meta carries token/latency totals and an
    optional 'error' string when both attempts failed."""
    meta = {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0, "error": None}
    last_error = None

    for _ in range(_MAX_ATTEMPTS):
        resp = provider.complete(system, user)
        meta["input_tokens"] += resp.input_tokens
        meta["output_tokens"] += resp.output_tokens
        meta["latency_ms"] += resp.latency_ms
        try:
            return _parse_findings(resp.text, category), meta
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            last_error = e

    meta["error"] = f"failed to parse findings: {last_error}"
    return [], meta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_node_llm_helper.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/_llm_node.py tests/test_node_llm_helper.py
git commit -m "feat: add shared LLM-node helper with validation and retry"
```

---

## Task 8: Security, logic, and test-coverage nodes

**Files:**
- Create: `agent/nodes/security_scan.py`
- Create: `agent/nodes/logic_analysis.py`
- Create: `agent/nodes/test_coverage.py`
- Test: `tests/test_node_security.py`
- Test: `tests/test_node_logic.py`
- Test: `tests/test_node_test_coverage.py`

These three nodes are structurally identical: they read `state.raw_diff`, call
`run_llm_findings` with their prompt, and write findings + accumulate token meta.
They differ only in prompt name, category, and the state field they populate.
The provider is read from `state` via a private attribute set by the graph
builder (see Task 9); for unit tests we set it directly.

- [ ] **Step 1: Write the failing tests**

`tests/test_node_security.py`:
```python
from agent.nodes.security_scan import security_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState, Severity

_FINDING = [{
    "file": "app.py", "line_start": 6, "line_end": 6, "severity": "high",
    "category": "security", "message": "SQL injection", "suggestion": "parameterize",
}]


def test_security_node_populates_security_findings():
    state = ReviewState(raw_diff="please run security review of app.py")
    state._provider = MockProvider(scripted={"security": _FINDING})
    out = security_node(state)
    assert len(out.security_findings) == 1
    assert out.security_findings[0].severity == Severity.HIGH
    assert out.token_usage["input_tokens"] > 0


def test_security_node_empty_when_no_findings():
    state = ReviewState(raw_diff="trivial change")
    state._provider = MockProvider(scripted={})
    out = security_node(state)
    assert out.security_findings == []
```

`tests/test_node_logic.py`:
```python
from agent.nodes.logic_analysis import logic_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState

_FINDING = [{
    "file": "app.py", "line_start": 3, "line_end": 4, "severity": "medium",
    "category": "logic", "message": "off by one", "suggestion": "use <=",
}]


def test_logic_node_populates_logic_findings():
    state = ReviewState(raw_diff="please run logic analysis of app.py")
    state._provider = MockProvider(scripted={"logic": _FINDING})
    out = logic_node(state)
    assert len(out.logic_findings) == 1
    assert out.logic_findings[0].category == "logic"
```

`tests/test_node_test_coverage.py`:
```python
from agent.nodes.test_coverage import test_coverage_node
from agent.providers.mock import MockProvider
from agent.state import ReviewState

_FINDING = [{
    "file": "app.py", "line_start": 1, "line_end": 8, "severity": "low",
    "category": "test", "message": "no tests for get_user", "suggestion": "add unit test",
}]


def test_coverage_node_populates_test_suggestions():
    state = ReviewState(raw_diff="please suggest test coverage for app.py")
    state._provider = MockProvider(scripted={"test": _FINDING})
    out = test_coverage_node(state)
    assert len(out.test_suggestions) == 1
    assert out.test_suggestions[0].category == "test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_node_security.py tests/test_node_logic.py tests/test_node_test_coverage.py -v`
Expected: FAIL — modules not found, and `ReviewState` has no `token_usage` / `_provider`.

- [ ] **Step 3: Extend `ReviewState` to carry a provider and token usage**

In `agent/state.py`, add inside `class ReviewState` (after `errors`):
```python
    token_usage: dict[str, float] = Field(
        default_factory=lambda: {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0.0}
    )

    model_config = {"arbitrary_types_allowed": True}

    # Provider is injected by the graph builder; excluded from serialization.
    _provider: object = None
```

> Note: `_provider` is a private attribute (leading underscore). In Pydantic v2,
> declare it with `PrivateAttr` for clean support. Replace the `_provider` line
> above with the following and add the import:

At the top of `agent/state.py`, change the pydantic import line to:
```python
from pydantic import BaseModel, Field, PrivateAttr
```
And replace the `_provider: object = None` line with:
```python
    _provider: object | None = PrivateAttr(default=None)
```

- [ ] **Step 4: Write the three nodes**

`agent/nodes/security_scan.py`:
```python
from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.prompts import load_prompt
from agent.state import ReviewState

_SYSTEM = load_prompt("security_scan")


def security_node(state: ReviewState) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        state._provider, _SYSTEM, user, category="security"
    )
    state.security_findings = findings
    _accumulate(state, meta)
    return state


def _accumulate(state: ReviewState, meta: dict) -> None:
    state.token_usage["input_tokens"] += meta["input_tokens"]
    state.token_usage["output_tokens"] += meta["output_tokens"]
    state.token_usage["latency_ms"] += meta["latency_ms"]
    if meta["error"]:
        state.errors.append(meta["error"])
```

`agent/nodes/logic_analysis.py`:
```python
from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.nodes.security_scan import _accumulate
from agent.prompts import load_prompt
from agent.state import ReviewState

_SYSTEM = load_prompt("logic_analysis")


def logic_node(state: ReviewState) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        state._provider, _SYSTEM, user, category="logic"
    )
    state.logic_findings = findings
    _accumulate(state, meta)
    return state
```

`agent/nodes/test_coverage.py`:
```python
from __future__ import annotations

from agent.nodes._llm_node import run_llm_findings
from agent.nodes.security_scan import _accumulate
from agent.prompts import load_prompt
from agent.state import ReviewState

_SYSTEM = load_prompt("test_coverage")


def test_coverage_node(state: ReviewState) -> ReviewState:
    user = _SYSTEM.replace("{diff}", state.raw_diff)
    findings, meta = run_llm_findings(
        state._provider, _SYSTEM, user, category="test"
    )
    state.test_suggestions = findings
    _accumulate(state, meta)
    return state
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_node_security.py tests/test_node_logic.py tests/test_node_test_coverage.py -v`
Expected: PASS (4 passed total).

- [ ] **Step 6: Commit**

```bash
git add agent/state.py agent/nodes/security_scan.py agent/nodes/logic_analysis.py agent/nodes/test_coverage.py tests/test_node_security.py tests/test_node_logic.py tests/test_node_test_coverage.py
git commit -m "feat: add security, logic, and test-coverage nodes"
```

---

## Task 9: Aggregate node

**Files:**
- Create: `agent/nodes/aggregate.py`
- Test: `tests/test_node_aggregate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_node_aggregate.py`:
```python
from agent.nodes.aggregate import aggregate_node
from agent.state import Finding, ReviewState, Severity


def _finding(sev):
    return Finding(file="a", line_start=1, line_end=1, severity=sev,
                   category="x", message="m", suggestion="s")


def test_aggregate_computes_score_from_all_findings():
    state = ReviewState(raw_diff="d")
    state.security_findings = [_finding(Severity.HIGH)]
    state.logic_findings = [_finding(Severity.LOW)]
    state.test_suggestions = []
    out = aggregate_node(state)
    assert out.score is not None
    assert out.score.counts["high"] == 1
    assert out.score.counts["low"] == 1
    assert out.score.overall < 1.0


def test_aggregate_clean_diff_scores_one():
    state = ReviewState(raw_diff="d")
    out = aggregate_node(state)
    assert out.score.overall == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_node_aggregate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.nodes.aggregate'`.

- [ ] **Step 3: Write the node**

`agent/nodes/aggregate.py`:
```python
from __future__ import annotations

from agent.state import ReviewScore, ReviewState


def aggregate_node(state: ReviewState) -> ReviewState:
    all_findings = (
        state.security_findings + state.logic_findings + state.test_suggestions
    )
    state.score = ReviewScore.from_findings(all_findings)
    return state
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_node_aggregate.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/nodes/aggregate.py tests/test_node_aggregate.py
git commit -m "feat: add aggregate node"
```

---

## Task 10: Build and wire the graph

**Files:**
- Create: `agent/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

`tests/test_graph.py`:
```python
from pathlib import Path

from agent.graph import run_review
from agent.providers.mock import MockProvider

FIXTURES = Path(__file__).parent / "fixtures"

_SECURITY = [{
    "file": "app.py", "line_start": 6, "line_end": 6, "severity": "high",
    "category": "security", "message": "SQL injection", "suggestion": "parameterize",
}]


def test_run_review_full_path_produces_findings_and_score():
    diff = (FIXTURES / "simple_python.diff").read_text()
    provider = MockProvider(scripted={"security": _SECURITY})
    result = run_review(diff, provider)
    assert result.score is not None
    assert len(result.security_findings) == 1
    assert result.is_trivial is False
    assert result.token_usage["input_tokens"] > 0


def test_run_review_skips_analysis_on_trivial_diff():
    diff = (FIXTURES / "trivial_whitespace.diff").read_text()
    # Even though security is scripted, trivial diffs skip the analysis nodes.
    provider = MockProvider(scripted={"security": _SECURITY})
    result = run_review(diff, provider)
    assert result.is_trivial is True
    assert result.security_findings == []
    assert result.score.overall == 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent.graph'`.

- [ ] **Step 3: Write the graph**

`agent/graph.py`:
```python
from __future__ import annotations

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


def build_graph():
    """Build and compile the review StateGraph."""
    g = StateGraph(ReviewState)
    g.add_node("ingest", ingest_node)
    g.add_node("security", security_node)
    g.add_node("logic", logic_node)
    g.add_node("test_coverage", test_coverage_node)
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
    state = ReviewState(raw_diff=diff)
    state._provider = provider
    compiled = build_graph()
    result = compiled.invoke(state)
    # LangGraph returns the state as a dict-like; rebuild a ReviewState for callers.
    final = ReviewState(**{k: v for k, v in dict(result).items() if k in ReviewState.model_fields})
    final._provider = provider
    return final
```

> Note on state injection: LangGraph passes state between nodes and may copy it.
> Because `_provider` is a `PrivateAttr`, it is preserved on the same object
> within a single `invoke` for the synchronous, in-process executor used here. If
> a future LangGraph version copies state across nodes and drops private attrs,
> move the provider into a `configurable` field via `compiled.invoke(state, config=...)`.
> Verify with the test below; if `test_run_review_full_path...` fails because the
> provider is `None` inside a node, switch to passing the provider through
> LangGraph's `config={"configurable": {"provider": provider}}` and read it in
> each node from the injected config argument.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py -v`
Expected: PASS (2 passed).

> If it fails with the provider being `None` inside nodes, apply the config-based
> injection described in the note above: change each node signature to
> `def security_node(state, config)` and read
> `provider = config["configurable"]["provider"]`, then call
> `compiled.invoke(state, config={"configurable": {"provider": provider}})`.

- [ ] **Step 5: Commit**

```bash
git add agent/graph.py tests/test_graph.py
git commit -m "feat: wire LangGraph review graph with trivial-diff routing"
```

---

## Task 11: Full suite + lint green

**Files:** none (verification task)

- [ ] **Step 1: Run the entire test suite**

Run: `uv run pytest -v`
Expected: PASS — all tests across every module green.

- [ ] **Step 2: Run the linter**

Run: `uv run ruff check .`
Expected: "All checks passed!" (fix any reported issues, then re-run).

- [ ] **Step 3: Smoke-test the agent from a REPL one-liner**

Run:
```bash
uv run python -c "from agent.graph import run_review; from agent.providers.mock import MockProvider; r = run_review(open('tests/fixtures/simple_python.diff').read(), MockProvider()); print(r.score.model_dump())"
```
Expected: prints a `ReviewScore` dict, e.g. `{'overall': 1.0, 'counts': {...}}`.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A
git commit -m "chore: lint clean for agent core" || echo "nothing to commit"
```

---

## Done criteria

- `uv run pytest` is fully green.
- `uv run ruff check .` passes.
- `run_review(diff, provider)` returns a populated `ReviewState` with findings,
  a `ReviewScore`, and accumulated `token_usage` — entirely offline via `MockProvider`.
- Trivial diffs skip the analysis nodes and score 1.0.

This leaves a runnable, tested agent core. **Plan 2 (API + GitHub + Langfuse)**
wraps this in FastAPI, adds the real provider adapters, the GitHub PR-URL fetch,
and Langfuse tracing.
