from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static

from freecode.tui.widgets.input import FreeCodeComposer


FREECODE_ASCII = r"""
 ███████╗██████╗ ███████╗███████╗ ██████╗ █████╗ ██████╗ ███████╗
 ██╔════╝██╔══██╗██╔════╝██╔════╝██╔════╝██╔══██╗██╔══██╗██╔════╝
 █████╗  ██████╔╝█████╗  █████╗  ██║     ██║  ██║██║  ██║█████╗  
 ██╔══╝  ██╔══██╗██╔══╝  ██╔══╝  ██║     ██║  ██║██║  ██║██╔══╝  
 ██║     ██║  ██║███████╗███████╗╚██████╗ █████╔╝██████╔╝███████╗
 ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚════╝ ╚═════╝ ╚══════╝
"""


class LandingScreen(Vertical):
    DEFAULT_CSS = """
    LandingScreen {
        width: 1fr;
        height: 1fr;
        align: center middle;
        background: $background;
    }

    #landing-content {
        width: 1fr;
        height: auto;
        align: center middle;
    }

    #freecode-ascii {
        width: 1fr;
        height: auto;
        content-align: center middle;
        text-align: center;
        color: $foreground;
        text-style: bold;
        margin-bottom: 2;
    }

    #landing-input-row {
        width: 1fr;
        height: auto;
        align: center middle;
    }

    #landing-input {
        width: 70%;
        max-width: 90;
        min-width: 40;
        height: auto;
        min-height: 3;
        max-height: 12;
        border: solid $panel;
        background: $surface;
    }

    #landing-hint {
        width: 1fr;
        height: auto;
        content-align: center middle;
        text-align: center;
        color: $secondary;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(FREECODE_ASCII, id="freecode-ascii"),
            Horizontal(
                FreeCodeComposer(id="landing-input"),
                id="landing-input-row",
            ),
            Static(
                "Enter = newline · Ctrl+Enter = send",
                id="landing-hint",
            ),
            id="landing-content",
        )
