"""
domain.events - local execution event contracts (ph-09).

Pure data. No I/O. Used by the Event Coalescer and later persistence.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

EventType = Literal[
    "tool_result",
    "file_changed",
    "command_started",
    "command_finished",
    "git_changed",
    "user_message",
    "approval_result",
    "agent_turn",
    "error",
]


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


@dataclass(frozen=True, slots=True)
class Event:
    """One local execution event."""

    type: EventType
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=_new_id)
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "summary": self.summary,
            "payload": dict(self.payload),
            "ts": self.ts,
        }


def tool_result_event(
    tool: str,
    status: str,
    output: str = "",
    *,
    error: str | None = None,
    mutating: bool = False,
) -> Event:
    summary = f"{tool}: {status}"
    if error:
        summary = f"{tool}: {status} ({error})"
    return Event(
        type="tool_result",
        summary=summary,
        payload={
            "tool": tool,
            "status": status,
            "output": output[:4000],
            "error": error,
            "mutating": mutating,
        },
    )


def file_changed_event(path: str, kind: str = "modified") -> Event:
    return Event(
        type="file_changed",
        summary=f"file {kind}: {path}",
        payload={"path": path, "kind": kind},
    )


def command_started_event(command: str) -> Event:
    return Event(
        type="command_started",
        summary=f"cmd start: {command[:120]}",
        payload={"command": command},
    )


def command_finished_event(command: str, exit_code: int, output: str = "") -> Event:
    return Event(
        type="command_finished",
        summary=f"cmd exit {exit_code}: {command[:80]}",
        payload={"command": command, "exit_code": exit_code, "output": output[:4000]},
    )


def git_changed_event(summary: str = "git working tree changed") -> Event:
    return Event(type="git_changed", summary=summary, payload={})


def user_message_event(text: str) -> Event:
    return Event(
        type="user_message",
        summary=text[:160],
        payload={"text": text[:8000]},
    )


def approval_result_event(approved: bool, action_summary: str) -> Event:
    return Event(
        type="approval_result",
        summary=f"{'approved' if approved else 'denied'}: {action_summary[:120]}",
        payload={"approved": approved, "action": action_summary},
    )


def agent_turn_event(status: str, message: str) -> Event:
    return Event(
        type="agent_turn",
        summary=f"agent {status}: {message[:120]}",
        payload={"status": status, "message": message[:4000]},
    )


def error_event(message: str) -> Event:
    return Event(type="error", summary=message[:200], payload={"message": message[:4000]})
