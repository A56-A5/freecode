"""
tools.executor - run agent Actions and direct tool calls under a policy.

Read-only tools may auto-run under `auto_readonly`. Mutating ops require
`auto` policy or an explicit `approved=True` from the caller (TUI/approval
gate in later phases).
"""
from __future__ import annotations

from pathlib import Path

from freecode.config.logging import get_logger
from freecode.config.settings import ApprovalPolicy, ApprovalSettings
from freecode.domain.actions import Action, CommandAction, EditAction
from freecode.tools import filesystem, git, search, shell
from freecode.domain.events import command_finished_event, command_started_event, file_changed_event, tool_result_event
from freecode.tools.results import ToolResult
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freecode.context.coalesce import EventCoalescer

log = get_logger(__name__)


def is_readonly_command(command: str, allowlist: tuple[str, ...]) -> bool:
    cmd = (command or "").strip().lower()
    for prefix in allowlist:
        p = prefix.strip().lower()
        if not p:
            continue
        if cmd == p.rstrip() or cmd.startswith(p):
            return True
    return False


def action_needs_approval(
    action: Action,
    settings: ApprovalSettings,
) -> bool:
    policy: ApprovalPolicy = settings.default_policy
    if policy == "auto":
        return False
    if policy == "ask":
        return True
    # auto_readonly
    if isinstance(action, EditAction):
        return True
    if isinstance(action, CommandAction):
        return not is_readonly_command(action.command, settings.readonly_allowlist)
    return True


class ToolExecutor:
    """
    Executes tools relative to a project root.

    MCP remains a thin boundary later; this is the local implementation.
    """

    def __init__(
        self,
        root: Path | str,
        approval: ApprovalSettings | None = None,
        coalescer: EventCoalescer | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        self.approval = approval or ApprovalSettings()
        self.coalescer = coalescer

    async def execute_action(
        self,
        action: Action,
        *,
        approved: bool = False,
    ) -> ToolResult:
        if action_needs_approval(action, self.approval) and not approved:
            log.info("action denied (needs approval): %s", action)
            return ToolResult(
                tool=getattr(action, "type", "action"),
                status="denied",
                error="approval required",
                mutating=True,
            )

        if isinstance(action, EditAction):
            result = filesystem.apply_edit(
                self.root, action.file, action.old, action.new
            )
            self._emit_tool(result)
            if result.ok:
                self._emit(file_changed_event(action.file))
            return result
        if isinstance(action, CommandAction):
            self._emit(command_started_event(action.command))
            result = await shell.run_command(action.command, cwd=self.root)
            readonly = is_readonly_command(
                action.command, self.approval.readonly_allowlist
            )
            out = ToolResult(
                tool=result.tool,
                status=result.status,
                output=result.output,
                error=result.error,
                data=result.data,
                mutating=not readonly,
            )
            self._emit_tool(out)
            code = int((result.data or {}).get("exit_code", 1))
            self._emit(command_finished_event(action.command, code, result.output))
            return out
        return ToolResult(
            tool="unknown",
            status="error",
            error=f"unsupported action: {type(action)!r}",
        )

    async def execute_actions(
        self,
        actions: list[Action] | tuple[Action, ...],
        *,
        approved: bool = False,
    ) -> list[ToolResult]:
        results: list[ToolResult] = []
        for action in actions:
            results.append(await self.execute_action(action, approved=approved))
        return results

    # ── direct tool API ──────────────────────────────────────────────

    def read_file(self, path: str) -> ToolResult:
        return filesystem.read_file(self.root, path)

    def write_file(self, path: str, content: str, *, approved: bool = False) -> ToolResult:
        if self.approval.default_policy != "auto" and not approved:
            return ToolResult(
                tool="write_file",
                status="denied",
                error="approval required",
                mutating=True,
            )
        return filesystem.write_file(self.root, path, content)

    def list_dir(self, path: str = ".") -> ToolResult:
        return filesystem.list_dir(self.root, path)

    async def run_shell(self, command: str, *, approved: bool = False) -> ToolResult:
        action = CommandAction(command=command)
        return await self.execute_action(action, approved=approved)

    async def git_status(self) -> ToolResult:
        return await git.git_status(self.root)

    async def git_diff(self, *, staged: bool = False) -> ToolResult:
        return await git.git_diff(self.root, staged=staged)

    async def git_log(self, n: int = 10) -> ToolResult:
        return await git.git_log(self.root, n=n)

    async def search(self, query: str) -> ToolResult:
        return await search.search_text(self.root, query)

    def _emit(self, event) -> None:
        if self.coalescer is not None:
            self.coalescer.emit(event)

    def _emit_tool(self, result: ToolResult) -> None:
        self._emit(
            tool_result_event(
                result.tool,
                result.status,
                result.output,
                error=result.error,
                mutating=result.mutating,
            )
        )
