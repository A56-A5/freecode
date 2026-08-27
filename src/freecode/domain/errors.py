"""
domain.errors - shared exception types.

LLM transport errors land here in ph-03 so the client, scheduler, and
agent can share a stable vocabulary without importing httpx.
"""
from __future__ import annotations


class FreeCodeError(Exception):
    """Base class for all FreeCode application errors."""


class LLMError(FreeCodeError):
    """Base class for ApiFreeLLM client failures."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMAuthError(LLMError):
    """Missing or invalid API key (HTTP 401)."""


class LLMForbiddenError(LLMError):
    """Service class / network not eligible (HTTP 403)."""


class LLMBadRequestError(LLMError):
    """Invalid request body or parameters (HTTP 400)."""


class LLMRateLimitError(LLMError):
    """Rate or usage boundary (HTTP 429).

    `retry_after_seconds` is taken from Retry-After when present, else None.
    The Scheduler (ph-04) owns backoff timing; the client does not retry.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code)
        self.retry_after_seconds = retry_after_seconds


class LLMServerError(LLMError):
    """Upstream 5xx failure."""


class LLMTransportError(LLMError):
    """Network / timeout / connection failure before a usable HTTP response."""


class LLMResponseError(LLMError):
    """HTTP 200 but body could not be parsed into the expected shape."""
