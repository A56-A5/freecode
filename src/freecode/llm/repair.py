"""
llm.repair - extract and validate structured agent JSON from model text.

Pipeline:
  raw text -> JSON extraction -> strict parse -> validation -> AgentResponse
           on failure -> recover "message" field from broken JSON
           on total failure -> plain-text fallback (no extra LLM call)

Handles: pure JSON, markdown fences, prose wrappers, truncated braces,
unescaped newlines inside JSON strings (common on long free-tier replies).
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

# Recover a JSON string value for "message" even when the rest is broken.
_MESSAGE_KEY_RE = re.compile(r'"message"\s*:\s*"', re.DOTALL)


def extract_json_candidates(text: str) -> list[str]:
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

    # Attempt to close truncated objects (long replies cut mid-JSON)
    if stripped.startswith("{") and not stripped.endswith("}"):
        for suffix in ('"}', '"], "status": "continue"}', '"status": "continue"}', "}"):
            _add(stripped + suffix)

    return candidates


def _first_balanced_object(text: str) -> str | None:
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
        # Try raw_decode from first brace
        try:
            start = candidate.find("{")
            if start < 0:
                return None
            data, _ = json.JSONDecoder().raw_decode(candidate[start:])
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict):
        return data
    return None


def _looks_like_agent_payload(data: dict[str, Any]) -> bool:
    keys = set(data.keys())
    contract = {"message", "actions", "status", "context_update"}
    return bool(keys & contract)


def _unescape_json_string(body: str) -> str:
    """Interpret JSON string escape sequences in an extracted fragment."""
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            if nxt == "n":
                out.append("\n")
            elif nxt == "t":
                out.append("\t")
            elif nxt == "r":
                out.append("\r")
            elif nxt == '"':
                out.append('"')
            elif nxt == "\\":
                out.append("\\")
            elif nxt == "/":
                out.append("/")
            elif nxt == "u" and i + 5 < len(body):
                try:
                    out.append(chr(int(body[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    out.append(nxt)
            else:
                out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_message_field(text: str) -> str | None:
    """
    Best-effort pull of the agent `message` string from messy model output.

    Handles:
    - valid JSON (via loads)
    - truncated JSON
    - unescaped raw newlines inside the message value (invalid JSON)
    """
    if not text:
        return None

    # Fast path: valid JSON
    data = _try_load(text.strip())
    if data and isinstance(data.get("message"), str):
        return data["message"]

    # Scan for "message": " ... "
    m = _MESSAGE_KEY_RE.search(text)
    if not m:
        return None

    i = m.end()
    # If the model put a real newline right after the opening quote and
    # continued without escaping, read until a line that looks like the
    # next JSON key or closing brace.
    raw_chars: list[str] = []
    escape = False
    while i < len(text):
        ch = text[i]
        if escape:
            raw_chars.append("\\")
            raw_chars.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\":
            escape = True
            i += 1
            continue
        if ch == '"':
            # End of string — unless this is invalid JSON with internal quotes
            # Peek: if next non-ws is : or , or } treat as end
            j = i + 1
            while j < len(text) and text[j] in " \t\r\n":
                j += 1
            if j >= len(text) or text[j] in ",}":
                break
            # Otherwise include the quote as content (broken JSON)
            raw_chars.append(ch)
            i += 1
            continue
        # Unescaped control newline inside string → keep as real newline
        raw_chars.append(ch)
        i += 1

    if not raw_chars:
        return None
    return _unescape_json_string("".join(raw_chars)).strip()


def _normalize_message(msg: str) -> str:
    # If the whole message still looks like a JSON wrapper, peel it.
    stripped = msg.strip()
    if stripped.startswith("{") and '"message"' in stripped:
        inner = extract_message_field(stripped)
        if inner and inner != msg:
            return inner
    return msg


def repair_response(text: str) -> AgentResponse:
    """
    Turn raw model text into an AgentResponse.

    Never raises for ordinary bad model output — degrades gracefully.
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
            msg = _normalize_message(parsed.message)
            if msg != parsed.message:
                parsed = AgentResponse(
                    message=msg,
                    actions=parsed.actions,
                    context_update=parsed.context_update,
                    status=parsed.status,
                    fallback=False,
                    raw_text=text,
                )
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

    # Recover message from broken / truncated JSON before plain fallback
    recovered = extract_message_field(text)
    if recovered:
        log.debug("recovered message field from broken JSON (%d chars)", len(recovered))
        return AgentResponse(
            message=_normalize_message(recovered),
            actions=(),
            status="continue",
            fallback=False,
            raw_text=text,
        )

    if last_error is not None:
        log.debug("falling back to plain text after validation errors: %s", last_error)
    else:
        log.debug("falling back to plain text (no JSON candidates)")

    # Avoid showing raw JSON blob as the user-visible reply when possible
    stripped = text.strip()
    if stripped.startswith("{") and '"message"' in stripped:
        recovered = extract_message_field(stripped)
        if recovered:
            return AgentResponse(
                message=recovered,
                actions=(),
                status="continue",
                fallback=False,
                raw_text=text,
            )

    return AgentResponse.plain_text_fallback(text)


def repair_chat_text(text: str) -> AgentResponse:
    return repair_response(text)
