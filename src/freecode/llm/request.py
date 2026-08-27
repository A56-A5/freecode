"""
llm.request - outbound ApiFreeLLM request shape.

The free-tier chat endpoint accepts a single flat message string and an
optional model alias — no roles, no message array, no tools.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChatRequest:
    """Payload for POST /api/v1/chat."""

    message: str
    model: str = "apifreellm"

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not self.message.strip():
            raise ValueError("message must be non-empty")
        if not isinstance(self.model, str) or not self.model.strip():
            raise ValueError("model must be a non-empty string")

    def to_body(self) -> dict[str, str]:
        return {"message": self.message, "model": self.model}
