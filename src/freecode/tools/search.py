"""
tools.search - project text search (rg if available, else pure Python).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from freecode.tools.results import ToolResult
from freecode.tools.shell import run_command

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".freecode", "dist", "build"}


async def search_text(
    root: Path,
    query: str,
    *,
    max_hits: int = 50,
) -> ToolResult:
    query = (query or "").strip()
    if not query:
        return ToolResult(tool="search", status="error", error="empty query")

    if shutil.which("rg"):
        # Fixed-string search for safety
        cmd = f'rg -n --fixed-strings --max-count {max_hits} --glob "!.git/*" {query!s}'
        # Use list form via shell carefully — escape handled by shlex in future
        import shlex
        cmd = (
            "rg -n --fixed-strings "
            f"--max-count {max_hits} "
            "--glob '!.git/*' --glob '!.venv/*' --glob '!node_modules/*' "
            + shlex.quote(query)
        )
        r = await run_command(cmd, cwd=root)
        return ToolResult(
            tool="search",
            status="ok" if r.status in ("ok", "error") else r.status,
            output=r.output or "(no matches)",
            error=None if (r.data.get("exit_code") in (0, 1) if r.data else True) else r.error,
            data=r.data,
            mutating=False,
        )

    # Fallback: walk files
    hits: list[str] = []
    root = root.resolve()
    try:
        for path in root.rglob("*"):
            if len(hits) >= max_hits:
                break
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if query in line:
                    rel = path.relative_to(root)
                    hits.append(f"{rel}:{i}:{line.strip()[:200]}")
                    if len(hits) >= max_hits:
                        break
        return ToolResult(
            tool="search",
            status="ok",
            output="\n".join(hits) if hits else "(no matches)",
            data={"hits": len(hits)},
            mutating=False,
        )
    except Exception as exc:
        return ToolResult(tool="search", status="error", error=str(exc))
