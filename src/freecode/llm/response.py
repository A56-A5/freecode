"""
llm.response - inbound ApiFreeLLM response shape.

The client maps the JSON body into these dataclasses. Structured agent
protocol parsing (message/actions/status JSON inside `text`) is ph-05
Response Repair — this layer only captures transport metadata.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ResponseFeatures:
    """`features` object from a successful ApiFreeLLM response."""

    unlimited: bool = False
    delay_seconds: float | None = None
    priority_processing: bool = False

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> ResponseFeatures:
        if not data:
            return cls()
        delay_raw = data.get("delaySeconds", data.get("delay_seconds"))
        delay: float | None
        try:
            delay = float(delay_raw) if delay_raw is not None else None
        except (TypeError, ValueError):
            delay = None
        return cls(
            unlimited=bool(data.get("unlimited", False)),
            delay_seconds=delay,
            priority_processing=bool(
                data.get("priorityProcessing", data.get("priority_processing", False))
            ),
        )


@dataclass(frozen=True, slots=True)
class ChatResponse:
    """Normalized result of a successful ApiFreeLLM chat call."""

    text: str
    success: bool = True
    tier: str | None = None
    features: ResponseFeatures = field(default_factory=ResponseFeatures)
    # Raw body kept for debugging / future protocol layers; not required.
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def delay_seconds(self) -> float | None:
        return self.features.delay_seconds

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ChatResponse:
        text = data.get("response", data.get("text", ""))
        if text is None:
            text = ""
        if not isinstance(text, str):
            text = str(text)
        return cls(
            text=text,
            success=bool(data.get("success", True)),
            tier=data.get("tier") if isinstance(data.get("tier"), str) else None,
            features=ResponseFeatures.from_mapping(
                data.get("features") if isinstance(data.get("features"), Mapping) else None
            ),
            raw=dict(data),
        )
