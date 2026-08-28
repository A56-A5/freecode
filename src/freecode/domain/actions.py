"""
domain.actions - structured action types the agent may emit.

Filled in by ph-05 (response protocol). These are pure data contracts —
no filesystem or shell execution happens here (that is tools/MCP later).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

ActionType = Literal["edit", "command", "web"]


@dataclass(frozen=True, slots=True)
class EditAction:
    """Propose a file edit (old → new). Applied only after approval."""

    file: str
    old: str
    new: str
    type: Literal["edit"] = "edit"

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "edit",
            "file": self.file,
            "old": self.old,
            "new": self.new,
        }


@dataclass(frozen=True, slots=True)
class CommandAction:
    """Propose a shell command. Applied only after approval (unless policy)."""

    command: str
    reason: str = ""
    type: Literal["command"] = "command"

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "command",
            "command": self.command,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class WebAction:
    """Fetch a URL (or search query) — always approval-gated."""

    url: str = ""
    query: str = ""
    reason: str = ""
    type: Literal["web"] = "web"

    def to_dict(self) -> dict[str, str]:
        d = {"type": "web", "reason": self.reason}
        if self.url:
            d["url"] = self.url
        if self.query:
            d["query"] = self.query
        return d


Action = EditAction | CommandAction | WebAction


def parse_action(data: Mapping[str, Any]) -> Action:
    """
    Parse a single action object from LLM JSON.

    Raises ValueError on unknown type or missing required fields.
    """
    if not isinstance(data, Mapping):
        raise ValueError(f"action must be an object, got {type(data).__name__}")
    raw_type = data.get("type")
    if raw_type == "edit":
        file = data.get("file")
        if not isinstance(file, str) or not file.strip():
            raise ValueError("edit action requires non-empty string 'file'")
        old = data.get("old", "")
        new = data.get("new", "")
        if not isinstance(old, str):
            old = str(old) if old is not None else ""
        if not isinstance(new, str):
            new = str(new) if new is not None else ""
        return EditAction(file=file.strip(), old=old, new=new)
    if raw_type == "command":
        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command action requires non-empty string 'command'")
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason) if reason is not None else ""
        return CommandAction(command=command.strip(), reason=reason)
    if raw_type in ("web", "web_fetch", "fetch", "lookup"):
        url = data.get("url") or data.get("href") or ""
        query = data.get("query") or data.get("q") or ""
        if not isinstance(url, str):
            url = str(url) if url else ""
        if not isinstance(query, str):
            query = str(query) if query else ""
        if not url.strip() and not query.strip():
            raise ValueError("web action requires 'url' or 'query'")
        reason = data.get("reason", "")
        if not isinstance(reason, str):
            reason = str(reason) if reason is not None else ""
        return WebAction(url=url.strip(), query=query.strip(), reason=reason)
    raise ValueError(f"unknown action type: {raw_type!r}")
