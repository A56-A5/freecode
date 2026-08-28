"""
context.mentions - expand @file / @dir pins from user messages.
"""
from __future__ import annotations

import re
from pathlib import Path

_MENTION = re.compile(r"(?<![\w/])@([^\s@]+)")


def extract_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(_MENTION.findall(text or "")))


def expand_mentions(root: Path, text: str, *, max_file_chars: int = 8000, max_dir_entries: int = 80) -> str:
    """
    Return a context block for @path mentions, or empty string if none.
    """
    root = root.resolve()
    mentions = extract_mentions(text)
    if not mentions:
        return ""
    parts: list[str] = ["## User-pinned paths (@mentions)"]
    for rel in mentions:
        rel = rel.strip().rstrip(",.;:")
        if not rel:
            continue
        path = (root / rel).resolve() if not Path(rel).is_absolute() else Path(rel).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            parts.append(f"- `{rel}` — outside project root (skipped)")
            continue
        if not path.exists():
            parts.append(f"- `{rel}` — not found")
            continue
        if path.is_dir():
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            lines = []
            for i, e in enumerate(entries):
                if i >= max_dir_entries:
                    lines.append(f"... ({len(entries)} total)")
                    break
                kind = "dir" if e.is_dir() else "file"
                lines.append(f"  {kind:4} {e.name}")
            parts.append(f"### @{rel}/ (directory)\n" + "\n".join(lines))
        elif path.is_file():
            try:
                data = path.read_text(encoding="utf-8", errors="replace")
            except Exception as exc:
                parts.append(f"- `{rel}` — read error: {exc}")
                continue
            if len(data) > max_file_chars:
                data = data[:max_file_chars] + "\n…[truncated]"
            parts.append(f"### @{rel}\n```\n{data}\n```")
        else:
            parts.append(f"- `{rel}` — not a file or directory")
    return "\n\n".join(parts)
