"""
llm.providers.groq - OpenAI-compatible chat completions on Groq free tier.

Multi-key rotation via GROQ_API_KEY, GROQ_API_KEY_2, … (same pattern as
ApiFreeLLM community keys).
"""
from __future__ import annotations

from typing import Any, Mapping

import httpx

from freecode.config.logging import get_logger
from freecode.domain.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTransportError,
)
from freecode.llm.client import _error_message, _is_daily_quota_error, _parse_retry_after
from freecode.llm.response import ChatResponse, ResponseFeatures

log = get_logger(__name__)

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.1-8b-instant"

# Common Groq free-tier chat models (names as of Groq console / docs).
GROQ_MODELS: tuple[str, ...] = (
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "qwen/qwen3-32b",
    "gemma2-9b-it",
    "mistral-saba-24b",
    "moonshotai/kimi-k2-instruct",
)


def _is_groq_quota_error(message: str) -> bool:
    low = (message or "").lower()
    return _is_daily_quota_error(message) or any(
        n in low
        for n in (
            "rate limit",
            "tokens per day",
            "tpd",
            "quota",
            "too many requests",
        )
    )


class GroqProvider:
    name = "groq"

    def __init__(
        self,
        *,
        api_keys: tuple[str, ...] = (),
        model: str = DEFAULT_MODEL,
        timeout_seconds: float = 120.0,
        endpoint: str = GROQ_ENDPOINT,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_keys = tuple(k for k in api_keys if k)
        self._model = model
        self._timeout = timeout_seconds
        self._endpoint = endpoint
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._key_index = 0
        self._exhausted_keys: set[int] = set()

    @property
    def model(self) -> str:
        return self._model

    def set_model(self, model: str) -> bool:
        name = (model or "").strip()
        if not name:
            return False
        self._model = name
        return True

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_keys)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self._timeout),
                "headers": {"Content-Type": "application/json"},
            }
            if self._transport is not None:
                kwargs["transport"] = self._transport
            self._client = httpx.AsyncClient(**kwargs)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def __aenter__(self) -> GroqProvider:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.aclose()

    def _rotate_key(self) -> bool:
        if not self._api_keys:
            return False
        start = self._key_index
        for offset in range(1, len(self._api_keys) + 1):
            index = (start + offset) % len(self._api_keys)
            if index not in self._exhausted_keys:
                log.warning(
                    "Groq key exhausted: switching %d -> %d",
                    self._key_index + 1,
                    index + 1,
                )
                self._key_index = index
                return True
        return False

    async def send(self, message: str, *, model: str | None = None) -> ChatResponse:
        if not self._api_keys:
            raise LLMAuthError("No Groq API key configured (GROQ_API_KEY).", status_code=401)

        client = await self._ensure_client()
        use_model = model or self._model
        body = {
            "model": use_model,
            "messages": [{"role": "user", "content": message}],
            "temperature": 0.7,
        }

        attempted: set[int] = set()
        while len(attempted) < len(self._api_keys):
            if self._key_index in self._exhausted_keys:
                if not self._rotate_key():
                    break
            if self._key_index in attempted:
                break
            attempted.add(self._key_index)
            key = self._api_keys[self._key_index]
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

            try:
                response = await client.post(self._endpoint, json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise LLMTransportError(f"Groq timed out after {self._timeout:.0f}s") from exc
            except httpx.RequestError as exc:
                raise LLMTransportError(f"Groq transport error: {exc}") from exc

            if response.status_code == 200:
                return self._parse_success(response)

            msg = _error_message(response)
            if response.status_code in (429, 403) and _is_groq_quota_error(msg):
                self._exhausted_keys.add(self._key_index)
                log.warning("Groq key %d/%d quota: %s", self._key_index + 1, len(self._api_keys), msg[:120])
                if self._rotate_key():
                    continue
                raise LLMRateLimitError(
                    "All configured Groq API keys are rate-limited / quota-exhausted.",
                    status_code=429,
                    retry_after_seconds=_parse_retry_after(response.headers),
                )
            if response.status_code == 401:
                raise LLMAuthError(msg, status_code=401)
            if response.status_code == 400:
                raise LLMBadRequestError(msg, status_code=400)
            if response.status_code == 429:
                raise LLMRateLimitError(
                    msg,
                    status_code=429,
                    retry_after_seconds=_parse_retry_after(response.headers),
                )
            if 500 <= response.status_code <= 599:
                raise LLMServerError(msg, status_code=response.status_code)
            raise LLMServerError(f"Unexpected HTTP {response.status_code}: {msg}", status_code=response.status_code)

        raise LLMRateLimitError(
            "All configured Groq API keys are exhausted.",
            status_code=429,
        )

    def _parse_success(self, response: httpx.Response) -> ChatResponse:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError("Groq returned non-JSON body", status_code=200) from exc
        if not isinstance(data, dict):
            raise LLMResponseError("Groq body must be a JSON object", status_code=200)
        choices = data.get("choices") or []
        text = ""
        if choices and isinstance(choices[0], Mapping):
            msg = choices[0].get("message") or {}
            if isinstance(msg, Mapping):
                text = str(msg.get("content") or "")
        # No delaySeconds from Groq — scheduler uses floor.
        return ChatResponse(
            text=text,
            features=ResponseFeatures(delay_seconds=None),
            raw=dict(data) if isinstance(data, dict) else {},
        )
