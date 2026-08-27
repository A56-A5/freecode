"""
tools.filesystem - read / write / list under a project root.
"""
from __future__ import annotations

from pathlib import Path

from freecode.tools.results import ToolResult


def _resolve(root: Path, rel: str) -> Path:
    root = root.resolve()
    target = (root / rel).resolve()
    if not str(target).startswith(str(root)):
        raise ValueError(f"path escapes project root: {rel}")
    return target


def read_file(root: Path, path: str, *, max_bytes: int = 512_000) -> ToolResult:
    try:
        target = _resolve(root, path)
        if not target.is_file():
            return ToolResult(tool="read_file", status="error", error=f"not a file: {path}")
        data = target.read_bytes()
        if len(data) > max_bytes:
            return ToolResult(
                tool="read_file",
                status="error",
                error=f"file too large ({len(data)} bytes)",
            )
        text = data.decode("utf-8", errors="replace")
        return ToolResult(tool="read_file", status="ok", output=text, data={"path": str(target)})
    except Exception as exc:
        return ToolResult(tool="read_file", status="error", error=str(exc))


def write_file(root: Path, path: str, content: str) -> ToolResult:
    try:
        target = _resolve(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(
            tool="write_file",
            status="ok",
            output=f"wrote {len(content)} chars to {path}",
            data={"path": str(target)},
            mutating=True,
        )
    except Exception as exc:
        return ToolResult(tool="write_file", status="error", error=str(exc), mutating=True)


def list_dir(root: Path, path: str = ".", *, max_entries: int = 500) -> ToolResult:
    try:
        target = _resolve(root, path)
        if not target.is_dir():
            return ToolResult(tool="list_dir", status="error", error=f"not a directory: {path}")
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for i, p in enumerate(entries):
            if i >= max_entries:
                lines.append(f"... truncated ({len(entries)} total)")
                break
            kind = "dir" if p.is_dir() else "file"
            lines.append(f"{kind:4} {p.name}")
        return ToolResult(
            tool="list_dir",
            status="ok",
            output="\n".join(lines),
            data={"path": str(target), "count": len(entries)},
        )
    except Exception as exc:
        return ToolResult(tool="list_dir", status="error", error=str(exc))


def apply_edit(root: Path, path: str, old: str, new: str) -> ToolResult:
    """Apply EditAction: replace old with new in file (or write new if empty old)."""
    try:
        target = _resolve(root, path)
        if target.exists():
            current = target.read_text(encoding="utf-8")
            if old and old not in current:
                return ToolResult(
                    tool="apply_edit",
                    status="error",
                    error="old text not found in file",
                    mutating=True,
                )
            updated = current.replace(old, new, 1) if old else new
        else:
            if old:
                return ToolResult(
                    tool="apply_edit",
                    status="error",
                    error="file does not exist and old text was provided",
                    mutating=True,
                )
            updated = new
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(updated, encoding="utf-8")
        return ToolResult(
            tool="apply_edit",
            status="ok",
            output=f"edited {path}",
            data={"path": str(target)},
            mutating=True,
        )
    except Exception as exc:
        return ToolResult(tool="apply_edit", status="error", error=str(exc), mutating=True)
