"""
security.policy - classify operations for approval decisions.

Independent of TUI. Used by ApprovalGate and ToolExecutor.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path

from freecode.config.settings import ApprovalSettings
from freecode.domain.actions import Action, CommandAction, EditAction, WebAction
from freecode.tools.executor import is_readonly_command
from freecode.tools.filesystem import path_escapes_root


class RiskLevel(str, Enum):
    # OUTSIDE_ROOT applies to EditAction paths only. Shell that cds elsewhere
    # is classified DESTRUCTIVE / WRITE and still prompts under auto_readonly.
    READONLY = "readonly"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    GIT_MUTATION = "git_mutation"
    OUTSIDE_ROOT = "outside_root"
    WEB = "web"


_DESTRUCTIVE_RE = re.compile(
    r"\b(rm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r)|rmdir|del\b|format\b|"
    r"mkfs|dd\s+if=|shutdown|reboot|"
    r"git\s+push\s+.*(--force|-f)\b|git\s+reset\s+--hard|"
    r"git\s+clean\s+-[a-z]*f|drop\s+table|truncate\s+table)\b",
    re.IGNORECASE,
)

_GIT_MUTATION_RE = re.compile(
    r"^\s*git\s+(add|commit|push|pull|fetch|merge|rebase|checkout|switch|"
    r"branch|tag|stash|reset|clean|cherry-pick)\b",
    re.IGNORECASE,
)

_DELETE_PATH_RE = re.compile(r"\b(rm|rmdir|unlink|del)\b", re.IGNORECASE)


def classify_command(command: str) -> RiskLevel:
    cmd = (command or "").strip()
    if not cmd:
        return RiskLevel.WRITE
    if _DESTRUCTIVE_RE.search(cmd) or _DELETE_PATH_RE.search(cmd):
        return RiskLevel.DESTRUCTIVE
    if _GIT_MUTATION_RE.match(cmd):
        return RiskLevel.GIT_MUTATION
    return RiskLevel.WRITE


def classify_action(
    action: Action,
    settings: ApprovalSettings | None = None,
    *,
    project_root: Path | str | None = None,
) -> RiskLevel:
    if isinstance(action, WebAction):
        return RiskLevel.WEB
    if isinstance(action, EditAction):
        if project_root is not None and path_escapes_root(Path(project_root), action.file):
            return RiskLevel.OUTSIDE_ROOT
        return RiskLevel.WRITE
    if isinstance(action, CommandAction):
        settings = settings or ApprovalSettings()
        if is_readonly_command(action.command, settings.readonly_allowlist):
            return RiskLevel.READONLY
        return classify_command(action.command)
    return RiskLevel.WRITE


def risk_label(level: RiskLevel) -> str:
    return {
        RiskLevel.READONLY: "read-only",
        RiskLevel.WRITE: "write",
        RiskLevel.DESTRUCTIVE: "destructive",
        RiskLevel.GIT_MUTATION: "git mutation",
        RiskLevel.OUTSIDE_ROOT: "outside project root",
        RiskLevel.WEB: "web lookup",
    }[level]
