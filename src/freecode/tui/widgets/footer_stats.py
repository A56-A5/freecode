"""
tui.widgets.footer_stats - bottom status line.
"""
from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class FooterStats(Static):
    mode_label: reactive[str] = reactive("freecode")
    files_edited: reactive[int] = reactive(0)
    session_label: reactive[str] = reactive("")

    def set_stats(
        self,
        *,
        mode_label: str | None = None,
        files_edited: int | None = None,
        session_label: str | None = None,
    ) -> None:
        if mode_label is not None:
            self.mode_label = mode_label
        if files_edited is not None:
            self.files_edited = files_edited
        if session_label is not None:
            self.session_label = session_label

    def render(self) -> str:
        noun = "file" if self.files_edited == 1 else "files"
        sess = f" · sess {self.session_label}" if self.session_label else ""
        return (
            f"[dim]{self.mode_label}{sess} · {self.files_edited} {noun} edited"
            f" · /help[/dim]"
        )
