from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical

from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats
from freecode.tui.widgets.input import FreeCodeInput
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

    #activity {
        width: 1fr;
        height: auto;
        padding: 0 2;
    }

    #cooldown {
        width: 1fr;
        height: auto;
        padding: 0 2;
    }

    #footer {
        width: 1fr;
        height: auto;
        padding: 0 2 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        yield LandingScreen(id="landing")

        yield Vertical(
            TranscriptPane(id="transcript-pane"),
            id="conversation",
        )

        yield Vertical(
            FreeCodeInput(
                id="chat-input",
                placeholder="Type a message...",
            ),
            ActivityIndicator(id="activity"),
            CooldownBar(id="cooldown"),
            FooterStats(id="footer"),
            id="composer",
        )

    def on_mount(self) -> None:
        self.query_one("#conversation").display = False
        self.query_one("#composer").display = False

    def start_conversation(self) -> None:
        self.query_one("#landing").display = False
        self.query_one("#conversation").display = True
        self.query_one("#composer").display = True

        self.query_one("#chat-input", FreeCodeInput).focus()