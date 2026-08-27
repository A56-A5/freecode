"""
context.rank - score index entries against a user query / goal.
"""
from __future__ import annotations

import re
from pathlib import Path

from freecode.context.index import FileEntry, ProjectIndex

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{1,}")


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def score_entry(entry: FileEntry, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    path_tokens = tokenize(entry.rel_path.replace("/", " ").replace("_", " ").replace("-", " "))
    name_tokens = tokenize(entry.name_lower.replace("_", " ").replace("-", " "))
    path_hits = len(query_tokens & path_tokens)
    name_hits = len(query_tokens & name_tokens)
    # Prefer path/name matches; boost source-ish suffixes slightly via size neutrality
    score = name_hits * 3.0 + path_hits * 1.5
    if entry.rel_path.startswith("src/") or entry.rel_path.startswith("tests/"):
        score += 0.25
    return score


def select_relevant(
    index: ProjectIndex,
    query: str,
    *,
    limit: int = 8,
    min_score: float = 1.0,
) -> list[FileEntry]:
    tokens = tokenize(query)
    scored: list[tuple[float, FileEntry]] = []
    for entry in index.files:
        s = score_entry(entry, tokens)
        if s >= min_score:
            scored.append((s, entry))
    scored.sort(key=lambda x: (-x[0], x[1].rel_path))
    return [e for _, e in scored[:limit]]


def read_snippets(
    index: ProjectIndex,
    entries: list[FileEntry],
    *,
    max_chars_each: int = 1200,
) -> list[tuple[str, str]]:
    """Return (rel_path, snippet) pairs."""
    out: list[tuple[str, str]] = []
    for entry in entries:
        path = index.root / entry.rel_path
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > max_chars_each:
            text = text[: max_chars_each - 20] + "\n…[truncated]…"
        out.append((entry.rel_path, text))
    return out
