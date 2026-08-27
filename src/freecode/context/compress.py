"""
context.compress - keep conversation under a token budget.
"""
from __future__ import annotations

from freecode.context.tokens import estimate_tokens
from freecode.domain.state import TurnRecord


def compress_history(
    history: list[TurnRecord],
    *,
    token_budget: int,
    chars_per_token: float = 4.0,
    prefer_recent: int = 8,
) -> list[TurnRecord]:
    """
    Keep the most recent turns that fit `token_budget`.

    Older turns are dropped first (not summarized in ph-08 — pure truncation).
    """
    if not history:
        return []
    # Always consider the tail first
    selected: list[TurnRecord] = []
    used = 0
    for turn in reversed(history):
        cost = estimate_tokens(f"{turn.role}: {turn.content}", chars_per_token)
        if selected and used + cost > token_budget:
            break
        if not selected and cost > token_budget:
            # Single huge turn — keep a trimmed marker via content slice later
            selected.append(turn)
            break
        selected.append(turn)
        used += cost
        if len(selected) >= prefer_recent * 2:
            # soft cap on number of turns
            pass
    selected.reverse()
    return selected


def format_history(turns: list[TurnRecord]) -> str:
    lines = []
    for turn in turns:
        prefix = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{prefix}: {turn.content}")
    return "\n".join(lines)
