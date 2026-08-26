"""
tui.panes.transcript - the unified conversation stream.

The transcript deliberately follows the visual language of terminal
coding agents such as Claude Code and OpenCode:

    › user prompt

    ● assistant response

User messages receive a subtle visual rail/background while assistant
messages remain mostly plain text.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Static


class TranscriptPane(VerticalScroll):
    DEFAULT_CSS = """
    TranscriptPane {
        width: 1fr;
        height: 1fr;

        background: $background;

        scrollbar-color: $accent;
        scrollbar-background: $background;
        scrollbar-corner-color: $background;
    }

    .message {
        width: 1fr;
        height: auto;
    }

    .user-message {
        width: 1fr;
        height: auto;

        margin: 1 1 1 1;
        padding: 0 1;

        background: $surface;
        border-left: thick $accent;

        color: $foreground;
    }

    .user-message-content {
        width: 1fr;
        height: auto;

        color: $foreground;
    }

    .assistant-message {
        width: 1fr;
        height: auto;

        margin: 1 1 2 1;
        padding: 0 1;

        background: $background;

        color: $foreground;
    }

    .assistant-message-content {
        width: 1fr;
        height: auto;

        color: $foreground;
    }

    .assistant-marker {
        width: auto;
        height: auto;

        color: $foreground;
        text-style: bold;
    }

    .user-marker {
        width: auto;
        height: auto;

        color: $accent;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        # The transcript starts empty.
        #
        # Messages are mounted dynamically by write_user_message() and
        # write_agent_message().
        yield from ()

    def write_user_message(self, text: str) -> None:
        """
        Render a user message with a subtle highlighted/railed treatment.
        """

        message = Static(
            f"› {text}",
            classes="message user-message",
        )

        self.mount(message)
        self.scroll_end(animate=False)

    def write_agent_message(self, text: str) -> None:
        """
        Render an assistant response as plain flowing terminal text.
        """

        message = Static(
            f"● {text}",
            classes="message assistant-message",
        )

        self.mount(message)
        self.scroll_end(animate=False)

    def write_mock_reply(self, prompt: str) -> None:
        """
        Temporary ph-01 fixture.

        This exists only so the TUI can be visually tested before the
        Agent Core is implemented.
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
                "This is a mock FreeCode response for ph-01.\n\n"
                "The real reasoning loop will eventually go through "
                "the Agent Core, Prompt Compiler, Scheduler, and "
                "ApiFreeLLM as described in FreeCode.md."
            )

        self.write_agent_message(reply)