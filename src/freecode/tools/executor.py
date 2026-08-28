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
from freecode.domain.actions import Action, CommandAction, EditAction, WebAction
from freecode.tools import filesystem, git, search, shell, web
from freecode.tools.filesystem import PathEscapeError
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
        self.plan_mode = False
        self._undo_stack: list[list[tuple[Path, str | None]]] = []  # batches of (path, old_text|None)
        self._current_batch: list[tuple[Path, str | None]] = []

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

        if self.plan_mode:
            return ToolResult(
                tool="plan",
                status="ok",
                output=f"[plan] skipped: {action!r}",
                data={"planned": True, "action": getattr(action, "type", "?")},
            )

        if isinstance(action, EditAction):
            snap = self._snapshot_before_edit(action.file)
            try:
                result = filesystem.apply_edit(
                    self.root, action.file, action.old, action.new
                )
            except PathEscapeError as exc:
                if approved:
                    # Explicit user allow for outside-root write
                    target = Path(exc.target)
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if action.old:
                            existing = target.read_text(encoding="utf-8") if target.exists() else ""
                            if action.old not in existing:
                                result = ToolResult(
                                    tool="edit",
                                    status="error",
                                    error="old text not found (outside-root)",
                                    mutating=True,
                                )
                            else:
                                target.write_text(
                                    existing.replace(action.old, action.new, 1),
                                    encoding="utf-8",
                                )
                                result = ToolResult(
                                    tool="edit",
                                    status="ok",
                                    output=f"edited {action.file} (outside root)",
                                    data={"path": str(target), "outside_root": True},
                                    mutating=True,
                                )
                        else:
                            target.write_text(action.new, encoding="utf-8")
                            result = ToolResult(
                                tool="edit",
                                status="ok",
                                output=f"wrote {action.file} (outside root)",
                                data={"path": str(target), "outside_root": True},
                                mutating=True,
                            )
                    except Exception as e:
                        result = ToolResult(
                            tool="edit", status="error", error=str(e), mutating=True
                        )
                else:
                    result = ToolResult(
                        tool="edit",
                        status="error",
                        error=str(exc),
                        mutating=True,
                    )
            self._emit_tool(result)
            if result.ok:
                self._current_batch.append(snap)
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

        if isinstance(action, WebAction):
            if not approved and self.approval.default_policy != "auto":
                return ToolResult(
                    tool="web_fetch",
                    status="error",
                    error="web lookup requires approval",
                )
            if action.url:
                result = web.fetch_url(action.url)
            else:
                result = web.web_search_duckduckgo(action.query)
            self._emit_tool(result)
            return result

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

    def begin_action_batch(self) -> None:
        self._current_batch = []

    def commit_undo_batch(self) -> None:
        if self._current_batch:
            self._undo_stack.append(self._current_batch)
            # keep last 10 batches
            self._undo_stack = self._undo_stack[-10:]
        self._current_batch = []

    def undo_last_batch(self) -> ToolResult:

        """Restore files from the last mutating batch (edits/writes)."""
        if not self._undo_stack:
            return ToolResult(tool="undo", status="error", error="nothing to undo")
        batch = self._undo_stack.pop()
        restored: list[str] = []
        errors: list[str] = []
        for path, old in batch:
            try:
                if old is None:
                    if path.exists():
                        path.unlink()
                        restored.append(f"removed {path}")
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(old, encoding="utf-8")
                    restored.append(str(path))
            except Exception as exc:
                errors.append(f"{path}: {exc}")
        if errors and not restored:
            return ToolResult(tool="undo", status="error", error="; ".join(errors))
        msg = "Restored:\n" + "\n".join(restored)
        if errors:
            msg += "\nErrors:\n" + "\n".join(errors)
        return ToolResult(tool="undo", status="ok", output=msg, mutating=True)

    def _snapshot_before_edit(self, rel: str) -> tuple[Path, str | None]:
        path = (self.root / rel).resolve() if not Path(rel).is_absolute() else Path(rel)
        try:
            if path.exists() and path.is_file():
                return path, path.read_text(encoding="utf-8")
        except Exception:
            pass
        return path, None
