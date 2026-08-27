"""
llm.repair - extract and validate structured agent JSON from model text.

Pipeline:
  raw text -> JSON extraction -> strict parse -> validation -> AgentResponse
           on any failure -> plain-text fallback (no extra LLM call)

Handles: pure JSON, markdown fences, leading/trailing prose, truncated
braces (best-effort), and total garbage (fallback).
"""
from __future__ import annotations

import json
import re
from typing import Any

from freecode.config.logging import get_logger
from freecode.llm.protocol import AgentResponse

log = get_logger(__name__)

_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n?(.*?)```",
    re.DOTALL,
)


def extract_json_candidates(text: str) -> list[str]:
    """
    Ordered candidate strings that might be the structured payload.

    Preference: fenced blocks first, then the whole text, then the first
    balanced {...} slice found in the text.
    """
    if not text or not text.strip():
        return []

    candidates: list[str] = []
    seen: set[str] = set()

    def _add(s: str) -> None:
        s = s.strip()
        if s and s not in seen:
            seen.add(s)
            candidates.append(s)

    for match in _FENCE_RE.finditer(text):
        _add(match.group(1))

    stripped = text.strip()
    _add(stripped)

    brace_slice = _first_balanced_object(stripped)
    if brace_slice is not None:
        _add(brace_slice)

    return candidates


def _first_balanced_object(text: str) -> str | None:
    """Return the first top-level {...} substring, or None."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _try_load(candidate: str) -> dict[str, Any] | None:
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        return data
    return None


def _looks_like_agent_payload(data: dict[str, Any]) -> bool:
    """
    Heuristic: accept dicts that carry at least one contract key so we
    do not treat arbitrary JSON blobs as a full agent turn.
    """
    keys = set(data.keys())
    contract = {"message", "actions", "status", "context_update"}
    return bool(keys & contract)


def repair_response(text: str) -> AgentResponse:
    """
    Turn raw model text into an AgentResponse.

    Never raises for ordinary bad model output — degrades to plain text.
    Does not call the LLM again.
    """
    if text is None:
        text = ""
    if not isinstance(text, str):
        text = str(text)

    candidates = extract_json_candidates(text)
    last_error: Exception | None = None

    for candidate in candidates:
        data = _try_load(candidate)
        if data is None:
            continue
        if not _looks_like_agent_payload(data):
            continue
        try:
            parsed = AgentResponse.from_mapping(data, raw_text=text)
            log.debug(
                "repaired structured response actions=%d status=%s",
                len(parsed.actions),
                parsed.status,
            )
            return parsed
        except (ValueError, TypeError) as exc:
            last_error = exc
            log.debug("candidate failed validation: %s", exc)
            continue

    if last_error is not None:
        log.debug("falling back to plain text after validation errors: %s", last_error)
    else:
        log.debug("falling back to plain text (no JSON candidates)")

    return AgentResponse.plain_text_fallback(text)


def repair_chat_text(text: str) -> AgentResponse:
    """Alias for repair_response — explicit name for ChatResponse.text input."""
    return repair_response(text)
