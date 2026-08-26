"""
tui.widgets.input - the message input at the bottom of the screen.

Thin wrapper around Textual's Input so later phases (history recall,
slash-commands, approval-prompt mode) can extend it without touching the
layout that composes it.
"""
from __future__ import annotations

from textual.widgets import Input


class FreeCodeInput(Input):
    def __init__(self, *, placeholder: str = "Type a message...", **kwargs):
        super().__init__(placeholder=placeholder, **kwargs)
