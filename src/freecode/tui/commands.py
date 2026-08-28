"""
tui.commands - slash commands (/help, /sessions, …).
"""
from __future__ import annotations

from datetime import datetime
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
| Ctrl+E | Edit last prompt (load into composer) |
| Ctrl+/ or type `/` | Open command palette |
| Ctrl+X | Interrupt agent |
| Ctrl+C | Quit |

| Command | Action |
|---------|--------|
| `/help` | Show this help |
| `/sessions` | List saved sessions (one per line) |
| `/session new [title]` | Create & switch to a new session |
| `/new` | Fresh chat (no old memory) |
| `/session switch <n|id>` | Switch by list # or id prefix |
| `/session delete <n|id>` | Delete by list # or id prefix |
| `/session` | Show active session id |
| `/edit` | Load last user prompt into the composer |
| `/provider` | List / switch LLM provider (apifreellm, groq) |
| `/model` | List / switch Groq model |
| `/plan` | Toggle dry-run plan mode |
| `/undo` | Restore files from last edit batch |
| `/theme` | List color themes |
| `/theme <name>` | Switch theme (live) |
| `/provider` | List LLM providers |
| `/provider <name>` | Force provider (apifreellm / groq) |

While **Cooking…**, new messages are **queued** and sent after the current turn.

FreeCode **can** run shell/search/edit actions after you **Allow** them in the
permission dialog. Prefer asking it to *run* a command rather than only print it.

Sessions live under `.freecode/state.db`.
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

    if cmd == "/theme":
        return _cmd_theme(app, arg1)

    if cmd == "/provider":
        return _cmd_provider(app, arg1)

    if cmd in ("/plan", "/dry-run", "/dryrun"):
        return _cmd_plan(app)

    if cmd == "/undo":
        return _cmd_undo(app)

    if cmd == "/model":
        rest_model = (arg1 + (" " + rest if rest else "")).strip() if arg1 else ""
        return _cmd_model(app, rest_model)

    if cmd == "/edit":
        return _cmd_edit_last(app)

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
        if arg1 in ("delete", "rm", "remove"):
            if not rest.strip():
                return CommandResult(
                    handled=True,
                    message="Usage: `/session delete <id>`",
                    error=True,
                )
            return _cmd_session_delete(app, rest.strip())
        return _cmd_session_switch(app, arg1)

    return CommandResult(
        handled=True,
        message=f"Unknown command `{cmd}`. Try `/help`.",
        error=True,
    )


def _fmt_ts(ts: float) -> str:
    try:
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
    except (OverflowError, OSError, ValueError):
        return "?"


def _cmd_sessions(app: FreeCodeApp) -> CommandResult:
    store = app.session_store
    if store is None:
        return CommandResult(handled=True, message="Persistence not available.", error=True)
    rows = store.list_sessions(limit=30)
    if not rows:
        return CommandResult(handled=True, message="No sessions yet. Use `/new`.")
    active = store.active_session_id()
    lines = ["**Sessions**", ""]
    for i, s in enumerate(rows, start=1):
        mark = "→" if s.id == active else " "
        title = (s.title or s.goal or "(untitled)").replace("\n", " ")[:40]
        when = _fmt_ts(s.updated_at)
        short = s.id[:8]
        lines.append(
            f"{mark} **#{i}** `{short}` · {title} · turn {s.turn} · {s.phase} · {when}"
        )
    lines.append("")
    lines.append("Switch: `/session switch 1` or `/session switch <id>`")
    lines.append("Delete: `/session delete 1` or `/session delete <id>`")
    lines.append("New: `/new`")
    return CommandResult(handled=True, message="\n".join(lines))



def _resolve_session_ref(app: FreeCodeApp, ref: str) -> str | None:
    """Accept list index (#1 / 1), short prefix, or full id."""
    ref = (ref or "").strip().lstrip("#")
    if not ref:
        return None
    store = app.session_store
    if store is None:
        return None
    rows = store.list_sessions(limit=50)
    if ref.isdigit():
        idx = int(ref)
        if 1 <= idx <= len(rows):
            return rows[idx - 1].id
        return None
    # exact or prefix match
    for s in rows:
        if s.id == ref or s.id.startswith(ref):
            return s.id
    return None


def _cmd_session_show(app: FreeCodeApp) -> CommandResult:
    sid = app.active_session_id
    if not sid:
        return CommandResult(handled=True, message="No active session.")
    return CommandResult(handled=True, message=f"Active session: `{sid}`")


def _cmd_session_new(app: FreeCodeApp, title: str) -> CommandResult:
    sid = app.new_session(title=title)
    return CommandResult(
        handled=True,
        message=f"New session `{sid}`" + (f" — {title}" if title else ""),
    )


def _cmd_session_switch(app: FreeCodeApp, session_id: str) -> CommandResult:
    resolved = _resolve_session_ref(app, session_id)
    if not resolved:
        return CommandResult(
            handled=True,
            message=f"Session `{session_id}` not found. Use `/sessions` then `/session switch 1`.",
            error=True,
        )
    ok = app.switch_session(resolved)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Session `{session_id}` not found.",
            error=True,
        )
    return CommandResult(handled=True, message=f"Switched to session `{resolved[:8]}`")


def _cmd_session_delete(app: FreeCodeApp, session_id: str) -> CommandResult:
    resolved = _resolve_session_ref(app, session_id)
    if not resolved:
        return CommandResult(
            handled=True,
            message=f"Session `{session_id}` not found. Use `/sessions` then `/session delete 1`.",
            error=True,
        )
    ok = app.delete_session(resolved)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Could not delete `{resolved[:8]}`.",
            error=True,
        )
    return CommandResult(handled=True, message=f"Deleted session `{resolved[:8]}`")


def _cmd_plan(app: FreeCodeApp) -> CommandResult:
    on = app.toggle_plan_mode()
    if on:
        return CommandResult(
            handled=True,
            message="**Plan mode ON** — tools are simulated only (no disk/shell/web side effects). `/plan` again to leave.",
        )
    return CommandResult(handled=True, message="**Plan mode OFF** — tools apply normally (with approval).")


def _cmd_undo(app: FreeCodeApp) -> CommandResult:
    msg = app.undo_last_tools()
    return CommandResult(handled=True, message=f"**Undo**\n\n{msg}")


def _cmd_model(app: FreeCodeApp, name: str) -> CommandResult:

    from freecode.llm.providers.groq import GROQ_MODELS, DEFAULT_MODEL

    # Only meaningful for Groq today; still list for discoverability
    cur_provider = app.active_provider()
    cur = app.active_model() or DEFAULT_MODEL
    if cur_provider != "groq" and name:
        return CommandResult(
            handled=True,
            message=f"Switch to Groq first: `/provider groq` (current: `{cur_provider}`).",
            error=True,
        )
    if not name:
        lines = [
            f"**Models** (active provider: `{cur_provider}`)",
            f"Current: `{cur}`",
            "",
            "Groq free-tier models:",
        ]
        for m in GROQ_MODELS:
            mark = "→" if m == cur else " "
            lines.append(f"{mark} `{m}`")
        lines.append("")
        lines.append("Switch: `/model llama-3.3-70b-versatile`")
        lines.append("Tip: switch provider first with `/provider groq`")
        return CommandResult(handled=True, message="\n".join(lines))
    ok = app.set_model_name(name)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Could not set model `{name}` on provider `{cur_provider}`.",
            error=True,
        )
    return CommandResult(
        handled=True,
        message=f"Model set to `{name}` on `{app.active_provider()}`",
    )


def _cmd_provider(app: FreeCodeApp, name: str) -> CommandResult:

    names = app.list_providers()
    if not name:
        cur = app.active_provider()
        lines = ["**Providers**", ""]
        for n in names:
            mark = "→" if n == cur else " "
            lines.append(f"{mark} `{n}`")
        lines.append("")
        lines.append("Switch: `/provider apifreellm` or `/provider groq`")
        lines.append("Keys: FREECODE_API_KEY… · GROQ_API_KEY…")
        return CommandResult(handled=True, message="\n".join(lines))
    ok = app.set_provider_name(name)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Unknown provider `{name}`. Available: {', '.join(names)}",
            error=True,
        )
    return CommandResult(handled=True, message=f"Provider set to `{name}`")


def _cmd_theme(app: FreeCodeApp, name: str) -> CommandResult:

    from freecode.tui.theme import list_theme_names

    names = list_theme_names()
    if not name:
        cur = getattr(app, "theme", "") or ""
        lines = ["**Themes**", ""]
        for n in names:
            mark = "→" if n == cur else " "
            lines.append(f"{mark} `{n}`")
        lines.append("")
        lines.append("Switch: `/theme <name>`")
        return CommandResult(handled=True, message="\n".join(lines))
    ok = app.set_theme_name(name)
    if not ok:
        return CommandResult(
            handled=True,
            message=f"Unknown theme `{name}`. Available: {', '.join(names)}",
            error=True,
        )
    return CommandResult(handled=True, message=f"Theme set to `{name}`")


def _cmd_edit_last(app: FreeCodeApp) -> CommandResult:
    text = app.load_last_prompt_into_composer()
    if not text:
        return CommandResult(
            handled=True,
            message="No previous user prompt to edit.",
            error=True,
        )
    return CommandResult(
        handled=True,
        message="Last prompt loaded into the composer — edit and Ctrl+Enter to resend.",
    )
