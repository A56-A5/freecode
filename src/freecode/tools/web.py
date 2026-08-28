"""
tools.web - fetch public web pages for lookup (always approval-gated upstream).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import quote_plus

import httpx

from freecode.tools.results import ToolResult

MAX_CHARS = 12_000
DEFAULT_TIMEOUT = 20.0


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = data.strip()
        if text:
            self._chunks.append(text)

    def text(self) -> str:
        return "\n".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        return re.sub(r"<[^>]+>", " ", html)
    return parser.text()


def fetch_url(url: str, *, timeout: float = DEFAULT_TIMEOUT, max_chars: int = MAX_CHARS) -> ToolResult:
    u = (url or "").strip()
    if not u:
        return ToolResult(tool="web_fetch", status="error", error="empty url")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(u, headers={"User-Agent": "FreeCode/0.1 (agent lookup; +https://github.com/A56-A5/freecode)"})
        if resp.status_code >= 400:
            return ToolResult(
                tool="web_fetch",
                status="error",
                error=f"HTTP {resp.status_code} for {u}",
                data={"url": u},
            )
        ctype = (resp.headers.get("content-type") or "").lower()
        if "html" in ctype or u.endswith((".html", ".htm")) or "<html" in resp.text[:200].lower():
            text = _html_to_text(resp.text)
        else:
            text = resp.text
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        truncated = len(text) > max_chars
        if truncated:
            text = text[:max_chars] + "\n…[truncated]"
        return ToolResult(
            tool="web_fetch",
            status="ok",
            output=text,
            data={"url": str(resp.url), "chars": len(text), "truncated": truncated},
            mutating=False,
        )
    except httpx.TimeoutException:
        return ToolResult(tool="web_fetch", status="error", error=f"timeout fetching {u}")
    except Exception as exc:
        return ToolResult(tool="web_fetch", status="error", error=str(exc))


def web_search_duckduckgo(query: str, *, timeout: float = DEFAULT_TIMEOUT) -> ToolResult:
    """Lightweight HTML search via DuckDuckGo HTML endpoint (no API key)."""
    q = (query or "").strip()
    if not q:
        return ToolResult(tool="web_search", status="error", error="empty query")
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(q)}"
    result = fetch_url(url, timeout=timeout, max_chars=8000)
    if not result.ok:
        return ToolResult(tool="web_search", status="error", error=result.error or "search failed")
    return ToolResult(
        tool="web_search",
        status="ok",
        output=f"Search: {q}\n\n{result.output}",
        data={"query": q, "url": url},
        mutating=False,
    )
