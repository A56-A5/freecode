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


async def grep_search(
    root: Path,
    pattern: str,
    *,
    file_pattern: str = "*",
    is_regex: bool = False,
    max_hits: int = 100,
) -> ToolResult:
    """
    Search files using grep or ripgrep.

    Args:
        root: Project root directory
        pattern: Search pattern
        file_pattern: Glob pattern for files to search (default: "*")
        is_regex: Treat pattern as regex (default: false)
        max_hits: Maximum number of matches to return

    Returns:
        ToolResult with search results
    """
    pattern = (pattern or "").strip()
    if not pattern:
        return ToolResult(tool="grep_search", status="error", error="empty pattern")

    file_pattern = (file_pattern or "*").strip()

    if shutil.which("rg"):
        # Use ripgrep
        import shlex

        args = [
            "rg",
            "-n",
            "--max-count",
            str(max_hits),
            "--glob",
            f"!.git/*",
            "--glob",
            "!.venv/*",
            "--glob",
            "!node_modules/*",
        ]
        if not is_regex:
            args.append("--fixed-strings")
        for p in file_pattern.split(","):
            args.extend(["-g", f"!{p.strip()}"])
        args.append(pattern)

        cmd = " ".join(shlex.quote(arg) for arg in args)
        r = await run_command(cmd, cwd=root)
        return ToolResult(
            tool="grep_search",
            status="ok",
            output=r.output or "(no matches)",
            error=None if (r.data.get("exit_code") in (0, 1) if r.data else True) else r.error,
            data=r.data,
            mutating=False,
        )

    # Fallback: use grep or walk files
    if shutil.which("grep"):
        cmd = f"grep -rn --include='*{file_pattern}' {pattern!r} ."
        r = await run_command(cmd, cwd=root)
        return ToolResult(
            tool="grep_search",
            status="ok",
            output=r.output or "(no matches)",
            error=None if r.status == "ok" else r.error,
            data=r.data,
            mutating=False,
        )

    # Pure Python fallback
    hits: list[str] = []
    root = root.resolve()
    try:
        import fnmatch
        from pathlib import Path

        for path in root.rglob("*"):
            if len(hits) >= max_hits:
                break
            if not path.is_file():
                continue
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            if not fnmatch.fnmatch(path.name, file_pattern):
                continue
            try:
                if path.stat().st_size > 1_000_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            for i, line in enumerate(text.splitlines(), 1):
                match = False
                if is_regex:
                    import re

                    match = re.search(pattern, line) is not None
                else:
                    match = pattern in line

                if match:
                    rel = path.relative_to(root)
                    hits.append(f"{rel}:{i}:{line.strip()[:200]}")
                    if len(hits) >= max_hits:
                        break

        return ToolResult(
            tool="grep_search",
            status="ok",
            output="\n".join(hits) if hits else "(no matches)",
            data={"hits": len(hits)},
            mutating=False,
        )
    except Exception as exc:
        return ToolResult(tool="grep_search", status="error", error=str(exc))


async def find_files(
    root: Path,
    pattern: str,
    max_results: int = 100,
) -> ToolResult:
    """
    Find files matching a glob pattern.

    Args:
        root: Project root directory
        pattern: Glob pattern to match
        max_results: Maximum number of files to return

    Returns:
        ToolResult with matching file paths
    """
    pattern = (pattern or "").strip()
    if not pattern:
        return ToolResult(tool="find_files", status="error", error="empty pattern")

    if shutil.which("find"):
        # Use find command
        import shlex

        cmd = f"find . -name {shlex.quote(pattern)} -not -path '*/.*' -type f | head -n {max_results}"
        r = await run_command(cmd, cwd=root)
        return ToolResult(
            tool="find_files",
            status="ok",
            output=r.output or "(no files found)",
            error=None if r.status == "ok" else r.error,
            data=r.data,
            mutating=False,
        )

    # Pure Python fallback
    files: list[str] = []
    root = root.resolve()
    try:
        import fnmatch

        for path in root.rglob("*"):
            if len(files) >= max_results:
                break
            if not path.is_file():
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            if fnmatch.fnmatch(path.name, pattern):
                files.append(str(path.relative_to(root)))

        return ToolResult(
            tool="find_files",
            status="ok",
            output="\n".join(files) if files else "(no files found)",
            data={"found": len(files)},
            mutating=False,
        )
    except Exception as exc:
        return ToolResult(tool="find_files", status="error", error=str(exc))
