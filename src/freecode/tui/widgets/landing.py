from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
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
        width: 90%;
        height: auto;
        align: center middle;
    }

    #freecode-ascii {
        width: auto;
        height: auto;
        color: $accent;
        text-style: bold;
        margin-bottom: 2;
    }

    #landing-input {
        width: 70;
        max-width: 90%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static(FREECODE_ASCII, id="freecode-ascii"),
            FreeCodeInput(
                id="chat-input",
                placeholder="Ask FreeCode anything...",
            ),
            id="landing-content",
        )
