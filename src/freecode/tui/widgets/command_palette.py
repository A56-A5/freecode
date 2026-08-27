"""
tui.widgets.command_palette - live `/` command picker.

Opens when the composer starts with `/`, filters as the user types,
Tab/Enter completes the selected command into the composer.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView, Static


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    args_hint: str
    description: str

    @property
    def insert_text(self) -> str:
        if self.args_hint:
            return f"{self.name} "
        return self.name

    @property
    def label(self) -> str:
        hint = f" {self.args_hint}" if self.args_hint else ""
        return f"{self.name}{hint}  —  {self.description}"


# Single source of truth for discoverability (dispatch stays in commands.py).
COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("/help", "", "Show shortcuts and commands"),
    CommandSpec("/sessions", "", "List saved sessions"),
    CommandSpec("/session", "new|switch|delete|show", "Session management"),
    CommandSpec("/session new", "[title]", "Create and switch to a new session"),
    CommandSpec("/session switch", "<id>", "Switch to an existing session"),
    CommandSpec("/session delete", "<id>", "Delete a session"),
    CommandSpec("/session", "", "Show active session id"),
    CommandSpec("/new", "", "Fresh chat (no old memory)"),
    CommandSpec("/edit", "", "Load last user prompt into the composer"),
    CommandSpec("/clear", "", "Alias for /new"),
)


def filter_commands(prefix: str) -> list[CommandSpec]:
    q = (prefix or "").strip().lower()
    if not q.startswith("/"):
        return []
    hits = [c for c in COMMAND_SPECS if c.name.startswith(q) or q in c.name]
    if not hits:
        hits = [c for c in COMMAND_SPECS if q[1:] in c.name.lower() or q[1:] in c.description.lower()]
    # de-dupe by name preserving order
    seen: set[str] = set()
    out: list[CommandSpec] = []
    for c in hits:
        if c.name not in seen:
            seen.add(c.name)
            out.append(c)
    return out


class CommandChosen(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class CommandPalette(ModalScreen[str | None]):
    """Return the insert text for the chosen command, or None if cancelled."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "select", "Select", show=True),
    ]

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }
    #palette-box {
        width: 72;
        max-width: 90%;
        height: auto;
        max-height: 18;
        border: thick $accent;
        background: $surface;
        padding: 1 1;
    }
    #palette-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #palette-list {
        height: auto;
        max-height: 12;
        background: $surface;
    }
    #palette-hint {
        color: $secondary;
        margin-top: 1;
    }
    """

    def __init__(self, prefix: str = "/") -> None:
        super().__init__()
        self.prefix = prefix
        self._specs = filter_commands(prefix) or list(COMMAND_SPECS)

    def compose(self):
        items = [
            ListItem(Label(spec.label), id=f"cmd-{i}")
            for i, spec in enumerate(self._specs)
        ]
        yield Vertical(
            Static("Commands", id="palette-title"),
            ListView(*items, id="palette-list"),
            Static("Enter = select · Esc = cancel · filter by typing /…", id="palette-hint"),
            id="palette-box",
        )

    def on_mount(self) -> None:
        try:
            self.query_one("#palette-list", ListView).index = 0
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        self._dismiss_selected()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._dismiss_selected()

    def _dismiss_selected(self) -> None:
        try:
            lv = self.query_one("#palette-list", ListView)
            idx = lv.index if lv.index is not None else 0
            if 0 <= idx < len(self._specs):
                self.dismiss(self._specs[idx].insert_text)
                return
        except Exception:
            pass
        self.dismiss(None)
