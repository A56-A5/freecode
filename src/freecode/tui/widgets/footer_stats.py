"""
tui.widgets.footer_stats - bottom status line (mode, files edited).

Placeholder data source for now (ph-01) - real values plug in once the
Agent Core (ph-06) and Context Engine (ph-08) exist to report them
(e.g. context-window usage %, actual edited-file count).
"""
from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class FooterStats(Static):
    mode_label: reactive[str] = reactive("freecode")
    files_edited: reactive[int] = reactive(0)

    def set_stats(self, *, mode_label: str | None = None, files_edited: int | None = None) -> None:
        if mode_label is not None:
            self.mode_label = mode_label
        if files_edited is not None:
            self.files_edited = files_edited

    def render(self) -> str:
        noun = "file" if self.files_edited == 1 else "files"
        return f"[dim]{self.mode_label} · {self.files_edited} {noun} edited[/dim]"
