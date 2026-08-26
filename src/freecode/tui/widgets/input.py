"""
tui.widgets.input - FreeCode's message composer.
"""

from __future__ import annotations

from textual.widgets import Input


class FreeCodeInput(Input):
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
    ):
        super().__init__(
            placeholder=placeholder,
            **kwargs,
        )