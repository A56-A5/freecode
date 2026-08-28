"""
tui.widgets.command_palette - live `/` command picker with query field.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual import on
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, ListItem, ListView, Static


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


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("/help", "", "Show shortcuts and commands"),
    CommandSpec("/sessions", "", "List saved sessions"),
    CommandSpec("/session new", "[title]", "Create and switch to a new session"),
    CommandSpec("/session switch", "<n|id>", "Switch by list # or id"),
    CommandSpec("/session delete", "<n|id>", "Delete by list # or id"),
    CommandSpec("/session", "", "Show active session id"),
    CommandSpec("/new", "", "Fresh chat (no old memory)"),
    CommandSpec("/edit", "", "Load last user prompt into the composer"),
    CommandSpec("/clear", "", "Alias for /new"),
    CommandSpec("/theme", "[name]", "List or switch color themes"),
    CommandSpec("/provider", "[name]", "List or force LLM provider"),
    CommandSpec("/model", "[name]", "List or switch Groq model"),
    CommandSpec("/plan", "", "Toggle dry-run plan mode"),
    CommandSpec("/undo", "", "Undo last file edit batch"),
)


def filter_commands(prefix: str) -> list[CommandSpec]:
    q = (prefix or "/").strip().lower()
    if not q.startswith("/"):
        q = "/" + q
    hits = [c for c in COMMAND_SPECS if c.name.startswith(q) or q in c.name]
    if not hits and len(q) > 1:
        tail = q[1:]
        hits = [
            c
            for c in COMMAND_SPECS
            if tail in c.name.lower() or tail in c.description.lower()
        ]
    if not hits:
        hits = list(COMMAND_SPECS)
    seen: set[str] = set()
    out: list[CommandSpec] = []
    for c in hits:
        if c.name not in seen:
            seen.add(c.name)
            out.append(c)
    return out


class CommandPalette(ModalScreen[str | None]):
    """Live-filtering command picker. Returns insert text or None."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("enter", "select", "Select", priority=True, show=True),
    ]

    DEFAULT_CSS = """
    CommandPalette {
        align: center middle;
    }
    #palette-box {
        width: 72;
        max-width: 90%;
        height: auto;
        max-height: 20;
        border: thick $accent;
        background: $surface;
        padding: 1 1;
    }
    #palette-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    #palette-query {
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
        self._prefix = prefix if prefix.startswith("/") else f"/{prefix}"
        self._specs: list[CommandSpec] = filter_commands(self._prefix)
        self._rebuild_token = 0

    def compose(self):
        yield Vertical(
            Static("Commands", id="palette-title"),
            Input(value=self._prefix, placeholder="/…", id="palette-query"),
            ListView(id="palette-list"),
            Static("Type to filter · Enter = top match · Esc = cancel", id="palette-hint"),
            id="palette-box",
        )

    def on_mount(self) -> None:
        self._inject_session_specs()
        self.call_after_refresh(self._rebuild_list)
        q = self.query_one("#palette-query", Input)
        q.focus()
        q.cursor_position = len(q.value)

    def _inject_session_specs(self) -> None:
        """When query looks like /session switch|delete, list #1.. from store."""
        global COMMAND_SPECS
        try:
            store = getattr(self.app, "session_store", None)
            if store is None:
                return
            rows = store.list_sessions(limit=12)
            extras = []
            for i, s in enumerate(rows, start=1):
                title = (s.title or s.goal or "session")[:28]
                extras.append(
                    CommandSpec(
                        f"/session switch {i}",
                        "",
                        f"{title} ({s.id[:8]})",
                    )
                )
                extras.append(
                    CommandSpec(
                        f"/session delete {i}",
                        "",
                        f"delete {title}",
                    )
                )
            # prepend dynamic specs for this palette instance only
            self._dynamic = extras
        except Exception:
            self._dynamic = []

    def _rebuild_list(self) -> None:
        self._rebuild_token += 1
        token = self._rebuild_token
        try:
            query = self.query_one("#palette-query", Input).value
        except Exception:
            query = self._prefix
        base = filter_commands(query)
        dyn = getattr(self, '_dynamic', [])
        q = (query or '').lower()
        if 'switch' in q or 'delete' in q or q.startswith('/session'):
            extra = [c for c in dyn if c.name.startswith(q.rstrip()) or q.rstrip() in c.name]
            # merge unique
            seen = {c.name for c in base}
            self._specs = base + [c for c in extra if c.name not in seen]
        else:
            self._specs = base

        lv = self.query_one("#palette-list", ListView)
        for child in list(lv.children):
            child.remove()

        items = [ListItem(Label(spec.label)) for spec in self._specs]

        async def _mount() -> None:
            if token != self._rebuild_token:
                return
            if items:
                await lv.mount(*items)
                if token == self._rebuild_token and self._specs:
                    lv.index = 0

        self.app.run_worker(_mount(), exclusive=False)

    @on(Input.Changed, "#palette-query")
    def _on_query_changed(self, event: Input.Changed) -> None:
        self._rebuild_list()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_select(self) -> None:
        self._dismiss_selected()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        self._dismiss_selected()

    def _dismiss_selected(self) -> None:
        # Prefer ListView highlight; fall back to first filtered match.
        if self._specs:
            try:
                lv = self.query_one("#palette-list", ListView)
                idx = lv.index if lv.index is not None else 0
                if not (0 <= idx < len(self._specs)):
                    idx = 0
                self.dismiss(self._specs[idx].insert_text)
                return
            except Exception:
                self.dismiss(self._specs[0].insert_text)
                return
        self.dismiss(None)
