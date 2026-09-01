"""
llm.providers.router - try providers in order; failover on daily/quota errors.
"""
from __future__ import annotations

from freecode.config.logging import get_logger
from freecode.domain.errors import LLMError, LLMRateLimitError
from freecode.llm.client import _is_daily_quota_error
from freecode.llm.response import ChatResponse

log = get_logger(__name__)


class ProviderRouter:
    """
    Ordered list of chat providers. On daily-quota / key-exhaustion style
    errors, advances to the next provider. Other errors propagate.
    """

    def __init__(self, providers: list) -> None:
        self._providers = [p for p in providers if getattr(p, "has_api_key", False) or True]
        # Prefer providers that actually have keys
        with_keys = [p for p in providers if getattr(p, "has_api_key", False)]
        self._providers = with_keys if with_keys else list(providers)
        self._index = 0
        self._exhausted: set[int] = set()

    @property
    def active_name(self) -> str:
        if not self._providers:
            return "none"
        return getattr(self._providers[self._index], "name", "unknown")

    @property
    def has_api_key(self) -> bool:
        return any(getattr(p, "has_api_key", False) for p in self._providers)

    def force(self, name: str) -> bool:
        """Switch active provider. Returns False if name unknown or no key."""
        name = (name or "").strip().lower()
        for i, p in enumerate(self._providers):
            if getattr(p, "name", "") == name:
                if not getattr(p, "has_api_key", False):
                    log.warning("force %s failed: no API key configured", name)
                    return False
                self._index = i
                # Fresh start on this provider (user explicitly chose it)
                self._exhausted.discard(i)
                log.info("provider forced -> %s", name)
                return True
        return False

    def names(self) -> list[str]:
        return [getattr(p, "name", "?") for p in self._providers]

    def provider_status(self) -> list[tuple[str, bool, bool]]:
        """(name, has_key, is_active) for UI."""
        out = []
        for i, p in enumerate(self._providers):
            out.append(
                (
                    getattr(p, "name", "?"),
                    bool(getattr(p, "has_api_key", False)),
                    i == self._index,
                )
            )
        return out

    def set_model(self, model: str) -> bool:
        """Set model on the active provider if it supports it."""
        p = self._providers[self._index]
        setter = getattr(p, "set_model", None)
        if callable(setter):
            return bool(setter(model))
        return False

    def active_model(self) -> str | None:
        p = self._providers[self._index]
        return getattr(p, "model", None) or getattr(p, "_model", None)

    async def send(self, message: str, *, model: str | None = None) -> ChatResponse:
        if not self._providers:
            raise LLMRateLimitError("No LLM providers configured.", status_code=429)

        attempted: set[int] = set()
        last_err: Exception | None = None

        while len(attempted) < len(self._providers):
            if self._index in self._exhausted:
                if not self._advance():
                    break
            if self._index in attempted:
                break
            attempted.add(self._index)
            provider = self._providers[self._index]
            log.debug("provider=%s attempt", getattr(provider, "name", "?"))
            try:
                async with provider:  # type: ignore[attr-defined]
                    return await provider.send(message, model=model)
            except LLMRateLimitError as exc:
                last_err = exc
                msg = str(exc)
                if _is_daily_quota_error(msg) or "exhausted" in msg.lower() or "quota" in msg.lower():
                    self._exhausted.add(self._index)
                    log.warning("provider %s exhausted: %s", provider.name, msg[:120])
                    if self._advance():
                        continue
                raise
            except LLMError:
                raise

        if last_err:
            raise last_err
        raise LLMRateLimitError("All LLM providers exhausted.", status_code=429)

    def _advance(self) -> bool:
        start = self._index
        for offset in range(1, len(self._providers) + 1):
            idx = (start + offset) % len(self._providers)
            if idx not in self._exhausted:
                self._index = idx
                log.warning("switching provider -> %s", self._providers[idx].name)
                return True
        return False

    async def aclose(self) -> None:
        for p in self._providers:
            close = getattr(p, "aclose", None)
            if close:
                try:
                    await close()
                except Exception:
                    pass
