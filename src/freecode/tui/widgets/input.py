"""
tui.widgets.input - FreeCode composers.
"""
from __future__ import annotations

from textual import on
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input, TextArea

from freecode.tui.widgets.command_palette import CommandChosen, CommandPalette


class MessageSubmitted(Message):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class FreeCodeInput(Input):
    DEFAULT_CSS = """
    FreeCodeInput {
        width: 1fr;
        height: 3;
        border: round $panel;
        background: $surface;
        color: $foreground;
        padding: 0 1;
    }
    FreeCodeInput:focus {
        border: round $accent;
    }
    """

    def __init__(self, *, placeholder: str = "Type a message...", **kwargs) -> None:
        super().__init__(placeholder=placeholder, **kwargs)

    @on(Input.Submitted)
    def _forward_submit(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self.post_message(MessageSubmitted(text))
        event.stop()


def _find_palette(widget) -> CommandPalette | None:
    app = widget.app
    wid = getattr(widget, "id", None)
    try:
        if wid == "landing-input":
            return app.query_one("#landing-palette", CommandPalette)
    except Exception:
        pass
    try:
        if wid == "chat-input":
            return app.query_one("#command-palette", CommandPalette)
    except Exception:
        pass
    try:
        landing = app.query_one("#landing")
        if getattr(landing, "display", True) is not False:
            return app.query_one("#landing-palette", CommandPalette)
    except Exception:
        pass
    try:
        return app.query_one("#command-palette", CommandPalette)
    except Exception:
        return None


class FreeCodeComposer(TextArea):
    BINDINGS = [
        Binding("ctrl+enter", "submit", "Send", priority=True, show=True),
        Binding("ctrl+j", "submit", "Send", priority=True, show=False),
        Binding("ctrl+slash", "open_palette", "Commands", priority=True, show=True),
        Binding("escape", "escape_palette", "Close palette", priority=True, show=False),
        Binding("up", "palette_up", "Palette up", priority=True, show=False),
        Binding("down", "palette_down", "Palette down", priority=True, show=False),
        Binding("enter", "palette_or_newline", "Select / newline", priority=True, show=False),
    ]

    DEFAULT_CSS = """
    FreeCodeComposer {
        width: 1fr;
        height: 7;
        min-height: 5;
        max-height: 14;
        border: round $panel;
        background: $surface;
        color: $foreground;
        padding: 0 1;
    }
    FreeCodeComposer:focus {
        border: round $accent;
    }
    """

    def __init__(self, *, id: str | None = None, **kwargs) -> None:
        super().__init__(id=id, **kwargs)

    def action_submit(self) -> None:
        text = self.text.strip()
        if not text:
            return
        self.post_message(MessageSubmitted(text))
        self.clear()

    def action_open_palette(self) -> None:
        self._sync_palette(force_open=True)
        self.focus()

    def action_escape_palette(self) -> None:
        pal = _find_palette(self)
        if pal is not None and pal.is_open():
            pal.close_palette()

    def action_palette_up(self) -> None:
        pal = _find_palette(self)
        if pal is not None and pal.is_open():
            pal.move(-1)
            return
        try:
            self.action_cursor_up()
        except Exception:
            pass

    def action_palette_down(self) -> None:
        pal = _find_palette(self)
        if pal is not None and pal.is_open():
            pal.move(1)
            return
        try:
            self.action_cursor_down()
        except Exception:
            pass

    def action_palette_or_newline(self) -> None:
        pal = _find_palette(self)
        if pal is not None and pal.is_open():
            text = pal.accept()
            if text is not None:
                self._apply_palette_choice(text)
            return
        try:
            self.insert("\n")
        except Exception:
            pass

    def _apply_palette_choice(self, text: str) -> None:
        text = (text or "").rstrip("\n")  # keep trailing space for args
        self.clear()
        if text == "":
            self.focus()
            return
        self.text = text
        try:
            lines = text.split("\n")
            self.cursor_location = (len(lines) - 1, len(lines[-1]))
        except Exception:
            pass
        self.focus()

    def on_key(self, event) -> None:  # type: ignore[no-untyped-def]
        key = getattr(event, "key", None) or ""
        if key == "enter":
            pal = _find_palette(self)
            if pal is not None and pal.is_open():
                text = pal.accept()
                if text is not None:
                    self._apply_palette_choice(text)
                event.prevent_default()
                event.stop()
                return
        if key == "escape":
            pal = _find_palette(self)
            if pal is not None and pal.is_open():
                pal.close_palette()
                event.prevent_default()
                event.stop()
                return
        if key in ("up", "down"):
            pal = _find_palette(self)
            if pal is not None and pal.is_open():
                pal.move(-1 if key == "up" else 1)
                event.prevent_default()
                event.stop()
                return
        ch = getattr(event, "character", None)
        if ch == "/" or (ch and ch.isprintable()):
            self.call_after_refresh(self._sync_palette)

    def _sync_palette(self, force_open: bool = False) -> None:
        pal = _find_palette(self)
        if pal is None:
            return
        first = (self.text or "").split("\n", 1)[0]
        stripped = first.strip()
        if force_open or stripped.startswith("/"):
            if not stripped.startswith("/"):
                stripped = "/"
            if not pal.is_open():
                pal.open_palette(stripped or "/")
            else:
                pal.refine(stripped or "/")
            return
        if pal.is_open():
            pal.close_palette()

    def on_command_chosen(self, event: CommandChosen) -> None:
        event.stop()
        self._apply_palette_choice(event.text)
