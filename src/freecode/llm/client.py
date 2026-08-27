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
        self._api_key = api_key if api_key is not None else s.api_key
        self._timeout = (
            timeout_seconds if timeout_seconds is not None else s.timeout_seconds
        )
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
        return bool(self._api_key)

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
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
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
        log.debug(
            "POST %s model=%s message_chars=%d",
            self._endpoint,
            request.model,
            len(request.message),
        )
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = await client.post(self._endpoint, json=body)
                break
            except httpx.TimeoutException as exc:
                last_exc = exc
                log.warning(
                    "ApiFreeLLM timeout after %.0fs (attempt %d/2)",
                    self._timeout,
                    attempt + 1,
                )
                if attempt == 0:
                    continue
                raise LLMTransportError(
                    f"Request timed out after {self._timeout:.0f}s "
                    f"(free-tier community limit — try a shorter ask, then retry)."
                ) from exc
            except httpx.RequestError as exc:
                raise LLMTransportError(
                    f"ApiFreeLLM transport error: {exc}"
                ) from exc
        else:
            raise LLMTransportError(
                f"Request timed out after {self._timeout:.0f}s"
            ) from last_exc

        return self._map_response(response)

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
            if "timed out" in low or "timeout" in low or "community" in low:
                raise LLMTransportError(
                    f"{err} — free-tier community requests can time out on long "
                    f"generations; try a shorter prompt or wait for cooldown and retry.",
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
