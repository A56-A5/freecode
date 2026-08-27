"""
tools.git - thin wrappers around git CLI (read-oriented helpers).
"""
from __future__ import annotations

from pathlib import Path

from freecode.tools.results import ToolResult
from freecode.tools.shell import run_command


async def git_status(cwd: Path) -> ToolResult:
    r = await run_command("git status --short", cwd=cwd)
    return ToolResult(
        tool="git_status",
        status=r.status,
        output=r.output,
        error=r.error,
        data=r.data,
        mutating=False,
    )


async def git_diff(cwd: Path, *, staged: bool = False) -> ToolResult:
    cmd = "git diff --staged" if staged else "git diff"
    r = await run_command(cmd, cwd=cwd)
    return ToolResult(
        tool="git_diff",
        status=r.status,
        output=r.output,
        error=r.error,
        data=r.data,
        mutating=False,
    )


async def git_log(cwd: Path, *, n: int = 10) -> ToolResult:
    r = await run_command(f"git log -n {int(n)} --oneline", cwd=cwd)
    return ToolResult(
        tool="git_log",
        status=r.status,
        output=r.output,
        error=r.error,
        data=r.data,
        mutating=False,
    )
