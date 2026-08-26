"""
tui.widgets.activity - the "● Cooking..." activity indicator.

Shown only while the agent is doing something (matches the reference
screenshot's behavior - it's a live status, not a permanent fixture).
Hidden entirely (display=False) when idle rather than showing an "IDLE"
banner, so the UI stays quiet when there's nothing to report.

No agent exists yet (ph-06), so nothing drives this in ph-01 - it's
exercised directly via set_activity()/set_idle() in tests, same pattern
as the cooldown bar.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static


class ActivityIndicator(Static):
    COMPONENT_CLASSES = {"activity--dot"}

    DEFAULT_CSS = """
    ActivityIndicator > .activity--dot {
        color: $accent;
    }
    ActivityIndicator {
        display: none;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = ""
        # Explicit, not just via DEFAULT_CSS's `display: none` - CSS only
        # applies once mounted in an app, so a standalone/unmounted
        # instance (as used in unit tests, or if ever reused elsewhere)
        # should still start hidden.
        self.display = False

    def set_activity(self, label: str) -> None:
        self._label = label
        self.display = True
        self.refresh()

    def set_idle(self) -> None:
        self._label = ""
        self.display = False
        self.refresh()

    def render(self) -> Text:
        if not self._label:
            return Text("")
        dot_style = self.get_component_rich_style("activity--dot")
        text = Text()
        text.append("● ", style=dot_style)
        text.append(self._label)
        return text
