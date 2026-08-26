"""
tui.layout - the permanent UI structure (redesigned, no boxed panes):

    ┌───────────────────────────────────────────┐
    │                                             │
    │  Transcript (scrollable, fills the screen)  │
    │                                             │
    ├─────────────────────────────────────────────┤   <- Rule divider
    │ ● Cooking...                                 │   <- ActivityIndicator (hidden when idle)
    │ > Type a message...                          │   <- input
    │ ████████░░░░░░░░░░░░░░  14.2s · next request │   <- CooldownBar
    │ freecode · dry-run · 0 files edited           │   <- FooterStats
    └───────────────────────────────────────────────┘

Only assembles pieces into this shape - each piece owns its own behavior.
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Rule

from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats
from freecode.tui.widgets.input import FreeCodeInput


class MainLayout(Vertical):
    def compose(self) -> ComposeResult:
        yield TranscriptPane(id="transcript-pane")
        yield Rule(id="divider")
        yield ActivityIndicator(id="activity-indicator")
        yield FreeCodeInput(id="chat-input")
        yield CooldownBar(id="cooldown-bar")
        yield FooterStats(id="footer-stats")
