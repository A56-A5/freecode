"""
tui.widgets.command_palette - drop-up command list above the input.

Plain Static rows (no ListView) so focus never leaves the composer.
"""
from __future__ import annotations

from dataclasses import dataclass

from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static


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
    CommandSpec("/sessions", "", "List sessions with chat history"),
    CommandSpec("/session switch", "<n>", "Switch by list # from /sessions"),
    CommandSpec("/session delete", "<n>", "Delete by list # from /sessions"),
    CommandSpec("/session new", "[title]", "Create a new session"),
    CommandSpec("/new", "", "Fresh chat"),
    CommandSpec("/edit", "", "Load last user prompt"),
    CommandSpec("/cls", "", "Clear transcript view"),
    CommandSpec("/copy", "", "Copy last assistant reply"),
    CommandSpec("/copy code", "", "Copy last code block"),
    CommandSpec("/plan", "", "Toggle dry-run plan mode"),
    CommandSpec("/undo", "", "Undo last file edit batch"),
    CommandSpec("/provider", "[name]", "List or switch LLM provider"),
    CommandSpec("/model", "[name]", "List or switch Groq model"),
    CommandSpec("/theme", "[name]", "List or switch theme"),
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
    return out[:12]


class CommandChosen(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class CommandPalette(Vertical):
    can_focus = False
    can_focus_children = False

    DEFAULT_CSS = """
    CommandPalette {
        width: 1fr;
        height: auto;
        max-height: 12;
        display: none;
        border: solid $accent;
        background: $surface;
        padding: 0 1 1 1;
        margin: 0 0 1 0;
    }
    CommandPalette.-open {
        display: block;
    }
    #palette-title {
        text-style: bold;
        color: $accent;
        height: 1;
    }
    #palette-body {
        height: auto;
        color: $foreground;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._specs: list[CommandSpec] = list(COMMAND_SPECS)[:12]
        self._index = 0
        self._filter = "/"

    def compose(self):
        yield Static("↑↓ select · Enter insert · Esc close", id="palette-title")
        yield Static("", id="palette-body")

    def is_open(self) -> bool:
        return bool(self.has_class("-open"))

    def open_palette(self, prefix: str = "/") -> None:
        raw = prefix or "/"
        self._filter = raw if raw.startswith("/") else f"/{raw}"
        self._index = 0
        self.display = True
        self.add_class("-open")
        self._rebuild()
        self.refresh(layout=True)

    def close_palette(self) -> None:
        self.remove_class("-open")
        self.display = False
        self.refresh(layout=True)

    def refine(self, prefix: str) -> None:
        if not self.is_open():
            return
        raw = prefix or "/"
        self._filter = raw if raw.startswith("/") else f"/{raw}"
        self._index = 0
        self._rebuild()

    def move(self, delta: int) -> None:
        if not self._specs:
            return
        self._index = max(0, min(len(self._specs) - 1, self._index + delta))
        self._render_body()

    def current_insert(self) -> str | None:
        if not self._specs:
            return None
        idx = max(0, min(len(self._specs) - 1, self._index))
        return self._specs[idx].insert_text

    def accept(self) -> str | None:
        text = self.current_insert()
        self.close_palette()
        return text

    def _rebuild(self) -> None:
        self._specs = filter_commands(self._filter)
        if self._index >= len(self._specs):
            self._index = max(0, len(self._specs) - 1)
        self._render_body()

    def _render_body(self) -> None:
        lines: list[str] = []
        for i, spec in enumerate(self._specs):
            if i == self._index:
                lines.append(f"[reverse] {spec.label} [/reverse]")
            else:
                lines.append(f" {spec.label}")
        body = "\n".join(lines) if lines else " (no matches)"
        try:
            self.query_one("#palette-body", Static).update(body)
        except Exception:
            pass
