"""
llm.client - async HTTP client for ApiFreeLLM free-tier chat.

Owns transport only: build request, POST, map status codes to domain
errors, parse the success body into ChatResponse.

Does NOT own:
  - scheduling / cooldown (ph-04)
  - response repair / agent protocol (ph-05)
  - agent state or TUI (ph-06+)

Retries are deliberately absent. Docs require handling 429/5xx without
retry storms; the Scheduler decides when the next attempt is allowed.
"""
from __future__ import annotations

from typing import Any, Mapping

import httpx

from freecode.config.logging import get_logger
from freecode.config.settings import LLMSettings
from freecode.domain.errors import (
    LLMAuthError,
    LLMBadRequestError,
    LLMForbiddenError,
    LLMRateLimitError,
    LLMResponseError,
    LLMServerError,
    LLMTransportError,
)
from freecode.llm.request import ChatRequest
from freecode.llm.response import ChatResponse

log = get_logger(__name__)

DEFAULT_TIMEOUT = 60.0


def _parse_retry_after(headers: httpx.Headers) -> float | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except Exception:
        text = (response.text or "").strip()
        return text[:500] if text else f"HTTP {response.status_code}"
    if isinstance(body, Mapping):
        for key in ("error", "message", "detail"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, Mapping) and isinstance(val.get("message"), str):
                return val["message"].strip()
    return f"HTTP {response.status_code}"



def _is_daily_quota_error(message: str) -> bool:
    """Detect community daily quota messages (50 req / 24h per key)."""
    low = (message or "").lower()
    needles = (
        "daily request limit",
        "daily limit",
        "50 requests",
        "24h",
        "24 h",
        "quota exceeded",
        "community daily",
    )
    return any(n in low for n in needles)


class ApiFreeLLMClient:
    """
    Thin async client for POST /api/v1/chat.

    Usage:
        async with ApiFreeLLMClient(settings) as client:
            response = await client.send("hello")
    """

    def __init__(
        self,
        settings: LLMSettings | None = None,
        *,
        endpoint: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        s = settings or LLMSettings()

        self._endpoint = endpoint if endpoint is not None else s.endpoint
        self._model = model if model is not None else s.model
        self._timeout = (
            timeout_seconds if timeout_seconds is not None else s.timeout_seconds
        )

        self._api_keys = (
            s.api_keys
            if s.api_keys
            else ((api_key if api_key is not None else s.api_key),)
        )

        self._api_keys = tuple(k for k in self._api_keys if k)

        self._key_index = 0
        self._exhausted_keys: set[int] = set()

        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def model(self) -> str:
        return self._model

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_keys)

    async def __aenter__(self) -> ApiFreeLLMClient:
        await self._ensure_client()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers: dict[str, str] = {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }

            kwargs: dict[str, Any] = {
                "timeout": httpx.Timeout(self._timeout),
                "headers": headers,
            }

            if self._transport is not None:
                kwargs["transport"] = self._transport

            self._client = httpx.AsyncClient(**kwargs)

        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def send(
        self,
        message: str,
        *,
        model: str | None = None,
    ) -> ChatResponse:
        """
        Send a single flat-string message and return the normalized response.

        Raises LLMError subclasses on auth/rate-limit/server/transport failure.
        Does not retry.
        """
        request = ChatRequest(
            message=message,
            model=model if model is not None else self._model,
        )
        return await self.send_request(request)

    async def send_request(self, request: ChatRequest) -> ChatResponse:
        client = await self._ensure_client()
        body = request.to_body()

        # No keys: still POST (mock/tests / open endpoints). Live community needs a key.
        if not self._api_keys:
            try:
                response = await client.post(self._endpoint, json=body)
            except httpx.TimeoutException as exc:
                raise LLMTransportError(
                    f"Request timed out after {self._timeout:.0f}s"
                ) from exc
            except httpx.RequestError as exc:
                raise LLMTransportError(
                    f"ApiFreeLLM transport error: {exc}"
                ) from exc
            return self._map_response(response)

        attempted_keys: set[int] = set()

        while len(attempted_keys) < len(self._api_keys):
            key_index = self._key_index

            if key_index in self._exhausted_keys:
                if not self._rotate_key():
                    break
                key_index = self._key_index

            if key_index in attempted_keys:
                break

            attempted_keys.add(key_index)

            api_key = self._api_keys[key_index]

            log.debug(
                "POST %s model=%s message_chars=%d api_key=%d/%d",
                self._endpoint,
                request.model,
                len(request.message),
                key_index + 1,
                len(self._api_keys),
            )

            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {api_key}",
            }

            try:
                response = await client.post(
                    self._endpoint,
                    json=body,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                raise LLMTransportError(
                    f"Request timed out after {self._timeout:.0f}s"
                ) from exc
            except httpx.RequestError as exc:
                raise LLMTransportError(
                    f"ApiFreeLLM transport error: {exc}"
                ) from exc

            # Daily quota can arrive as 429 *or* HTTP 200 + success:false.
            if response.status_code == 200:
                try:
                    data = response.json()
                except Exception:
                    data = None
                if isinstance(data, dict) and data.get("success") is False:
                    err = data.get("error") or data.get("message") or "success=false"
                    if not isinstance(err, str):
                        err = str(err)
                    if _is_daily_quota_error(err):
                        self._exhausted_keys.add(key_index)
                        log.warning(
                            "ApiFreeLLM key %d/%d daily quota (200): %s",
                            key_index + 1,
                            len(self._api_keys),
                            err[:120],
                        )
                        if self._rotate_key():
                            continue
                        raise LLMRateLimitError(
                            "All configured ApiFreeLLM API keys have reached their "
                            "daily community limit (50 requests / 24h per key). "
                            "Add more keys via FREECODE_API_KEY_2, _3, … or wait.",
                            status_code=429,
                        )
                return self._map_response(response)

            if response.status_code != 429:
                return self._map_response(response)

            message = _error_message(response)

            if not _is_daily_quota_error(message):
                # Normal inter-request 429 → Scheduler cooldown.
                return self._map_response(response)

            self._exhausted_keys.add(key_index)
            log.warning(
                "ApiFreeLLM key %d/%d reached daily community quota",
                key_index + 1,
                len(self._api_keys),
            )
            if not self._rotate_key():
                return self._map_response(response)
            continue

        raise LLMRateLimitError(
            "All configured ApiFreeLLM API keys have reached their daily "
            "Community request limit.",
            status_code=429,
            retry_after_seconds=None,
        )

    def _map_response(self, response: httpx.Response) -> ChatResponse:
        status = response.status_code
        if status == 200:
            return self._parse_success(response)
        message = _error_message(response)
        if status == 400:
            raise LLMBadRequestError(message, status_code=400)
        if status == 401:
            raise LLMAuthError(message, status_code=401)
        if status == 403:
            raise LLMForbiddenError(message, status_code=403)
        if status == 429:
            raise LLMRateLimitError(
                message,
                status_code=429,
                retry_after_seconds=_parse_retry_after(response.headers),
            )
        if 500 <= status <= 599:
            raise LLMServerError(message, status_code=status)
        raise LLMServerError(
            f"Unexpected HTTP {status}: {message}",
            status_code=status,
        )

    def _parse_success(self, response: httpx.Response) -> ChatResponse:
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "ApiFreeLLM returned non-JSON success body",
                status_code=200,
            ) from exc
        if not isinstance(data, dict):
            raise LLMResponseError(
                "ApiFreeLLM success body must be a JSON object",
                status_code=200,
            )
        # Some error payloads still arrive with HTTP 200 + success:false.
        if data.get("success") is False:
            err = data.get("error") or data.get("message") or "success=false"
            if not isinstance(err, str):
                err = str(err)
            low = err.lower()
            # ApiFreeLLM free tier often returns success:false with e.g.
            # "Community request timed out" — that is NOT the daily 50/24h quota.
            if (
                "timed out" in low
                or "timeout" in low
                or "request timed out" in low
            ):
                raise LLMTransportError(
                    f"{err} — ApiFreeLLM free-tier community requests often time out "
                    f"under load or on long prompts. Wait for the cooldown bar, then "
                    f"retry with a shorter message (or use `/provider groq`).",
                    status_code=200,
                )
            raise LLMResponseError(err, status_code=200)
        parsed = ChatResponse.from_mapping(data)
        log.debug(
            "ApiFreeLLM ok chars=%d delay=%s tier=%s",
            len(parsed.text),
            parsed.delay_seconds,
            parsed.tier,
        )
        return parsed

    @property
    def api_key_count(self) -> int:
        return len(self._api_keys)


    @property
    def current_key_index(self) -> int:
        return self._key_index


    def _current_api_key(self) -> str | None:
        if not self._api_keys:
            return None

        if self._key_index in self._exhausted_keys:
            self._rotate_key()

        if self._key_index >= len(self._api_keys):
            return None

        return self._api_keys[self._key_index]


    def _rotate_key(self) -> bool:
        if not self._api_keys:
            return False

        start = self._key_index

        for offset in range(1, len(self._api_keys) + 1):
            index = (start + offset) % len(self._api_keys)

            if index not in self._exhausted_keys:
                old_index = self._key_index
                self._key_index = index

                log.warning(
                    "ApiFreeLLM API key exhausted: switching key %d -> %d",
                    old_index + 1,
                    index + 1,
                )

                return True

        return False