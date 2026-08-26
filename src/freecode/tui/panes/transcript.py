"""
tui.panes.transcript - the unified conversation stream.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog


class TranscriptPane(Vertical):
    DEFAULT_CSS = """
    TranscriptPane {
        width: 1fr;
        height: 1fr;
        background: $background;
    }

    #transcript-log {
        width: 1fr;
        height: 1fr;

        background: $background;

        /* Textual defaults can make this look like a random blue scrollbar. */
        scrollbar-color: $accent;
        scrollbar-background: $background;
        scrollbar-corner-color: $background;

        /* Don't reserve scrollbar space when it isn't needed. */
        scrollbar-size-vertical: 1;
        scrollbar-size-horizontal: 0;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(
            id="transcript-log",
            wrap=True,
            markup=True,
            highlight=False,
            auto_scroll=True,
        )

    def write_user_message(self, text: str) -> None:
        log = self.query_one("#transcript-log", RichLog)
        log.write(f"[bold $accent]›[/bold $accent] {text}")

    def write_agent_message(self, text: str) -> None:
        log = self.query_one("#transcript-log", RichLog)
        log.write(f"[bold $accent]●[/bold $accent] {text}")

    def write_mock_reply(self, prompt: str) -> None:
        """
        Temporary ph-01 fixture.

        This intentionally does NOT pretend to be the future Agent Core.
        It only gives us enough conversation content to exercise the TUI.
        """
        prompt_lower = prompt.lower()

        if "hello" in prompt_lower or "hi" in prompt_lower:
            reply = (
                "Hey! I'm FreeCode.\n\n"
                "The conversation UI is working. Try sending another "
                "message to test the transcript and scrolling."
            )

        elif "help" in prompt_lower:
            reply = (
                "Here's the current mock command set:\n\n"
                "  help     show this message\n"
                "  test     generate a longer response\n"
                "  hello    generate a greeting\n\n"
                "Real agent behaviour will arrive in later phases."
            )

        elif "test" in prompt_lower:
            reply = (
                "Running the UI test fixture...\n\n"
                "✓ Input submission\n"
                "✓ User message rendering\n"
                "✓ Agent message rendering\n"
                "✓ Conversation transition\n"
                "✓ Transcript growth\n"
                "✓ Automatic scrolling\n\n"
                "This response is deliberately long enough to verify "
                "scroll behaviour."
            )

        else:
            reply = (
                f"I received:\n\n"
                f"  {prompt}\n\n"
                "This is a mock FreeCode response for ph-01. "
                "The real reasoning loop will eventually go through "
                "the Agent Core, Prompt Compiler, Scheduler, and "
                "ApiFreeLLM as described in FreeCode.md."
            )

        self.write_agent_message(reply)