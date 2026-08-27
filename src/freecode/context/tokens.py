"""
context.tokens - token budget helpers.

ApiFreeLLM uses a flat string; we approximate tokens as chars / chars_per_token
because we have no tokenizer for the free-tier model.
"""
from __future__ import annotations

from freecode.config.settings import ContextSettings


def estimate_tokens(text: str, chars_per_token: float = 4.0) -> int:
    if not text:
        return 0
    cpt = chars_per_token if chars_per_token > 0 else 4.0
    return max(1, int(len(text) / cpt))


def fits_budget(text: str, budget: int, chars_per_token: float = 4.0) -> bool:
    return estimate_tokens(text, chars_per_token) <= budget


def trim_to_budget(text: str, budget: int, chars_per_token: float = 4.0) -> str:
    """Hard-trim if over budget (keep head + tail with a marker)."""
    if fits_budget(text, budget, chars_per_token):
        return text
    max_chars = max(32, int(budget * chars_per_token))
    if len(text) <= max_chars:
        return text
    marker = "\n\n…[truncated]…\n\n"
    if max_chars <= len(marker) + 8:
        return text[:max_chars]
    head = max(4, int((max_chars - len(marker)) * 0.7))
    tail = max_chars - head - len(marker)
    if tail < 4:
        return text[:max_chars]
    return text[:head] + marker + text[-tail:]


def budget_from_settings(settings: ContextSettings) -> int:
    # Leave a little headroom under the window for the model reply.
    return min(settings.token_budget, max(512, settings.context_window - 2000))
