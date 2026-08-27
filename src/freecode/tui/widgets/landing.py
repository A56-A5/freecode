from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Static

from freecode.tui.widgets.input import FreeCodeInput


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

        /*
         * IMPORTANT:
         * The logo is NOT the accent color.
         * Keep the green for interactive/status elements.
         */
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
        max-width: 80;
        min-width: 30;

        border: solid $panel;
        background: $surface;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(
                FREECODE_ASCII,
                id="freecode-ascii",
            ),
            Horizontal(
                FreeCodeInput(
                    id="landing-input",
                    placeholder="Ask FreeCode anything...",
                ),
                id="landing-input-row",
            ),
            id="landing-content",
        )