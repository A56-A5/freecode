"""
llm.providers.base - provider protocol for chat backends.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from freecode.llm.response import ChatResponse


@runtime_checkable
class ChatProvider(Protocol):
    """Minimal interface: send a flat user message, get ChatResponse."""

    name: str

    @property
    def has_api_key(self) -> bool: ...

    async def send(self, message: str, *, model: str | None = None) -> ChatResponse: ...

    async def aclose(self) -> None: ...
