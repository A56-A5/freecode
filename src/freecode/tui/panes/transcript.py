"""
tui.panes.transcript - the single unified conversation stream.

Deliberately replaces the earlier chat/diff/commands three-pane layout.
Everything happening in a session - user messages, agent messages, and
(from ph-06/ph-07 onward) proposed diffs and command output - renders
inline in this one scrollable log, in the order it happened, the way
Claude Code and opencode present a session rather than splitting it
across separate boxed regions.

ph-01 scope: user/agent text messages only. write_diff()/write_command()
land in ph-06/ph-07 when there's something real to render.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog


class TranscriptPane(Vertical):
    DEFAULT_CSS = """
    TranscriptPane {
        background: $background;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(id="transcript-log", wrap=True, markup=True, highlight=False)

    def write_user_message(self, text: str) -> None:
        self.query_one("#transcript-log", RichLog).write(f"[bold cyan]›[/bold cyan] {text}")

    def write_agent_message(self, text: str) -> None:
        self.query_one("#transcript-log", RichLog).write(f"[bold green]●[/bold green] {text}")
