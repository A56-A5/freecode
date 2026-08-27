"""
tui.layout - the main FreeCode TUI layout.

The landing screen is shown initially. After the first submitted
message, the landing screen is replaced by the normal conversation
layout.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical

from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats
from freecode.tui.widgets.input import FreeCodeComposer, FreeCodeInput
from freecode.tui.widgets.landing import LandingScreen


class MainLayout(Vertical):
    DEFAULT_CSS = """
    MainLayout {
        width: 1fr;
        height: 1fr;
        background: $background;
    }

    #landing {
        width: 1fr;
        height: 1fr;
    }

    #conversation {
        width: 1fr;
        height: 1fr;
    }

    #composer {
        width: 1fr;
        height: auto;
        padding: 0 2 1 2;
    }

    #chat-input {
        width: 1fr;
    }

    #activity-indicator {
        width: 1fr;
        height: auto;
        padding: 0 2;
    }

    #cooldown-bar {
        width: 1fr;
        height: auto;
        padding: 0 2;
    }

    #footer-stats {
        width: 1fr;
        height: auto;
        padding: 0 2 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        # Initial landing page.
        yield LandingScreen(id="landing")

        # Normal conversation area.
        yield Vertical(
            TranscriptPane(id="transcript-pane"),
            id="conversation",
        )

        # Bottom composer and status widgets.
        yield Vertical(
            FreeCodeComposer(
                id="chat-input",
            ),
            ActivityIndicator(id="activity-indicator"),
            CooldownBar(id="cooldown-bar"),
            FooterStats(id="footer-stats"),
            id="composer",
        )

    def on_mount(self) -> None:
        # Start in landing mode.
        self.query_one("#conversation").display = False
        self.query_one("#composer").display = False

        # Focus is deliberately owned by FreeCodeApp after the complete
        # application tree has mounted.
        self.query_one("#landing-input").focus()

    def start_conversation(self) -> None:
        """
        Switch from the landing screen to the normal conversation UI.
        """
        self.query_one("#landing").display = False
        self.query_one("#conversation").display = True
        self.query_one("#composer").display = True
        self.query_one("#chat-input").focus()