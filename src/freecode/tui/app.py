"""
tui.app - the FreeCode Textual application.

ph-01 scope: real, running TUI with the new unified-transcript layout,
a working chat input, and the configurable theme registered. No agent,
LLM, scheduler, or MCP behind it yet (ph-03 through ph-07) - the
activity indicator and cooldown bar are fully functional widgets but
nothing drives them until the Scheduler (ph-04) and Agent Core (ph-06)
exist.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input

from freecode.tui.layout import MainLayout
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import APP_TITLE, build_theme


class FreeCodeApp(App):
    CSS_PATH = Path(__file__).parent / "app.tcss"
    TITLE = APP_TITLE
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def compose(self) -> ComposeResult:
        yield MainLayout()

    def on_mount(self) -> None:
        theme = build_theme()
        self.register_theme(theme)
        self.theme = theme.name

        # The landing input is the only input visible at startup.
        self.query_one("#landing-input").focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()

        if not text:
            return

        layout = self.query_one(MainLayout)
        transcript = self.query_one(
            "#transcript-pane",
            TranscriptPane,
        )

        # First submission transitions:
        #
        #   landing screen
        #       ↓
        #   conversation screen
        #
        layout.start_conversation()

        # Add the user's prompt.
        transcript.write_user_message(text)

        # Clear the submitted input.
        event.input.value = ""

        # Temporary ph-01 response.
        #
        # This will eventually be replaced by Agent Core output.
        transcript.write_mock_reply(text)


def run_tui() -> int:
    """Launches the interactive TUI. Called from freecode.main.run()."""
    FreeCodeApp().run()
    return 0