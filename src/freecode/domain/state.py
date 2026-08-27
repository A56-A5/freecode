"""
domain.state - agent session state shape (ph-06).

Pure data. No I/O, no Textual, no HTTP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freecode.domain.actions import Action
    from freecode.llm.protocol import AgentResponse


class AgentPhase(str, Enum):
    """High-level lifecycle phase of the agent."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    NEEDS_INPUT = "needs_input"
    DONE = "done"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass(slots=True)
class TurnRecord:
    """One user or assistant utterance kept for short context."""

    role: str  # "user" | "assistant"
    content: str


@dataclass(slots=True)
class AgentState:
    """Mutable session state owned by Agent Core."""

    goal: str | None = None
    phase: AgentPhase = AgentPhase.IDLE
    turn: int = 0
    facts: tuple[str, ...] = ()
    pending_actions: tuple = ()
    last_message: str = ""
    last_status: str = "continue"
    last_fallback: bool = False
    history: list[TurnRecord] = field(default_factory=list)
    error: str | None = None

    def append_user(self, text: str) -> None:
        self.history.append(TurnRecord(role="user", content=text))

    def append_assistant(self, text: str) -> None:
        self.history.append(TurnRecord(role="assistant", content=text))

    def merge_facts(self, new_facts: tuple[str, ...]) -> None:
        if not new_facts:
            return
        seen = set(self.facts)
        merged = list(self.facts)
        for f in new_facts:
            if f not in seen:
                seen.add(f)
                merged.append(f)
        self.facts = tuple(merged)
