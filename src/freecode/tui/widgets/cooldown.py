"""
tui.widgets.cooldown - the live rate-limit cooldown bar.

Block-fill style (solid blocks filling left-to-right, matching the
reference screenshot) rather than the earlier boxed/labeled version.
Colors come from the active theme via Textual's component-class system
(COMPONENT_CLASSES + DEFAULT_CSS) rather than hardcoded hex, so a user's
`.freecode/theme.toml` override changes this bar automatically.

Contract this widget exposes to ph-04's Scheduler (unchanged from the
original design - only the rendering changed):
    bar.set_cooldown(total_seconds, remaining_seconds)   # normal cooldown
    bar.set_backoff(total_seconds, remaining_seconds)    # 429/5xx backoff
    bar.set_idle()                                       # no request in flight
"""
from __future__ import annotations

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

BAR_WIDTH = 24
FILLED_CHAR = "█"
EMPTY_CHAR = "░"


class CooldownBar(Static):
    COMPONENT_CLASSES = {"cooldown--filled", "cooldown--backoff", "cooldown--empty"}

    DEFAULT_CSS = """
    CooldownBar > .cooldown--filled {
        color: $success;
    }
    CooldownBar > .cooldown--backoff {
        color: $error;
    }
    CooldownBar > .cooldown--empty {
        color: $panel;
    }
    """

    mode: reactive[str] = reactive("idle")            # idle | cooldown | backoff
    total_seconds: reactive[float] = reactive(0.0)
    remaining_seconds: reactive[float] = reactive(0.0)

    def set_idle(self) -> None:
        self.mode = "idle"
        self.total_seconds = 0.0
        self.remaining_seconds = 0.0

    def set_cooldown(self, total_seconds: float, remaining_seconds: float) -> None:
        self.mode = "cooldown"
        self.total_seconds = total_seconds
        self.remaining_seconds = max(0.0, min(remaining_seconds, total_seconds))

    def set_backoff(self, total_seconds: float, remaining_seconds: float) -> None:
        self.mode = "backoff"
        self.total_seconds = total_seconds
        self.remaining_seconds = max(0.0, min(remaining_seconds, total_seconds))

    def _fraction_filled(self) -> float:
        if self.total_seconds <= 0:
            return 0.0
        elapsed = self.total_seconds - self.remaining_seconds
        return max(0.0, min(1.0, elapsed / self.total_seconds))

    def render(self) -> Text:
        if self.mode == "idle" or self.total_seconds <= 0:
            return Text("Ready", style="dim")

        filled_class = "cooldown--backoff" if self.mode == "backoff" else "cooldown--filled"
        filled_style = self.get_component_rich_style(filled_class)
        empty_style = self.get_component_rich_style("cooldown--empty")

        filled = round(self._fraction_filled() * BAR_WIDTH)
        text = Text()
        text.append(FILLED_CHAR * filled, style=filled_style)
        text.append(EMPTY_CHAR * (BAR_WIDTH - filled), style=empty_style)
        label = "backoff" if self.mode == "backoff" else "next request"
        text.append(f"  {self.remaining_seconds:4.1f}s · {label}", style="dim")
        return text
