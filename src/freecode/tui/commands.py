"""
tui.commands - slash commands (/help, /sessions, …).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from freecode.tui.app import FreeCodeApp


@dataclass(frozen=True, slots=True)
class CommandResult:
    handled: bool
    message: str = ""
    error: bool = False


HELP_TEXT = """\
**Shortcuts & commands**

| Key | Action |
|-----|--------|
| Enter | New line in composer |
| Ctrl+Enter | Send message |
| Ctrl+X | Interrupt agent |
| Ctrl+C | Quit |

| Command | Action |
|---------|--------|
| `/help` | Show this help |
| `/sessions` | List saved sessions |
| `/session new [title]` | Create & switch to a new session |
| `/new` | Same as `/session new` (fresh chat, no old memory) |
| `/session switch <id>` | Switch to an existing session |
| `/session` | Show active session id |

Each app launch starts a **fresh** session. Old chats stay in `/sessions`.
Sessions are stored under `.freecode/state.db`.
Mutating tools (edits, shell, git writes) prompt **Allow / Deny**.
"""


def try_handle_slash(app: FreeCodeApp, text: str) -> CommandResult:
    raw = text.strip()
    if not raw.startswith("/"):
        return CommandResult(handled=False)

    parts = raw.split(maxsplit=2)
    cmd = parts[0].lower()
    arg1 = parts[1] if len(parts) > 1 else ""
    rest = parts[2] if len(parts) > 2 else ""

    if cmd in ("/help", "/?"):
        return CommandResult(handled=True, message=HELP_TEXT)

    if cmd in ("/new", "/clear"):
        return _cmd_session_new(app, "")

    if cmd == "/sessions":
        return _cmd_sessions(app)

    if cmd == "/session":
        if not arg1 or arg1 in ("show", "current"):
            return _cmd_session_show(app)
        if arg1 == "new":
            return _cmd_session_new(app, rest.strip())
        if arg1 == "switch":
            if not rest.strip():
                return CommandResult(
                    handled=True,
                    message="Usage: `/session switch <id>`",
                    error=True,
                )
            return _cmd_session_switch(app, rest.strip())
        # /session <id> as switch shorthand
        return _cmd_session_switch(app, arg1)

    return CommandResult(
        handled=True,
        message=f"Unknown command `{cmd}`. Try `/help`.",
        error=True,
    )


def _cmd_sessions(app: FreeCodeApp) -> CommandResult:
    store = app.session_store
    if store is None:
        return CommandResult(handled=True, message="Persistence not available.", error=True)
    rows = store.list_sessions(limit=20)
    if not rows:
        return CommandResult(handled=True, message="No sessions yet. Use `/session new`.")
    active = store.active_session_id()
    lines = ["**Sessions**", ""]
    for s in rows:
        mark = "→ " if s.id == active else "  "
        title = s.title or s.goal or "(untitled)"
        lines.append(f"{mark}`{s.id}`  {title}  · turn {s.turn} · {s.phase}")
    lines.append("")
    lines.append("Switch: `/session switch <id>`")
    return CommandResult(handled=True, message="\n".join(lines))


def _cmd_session_show(app: FreeCodeApp) -> CommandResult:
    sid = app.active_session_id
    if not sid:
        return CommandResult(handled=True, message="No active session.")
    return CommandResult(handled=True, message=f"Active session: `{sid}`")


def _cmd_session_new(app: FreeCodeApp, title: str) -> CommandResult:
    sid = app.new_session(title=title)
    return CommandResult(handled=True, message=f"New session `{sid}`" + (f" — {title}" if title else ""))


def _cmd_session_switch(app: FreeCodeApp, session_id: str) -> CommandResult:
    ok = app.switch_session(session_id)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Session `{session_id}` not found.",
            error=True,
        )
    return CommandResult(handled=True, message=f"Switched to session `{session_id}`")
