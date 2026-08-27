"""
tui.widgets.input - FreeCode message composers.

- FreeCodeInput: single-line (landing screen)
- FreeCodeComposer: multi-line TextArea (conversation)

Submit: Ctrl+Enter (Enter inserts a newline for paragraphs).
Paste: handled by Textual/TextArea (bracketed paste in supporting terminals).
"""
from __future__ import annotations

from textual import on
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input, TextArea


class MessageSubmitted(Message):
    """Posted when the user submits a composer (or landing) message."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class FreeCodeInput(Input):
    """Single-line input used on the landing screen."""

    DEFAULT_CSS = """
    FreeCodeInput {
        width: 1fr;
        height: 3;
        border: round $panel;
        background: $surface;
        color: $foreground;
        padding: 0 1;
    }

    FreeCodeInput:focus {
        border: round $accent;
    }
    """

    def __init__(
        self,
        *,
        placeholder: str = "Type a message...",
        **kwargs,
    ) -> None:
        super().__init__(placeholder=placeholder, **kwargs)

    @on(Input.Submitted)
    def _forward_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(MessageSubmitted(text))
        event.stop()


class FreeCodeComposer(TextArea):
    """
    Multi-line message box for the conversation view.

    Enter     → new line (paragraphs)
    Ctrl+Enter → send
    Paste works via the terminal's bracketed-paste support.
    """

    BINDINGS = [
        Binding("ctrl+enter", "submit", "Send", priority=True, show=True),
        Binding("ctrl+j", "submit", "Send", priority=True, show=False),
    ]

    DEFAULT_CSS = """
    FreeCodeComposer {
        width: 1fr;
        height: 7;
        min-height: 5;
        max-height: 14;
        border: round $panel;
        background: $surface;
        color: $foreground;
        padding: 0 1;
    }

    FreeCodeComposer:focus {
        border: round $accent;
    }
    """

    def __init__(
        self,
        *,
        id: str | None = None,
        placeholder: str = "Message… (Enter = newline, Ctrl+Enter = send)",
        **kwargs,
    ) -> None:
        # soft_wrap helps long lines; show line numbers off for a chat feel
        super().__init__(
            id=id,
            soft_wrap=True,
            show_line_numbers=False,
            tab_behavior="indent",
            **kwargs,
        )
        self._placeholder = placeholder

    def on_mount(self) -> None:
        # TextArea has no built-in placeholder; tooltip helps discover submit.
        self.tooltip = self._placeholder

    def action_submit(self) -> None:
        text = self.text.strip()
        if not text:
            return
        self.post_message(MessageSubmitted(text))
        self.clear()
