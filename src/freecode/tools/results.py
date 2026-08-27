"""
tools.results - shared result types for local tool execution.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ToolStatus = Literal["ok", "error", "denied", "skipped"]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Outcome of one tool invocation."""

    tool: str
    status: ToolStatus
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    mutating: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok"
