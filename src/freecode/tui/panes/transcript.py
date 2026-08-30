"""
tui.panes.transcript - the unified conversation stream.

Visual language of terminal coding agents (Claude Code / OpenCode style):

    › user prompt

    ● assistant response (Markdown-rendered, optionally typed out)

ApiFreeLLM free tier does not stream tokens; we simulate a live typing
feel by revealing the full reply in small chunks after it arrives.
"""
from __future__ import annotations

import asyncio
import re

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Markdown, Static

_FENCE_RE = re.compile(r"```(?:[\w+-]*)\n(.*?)```", re.DOTALL)


def extract_fenced_blocks(text: str) -> list[str]:
    """Return bodies of markdown fenced code blocks (no fences)."""
    return [m.group(1).rstrip("\n") for m in _FENCE_RE.finditer(text or "")]


class TranscriptPane(VerticalScroll):
    """Scrollable conversation transcript."""

    DEFAULT_CSS = """
    TranscriptPane {
        width: 1fr;
        height: 1fr;
        background: $background;
        scrollbar-color: $accent;
        scrollbar-background: $background;
        scrollbar-corner-color: $background;
        padding: 0 1;
    }

    .message {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
    }

    .user-message {
        width: 1fr;
        height: auto;
        margin: 1 0;
        padding: 0 1;
        background: $surface;
        border-left: thick $accent;
        color: $foreground;
    }

    .assistant-row {
        width: 1fr;
        height: auto;
        margin: 0 0 1 0;
        padding: 0 0 0 0;
    }

    .assistant-marker {
        width: 3;
        height: auto;
        padding: 0 1 0 0;
        color: $accent;
        text-style: bold;
    }

    .assistant-body {
        width: 1fr;
        height: auto;
        padding: 0 1 0 0;
    }

    .assistant-body Markdown {
        width: 1fr;
        height: auto;
        margin: 0;
        padding: 0;
        background: transparent;
        color: $foreground;
    }

    .assistant-body Markdown .code_inline {
        background: $panel;
    }

    .error-message {
        width: 1fr;
        height: auto;
        margin: 1 0;
        padding: 0 1;
        color: $error;
        border-left: thick $error;
    }
    """

    def compose(self) -> ComposeResult:
        yield from ()

    def clear(self) -> None:
        """Remove all messages (used on session switch)."""
        for child in list(self.children):
            child.remove()

    def clear_view(self) -> None:
        """Clear the visible transcript only (session state unchanged)."""
        self.clear()

    def _remember_assistant(self, text: str) -> None:
        self._last_assistant_text = text or ""
        blocks = extract_fenced_blocks(text or "")
        if blocks:
            self._last_code_blocks = blocks
            self._last_code_block = blocks[-1]

    def last_assistant_text(self) -> str:
        return getattr(self, "_last_assistant_text", "") or ""

    def last_code_block(self) -> str:
        return getattr(self, "_last_code_block", "") or ""

    def write_user_message(self, text: str) -> None:
        """Render a user message with a left accent rail."""
        text = (text or "").rstrip()
        # Preserve paragraphs from multi-line composer.
        message = Static(
            f"› {text}",
            classes="message user-message",
        )
        self.mount(message)
        self.scroll_end(animate=False)

    def write_agent_message(self, text: str) -> None:
        """Mount a complete assistant reply (no typing animation)."""
        text = (text or "").rstrip() or "*(empty response)*"
        self._remember_assistant(text)
        md = Markdown(text)
        row = Horizontal(
            Static("●", classes="assistant-marker"),
            Vertical(md, classes="assistant-body"),
            classes="assistant-row message",
        )
        self.mount(row)
        self.scroll_end(animate=False)

    async def stream_agent_message(
        self,
        text: str,
        *,
        chars_per_tick: int = 6,
        tick_seconds: float = 0.018,
    ) -> None:
        """
        Reveal `text` progressively so replies feel generated live.

        The API still returns the full string at once; this is presentation
        only. Short replies appear almost immediately; long ones type out.
        """
        text = (text or "").rstrip() or "*(empty response)*"
        self._remember_assistant(text)
        md = Markdown("")
        row = Horizontal(
            Static("●", classes="assistant-marker"),
            Vertical(md, classes="assistant-body"),
            classes="assistant-row message",
        )
        await self.mount(row)
        self.scroll_end(animate=False)

        # Adaptive speed: don't spend forever on huge replies.
        n = len(text)
        if n > 4000:
            chars_per_tick = max(chars_per_tick, 24)
        elif n > 1500:
            chars_per_tick = max(chars_per_tick, 12)

        pos = 0
        while pos < n:
            pos = min(n, pos + chars_per_tick)
            # Prefer breaking on whitespace so words appear whole when possible.
            if pos < n and text[pos - 1] not in " \n\t":
                space = text.find(" ", pos)
                newline = text.find("\n", pos)
                candidates = [c for c in (space, newline) if c != -1 and c < pos + chars_per_tick * 2]
                if candidates:
                    pos = min(candidates) + 1
            chunk = text[:pos]
            md.update(chunk)
            self.scroll_end(animate=False)
            await asyncio.sleep(tick_seconds)

        md.update(text)
        self.scroll_end(animate=False)

    def write_error_message(self, text: str) -> None:
        """Surface transport / rate-limit errors distinctly."""
        text = (text or "").rstrip()
        message = Static(
            f"⚠ {text}",
            classes="message error-message",
        )
        self.mount(message)
        self.scroll_end(animate=False)

    async def stream_mock_reply(self, prompt: str) -> None:
        """Offline demo reply with the same typing feel as live mode."""
        prompt_lower = prompt.lower()

        if "hello" in prompt_lower or "hi" in prompt_lower:
            reply = (
                "Hello! Mock mode is active (no API key).\n\n"
                "Set `FREECODE_API_KEY` to talk to ApiFreeLLM.\n\n"
                "Try a multi-line message with **Ctrl+Enter** to send."
            )
        elif "help" in prompt_lower:
            reply = (
                "Here's the current mock command set:\n\n"
                "- **help** — show this message\n"
                "- **test** — generate a longer response\n"
                "- **hello** — generate a greeting\n\n"
                "Composer: **Enter** = newline, **Ctrl+Enter** = send."
            )
        elif "test" in prompt_lower:
            reply = (
                "Running the UI test fixture...\n\n"
                "- Input submission\n"
                "- Multi-line composer\n"
                "- Markdown + typing reveal\n"
                "- Automatic scrolling\n\n"
                "```python\n"
                "def ok() -> bool:\n"
                "    return True\n"
                "```\n"
            )
        else:
            reply = (
                f"I received:\n\n"
                f"> {prompt}\n\n"
                "This is a **mock** FreeCode response (no API key).\n\n"
                "Composer: **Enter** = newline, **Ctrl+Enter** = send."
            )

        await self.stream_agent_message(reply)
