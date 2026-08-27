"""
llm.protocol - structured agent response contract.

The free-tier model has no tool-calling, so it must emit this JSON as
plain text. The repair layer turns messy model output into AgentResponse.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

from freecode.domain.actions import Action, parse_action

AgentStatus = Literal["continue", "done", "needs_input"]
_VALID_STATUS: frozenset[str] = frozenset({"continue", "done", "needs_input"})


@dataclass(frozen=True, slots=True)
class ContextUpdate:
    """Optional facts the model wants remembered across turns."""

    facts: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> ContextUpdate:
        if not data:
            return cls()
        raw = data.get("facts", ())
        if isinstance(raw, str):
            facts = (raw,) if raw.strip() else ()
        elif isinstance(raw, Sequence):
            facts = tuple(str(x) for x in raw if x is not None and str(x).strip())
        else:
            facts = ()
        return cls(facts=facts)


@dataclass(frozen=True, slots=True)
class AgentResponse:
    """
    Parsed agent turn.

    `fallback` is True when the model output could not be parsed as the
    structured contract and the plain-text path was used instead. A
    fallback must NOT trigger another LLM call by itself (ph-05 rule).
    """

    message: str
    actions: tuple[Action, ...] = ()
    context_update: ContextUpdate = field(default_factory=ContextUpdate)
    status: AgentStatus = "continue"
    fallback: bool = False
    raw_text: str = ""

    @property
    def is_structured(self) -> bool:
        return not self.fallback

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, raw_text: str = "") -> AgentResponse:
        message = data.get("message", "")
        if message is None:
            message = ""
        if not isinstance(message, str):
            message = str(message)

        actions_raw = data.get("actions", [])
        actions: list[Action] = []
        if isinstance(actions_raw, Sequence) and not isinstance(actions_raw, (str, bytes)):
            for item in actions_raw:
                if isinstance(item, Mapping):
                    actions.append(parse_action(item))
                else:
                    raise ValueError(f"action entry must be an object, got {type(item).__name__}")
        elif actions_raw is not None and actions_raw != []:
            raise ValueError("actions must be an array")

        status_raw = data.get("status", "continue")
        if not isinstance(status_raw, str) or status_raw not in _VALID_STATUS:
            raise ValueError(
                f"status must be one of {sorted(_VALID_STATUS)}, got {status_raw!r}"
            )
        status: AgentStatus = status_raw  # type: ignore[assignment]

        ctx_raw = data.get("context_update")
        if ctx_raw is not None and not isinstance(ctx_raw, Mapping):
            raise ValueError("context_update must be an object")
        context_update = ContextUpdate.from_mapping(
            ctx_raw if isinstance(ctx_raw, Mapping) else None
        )

        return cls(
            message=message,
            actions=tuple(actions),
            context_update=context_update,
            status=status,
            fallback=False,
            raw_text=raw_text,
        )

    @classmethod
    def plain_text_fallback(cls, text: str) -> AgentResponse:
        """Safe degrade path when structured parse fails."""
        return cls(
            message=text.strip() if text else "",
            actions=(),
            context_update=ContextUpdate(),
            status="continue",
            fallback=True,
            raw_text=text,
        )
