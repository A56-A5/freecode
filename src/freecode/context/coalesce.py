"""
context.coalesce - Event Coalescer (ph-09).

Buffers events that occur during cooldown / between agent turns and
folds them into a compact block for the next reasoning prompt.

This is a central FreeCode performance mechanism: avoid one LLM call
per tiny tool event; batch into the next turn.
"""
from __future__ import annotations

from freecode.context.tokens import estimate_tokens
from freecode.domain.events import Event, EventType


# When coalescing, keep at most this many of each type (oldest dropped first
# within a type after the cap, except we prefer newest).
_DEFAULT_CAPS: dict[EventType, int] = {
    "tool_result": 12,
    "file_changed": 20,
    "command_started": 8,
    "command_finished": 8,
    "git_changed": 3,
    "user_message": 4,
    "approval_result": 8,
    "agent_turn": 4,
    "error": 6,
}


class EventCoalescer:
    """
    In-memory event buffer with type-aware capping and prompt formatting.
    """

    def __init__(self, caps: dict[EventType, int] | None = None) -> None:
        self._events: list[Event] = []
        self._caps = dict(_DEFAULT_CAPS)
        if caps:
            self._caps.update(caps)

    def __len__(self) -> int:
        return len(self._events)

    @property
    def events(self) -> tuple[Event, ...]:
        return tuple(self._events)

    def emit(self, event: Event) -> None:
        self._events.append(event)
        self._enforce_caps()

    def emit_many(self, events: list[Event] | tuple[Event, ...]) -> None:
        for e in events:
            self._events.append(e)
        self._enforce_caps()

    def clear(self) -> list[Event]:
        """Drain and return buffered events."""
        out = list(self._events)
        self._events.clear()
        return out

    def peek(self) -> list[Event]:
        return list(self._events)

    def _enforce_caps(self) -> None:
        by_type: dict[str, list[Event]] = {}
        for e in self._events:
            by_type.setdefault(e.type, []).append(e)
        kept: list[Event] = []
        for typ, items in by_type.items():
            cap = self._caps.get(typ, 10)  # type: ignore[arg-type]
            if len(items) > cap:
                items = items[-cap:]
            kept.extend(items)
        kept.sort(key=lambda e: e.ts)
        self._events = kept

    def coalesce_for_prompt(
        self,
        *,
        token_budget: int = 2000,
        chars_per_token: float = 4.0,
        drain: bool = False,
    ) -> str:
        """
        Build a compact text block describing pending events.

        If drain=True, clears the buffer (typical when attaching to next turn).
        """
        events = self.clear() if drain else list(self._events)
        if not events:
            return ""

        # Group for readability
        lines: list[str] = ["Events since last reasoning turn:"]
        for e in events:
            line = f"- [{e.type}] {e.summary}"
            # Attach short output for tool_result / command_finished when useful
            if e.type == "tool_result":
                out = (e.payload.get("output") or "")[:240]
                if out.strip():
                    line += f"\n  output: {out.strip()}"
            elif e.type == "command_finished":
                out = (e.payload.get("output") or "")[:240]
                if out.strip():
                    line += f"\n  output: {out.strip()}"
            lines.append(line)

        text = "\n".join(lines)
        # Budget trim from the top (drop oldest detail lines)
        while estimate_tokens(text, chars_per_token) > token_budget and len(lines) > 2:
            # remove second line (first event) repeatedly
            lines.pop(1)
            text = "\n".join(lines)
        return text
