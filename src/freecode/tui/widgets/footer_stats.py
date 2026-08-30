"""
tui.widgets.footer_stats - minimal bottom status line.
"""
from __future__ import annotations

from textual.reactive import reactive
from textual.widgets import Static


class FooterStats(Static):
    model_label: reactive[str] = reactive("—")
    status: reactive[str] = reactive("ready")
    files_edited: reactive[int] = reactive(0)

    def set_stats(
        self,
        *,
        model_label: str | None = None,
        status: str | None = None,
        files_edited: int | None = None,
        # accepted but ignored (older call sites)
        mode_label: str | None = None,
        session_label: str | None = None,
        hint: str | None = None,
    ) -> None:
        if model_label is not None:
            self.model_label = model_label
        elif mode_label is not None:
            self.model_label = mode_label
        if status is not None:
            self.status = status
        if files_edited is not None:
            self.files_edited = files_edited

    def render(self) -> str:
        noun = "file" if self.files_edited == 1 else "files"
        return (
            f"[dim]{self.model_label} · {self.status}"
            f" · {self.files_edited} {noun} edited · /help[/dim]"
        )
