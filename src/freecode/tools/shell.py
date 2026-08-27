"""
tools.shell - run local shell commands (async subprocess).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from freecode.tools.results import ToolResult

DEFAULT_TIMEOUT = 60.0
MAX_OUTPUT = 100_000


async def run_command(
    command: str,
    *,
    cwd: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> ToolResult:
    command = (command or "").strip()
    if not command:
        return ToolResult(tool="shell", status="error", error="empty command", mutating=True)
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ToolResult(
                tool="shell",
                status="error",
                error=f"timed out after {timeout}s",
                mutating=True,
            )
        stdout = stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT]
        stderr = stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT]
        code = proc.returncode or 0
        parts = []
        if stdout:
            parts.append(stdout.rstrip())
        if stderr:
            parts.append(f"[stderr]\n{stderr.rstrip()}")
        parts.append(f"[exit {code}]")
        status = "ok" if code == 0 else "error"
        return ToolResult(
            tool="shell",
            status=status,
            output="\n".join(parts),
            error=None if code == 0 else f"exit code {code}",
            data={"exit_code": code, "command": command},
            mutating=True,
        )
    except Exception as exc:
        return ToolResult(tool="shell", status="error", error=str(exc), mutating=True)
