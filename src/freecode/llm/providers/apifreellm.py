"""
llm.providers.apifreellm - thin wrapper around ApiFreeLLMClient.
"""
from __future__ import annotations

from freecode.config.settings import LLMSettings
from freecode.llm.client import ApiFreeLLMClient
from freecode.llm.response import ChatResponse


class ApiFreeLLMProvider:
    name = "apifreellm"

    def __init__(self, settings: LLMSettings, **kwargs) -> None:
        self._client = ApiFreeLLMClient(settings, **kwargs)

    @property
    def has_api_key(self) -> bool:
        return self._client.has_api_key

    async def send(self, message: str, *, model: str | None = None) -> ChatResponse:
        return await self._client.send(message, model=model)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ApiFreeLLMProvider:
        await self._client._ensure_client()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()
