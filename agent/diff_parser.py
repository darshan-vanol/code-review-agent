from __future__ import annotations

import re

from agent.state import FileDiff

# File extensions we treat as non-code (docs / config prose).
_DOC_EXTENSIONS = {".md", ".rst", ".txt"}
# Start each file at its `diff --git a/<old> b/<new>` header. Keying off this
# (rather than `+++ b/...`) means deletions — whose new path is `+++ /dev/null` —
# are still captured, using the new path, or the old path when the file is deleted.
_DIFF_GIT_HEADER = re.compile(r"^diff --git a/(.+) b/(.+)$")
_HUNK_HEADER = re.compile(r"^@@ ")


def parse_diff(raw: str) -> list[FileDiff]:
    if not raw.strip():
        return []

    files: list[FileDiff] = []
    current: FileDiff | None = None

    for line in raw.splitlines():
        header = _DIFF_GIT_HEADER.match(line)
        if header:
            old_path, new_path = header.group(1), header.group(2)
            path = old_path if new_path == "/dev/null" else new_path
            current = FileDiff(path=path, hunks=[])
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
