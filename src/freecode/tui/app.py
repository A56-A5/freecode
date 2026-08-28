"""
tui.app - FreeCode Textual application.

Live path: slash commands | AgentCore/AgentLoop → stream reply → approval
modal → tools → event coalescing → persistence.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input

from freecode.agent import AgentCore, AgentLoop
from freecode.config import Config, get_logger, load_config
from freecode.context import ContextEngine
from freecode.domain.errors import LLMError, LLMRateLimitError, LLMServerError
from freecode.domain.state import AgentState
from freecode.llm import Scheduler
from freecode.llm.providers import ApiFreeLLMProvider, GroqProvider, ProviderRouter
from freecode.context.mentions import expand_mentions
from freecode.security import ApprovalGate, ApprovalRequest
from freecode.storage import CooldownStore, EventStore, SessionStore
from freecode.tools import ToolExecutor
from freecode.tui.commands import try_handle_slash
from freecode.tui.layout import MainLayout
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import (
    APP_TITLE,
    build_theme,
    list_theme_names,
    persist_theme_name,
    preferred_theme_name,
)
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.approval import ApprovalModal
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats
from freecode.tui.widgets.input import FreeCodeComposer, MessageSubmitted

log = get_logger(__name__)


class FreeCodeApp(App):
    CSS_PATH = Path(__file__).parent / "app.tcss"
    TITLE = APP_TITLE
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+x", "interrupt", "Interrupt"),
        ("ctrl+e", "edit_last", "Edit last prompt"),
    ]

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self._config = (config if config is not None else load_config()).resolve_paths()
        self._scheduler = Scheduler(self._config.scheduler)
        self._agent: AgentCore | None = None
        self._engine: ContextEngine | None = None
        self._busy = False
        self._pending_messages: list[str] = []
        self._last_user_prompt: str = ""
        self._files_edited: int = 0
        self._plan_mode: bool = False
        self._router: ProviderRouter | None = None
        self._session_store: SessionStore | None = None
        self._event_store: EventStore | None = None
        self._cooldown_store: CooldownStore | None = None
        self._session_id: str | None = None
        self._gate: ApprovalGate | None = None
        self._tools: ToolExecutor | None = None

    @property
    def session_store(self) -> SessionStore | None:
        return self._session_store

    @property
    def active_session_id(self) -> str | None:
        return self._session_id

    def new_session(self, title: str = "") -> str:
        self._persist_current()
        state = AgentState()
        assert self._session_store is not None
        sid = self._session_store.create(title=title or "session", state=state)
        self._session_id = sid
        self._agent = self._build_agent(state)
        self._last_user_prompt = ""
        self._reset_transcript_ui()
        self._sync_footer()
        return sid

    def switch_session(self, session_id: str) -> bool:
        assert self._session_store is not None
        state = self._session_store.load_state(session_id)
        if state is None:
            return False
        self._persist_current()
        self._session_id = session_id
        self._session_store.set_meta("active_session_id", session_id)
        self._agent = self._build_agent(state)
        self._reset_transcript_ui()
        try:
            transcript = self.query_one("#transcript-pane", TranscriptPane)
            for turn in state.history[-12:]:
                if turn.role == "user":
                    transcript.write_user_message(turn.content)
                else:
                    transcript.write_agent_message(turn.content)
        except Exception:
            pass
        self._sync_footer()
        return True

    def delete_session(self, session_id: str) -> bool:
        if self._session_store is None:
            return False
        if session_id == self._session_id:
            self.new_session(title="session")
        try:
            self._session_store.delete_session(session_id)
            self._sync_footer()
            return True
        except Exception:
            log.exception("delete session failed")
            return False

    def load_last_prompt_into_composer(self) -> str:
        text = self._last_user_prompt or ""
        if not text and self._agent is not None:
            for turn in reversed(self._agent.state.history):
                if turn.role == "user":
                    text = turn.content
                    break
        if not text:
            return ""
        try:
            composer = self.query_one("#chat-input", FreeCodeComposer)
            composer.text = text
            composer.focus()
        except Exception:
            try:
                inp = self.query_one("#landing-input", Input)
                inp.value = text
                inp.focus()
            except Exception:
                pass
        return text

    def action_edit_last(self) -> None:
        if not self.load_last_prompt_into_composer():
            try:
                self.query_one("#transcript-pane", TranscriptPane).write_error_message(
                    "No previous prompt to edit. Tip: /edit or Ctrl+E"
                )
            except Exception:
                pass

    def compose(self) -> ComposeResult:
        yield MainLayout()

    def on_mount(self) -> None:
        for name in list_theme_names():
            self.register_theme(build_theme(name=name))
        start = preferred_theme_name()
        self.theme = start
        self.query_one("#landing-input").focus()
        self.set_interval(0.25, self._sync_cooldown_bar)

        db = self._config.paths.state_db
        self._session_store = SessionStore(db)
        self._event_store = EventStore(db)
        self._cooldown_store = CooldownStore(db)

        # Fresh session each launch — resume via /sessions
        state = AgentState()
        self._session_id = self._session_store.create(title="session", state=state)
        self._agent = self._build_agent(state)
        self._sync_footer()

    def on_unmount(self) -> None:
        self._persist_current()
        for store in (self._session_store, self._event_store, self._cooldown_store):
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass

    def _build_agent(self, state: AgentState | None = None) -> AgentCore:
        self._router = self._build_router()
        engine = ContextEngine(
            root=self._config.paths.project_dir,
            settings=self._config.context,
        )
        engine.refresh_index()
        self._engine = engine

        self._gate = ApprovalGate(
            self._config.approval,
            prompt_fn=None,
            coalescer=engine.coalescer,
        )
        self._gate.project_root = self._config.paths.project_dir
        self._tools = ToolExecutor(
            self._config.paths.project_dir,
            approval=self._config.approval,
            coalescer=engine.coalescer,
        )

        async def send(message: str):
            assert self._router is not None
            await self._scheduler.wait_until_ready()
            self._sync_cooldown_bar()
            chat = await self._router.send(message)
            # ApiFreeLLM needs 20–25s floor; Groq does not.
            apply_floor = self._router.active_name == "apifreellm"
            self._scheduler.record_success(
                chat.delay_seconds if apply_floor else 0.0,
                apply_floor=apply_floor,
            )
            self._sync_cooldown_bar()
            self._persist_cooldown()
            self._sync_footer()
            return chat

        return AgentCore(
            send=send,
            state=state if state is not None else AgentState(),
            build_prompt=engine.prompt_builder,
        )

    def _build_router(self) -> ProviderRouter:
        s = self._config.llm
        providers = []
        order = s.providers or ("apifreellm", "groq")
        pref_name, pref_model = self._load_provider_prefs()
        groq_model = pref_model or s.groq_model
        for name in order:
            if name == "apifreellm":
                providers.append(ApiFreeLLMProvider(s))
            elif name == "groq":
                providers.append(
                    GroqProvider(
                        api_keys=s.groq_api_keys,
                        model=groq_model,
                        timeout_seconds=s.timeout_seconds,
                    )
                )
        router = ProviderRouter(providers)
        if pref_name:
            router.force(pref_name)
        return router

    def _load_provider_prefs(self) -> tuple[str | None, str | None]:
        try:
            import tomllib
            from pathlib import Path

            path = Path(self._config.paths.runtime_dir) / "provider.toml"
            if not path.exists():
                return None, None
            with open(path, "rb") as f:
                data = tomllib.load(f)
            block = data.get("provider") or {}
            name = block.get("name") if isinstance(block.get("name"), str) else None
            model = block.get("model") if isinstance(block.get("model"), str) else None
            return name or None, model or None
        except Exception:
            return None, None

    async def _ask_approval(self, request: ApprovalRequest) -> bool:
        return await self.push_screen_wait(ApprovalModal(request))

    def action_interrupt(self) -> None:
        if self._agent is not None:
            self._agent.interrupt()
            try:
                self.query_one("#transcript-pane", TranscriptPane).write_error_message(
                    "Interrupt requested."
                )
            except Exception:
                pass

    def on_message_submitted(self, event: MessageSubmitted) -> None:
        self._handle_user_text(event.text)
        event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if text:
            self._handle_user_text(text)
        event.stop()

    def _handle_user_text(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return

        if self._busy:
            self._pending_messages.append(text)
            try:
                self.query_one("#transcript-pane", TranscriptPane).write_error_message(
                    f"Queued ({len(self._pending_messages)}) — will send after Cooking finishes."
                )
            except Exception:
                pass
            return

        layout = self.query_one(MainLayout)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        layout.start_conversation()

        cmd = try_handle_slash(self, text)
        if cmd.handled:
            transcript.write_user_message(text)
            if cmd.error:
                transcript.write_error_message(cmd.message)
            else:
                self.run_worker(
                    transcript.stream_agent_message(cmd.message), exclusive=False
                )
            return

        transcript.write_user_message(text)
        self._last_user_prompt = text

        if not (self._config.llm.api_keys or self._config.llm.groq_api_keys):
            self._busy = True
            self.run_worker(self._mock_reply(text), exclusive=True)
            return

        if self._agent is None:
            self._agent = self._build_agent()

        self._busy = True
        self.run_worker(self._live_reply(text), exclusive=True)

    async def _mock_reply(self, text: str) -> None:
        activity = self.query_one("#activity-indicator", ActivityIndicator)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        try:
            activity.set_activity("Mocking...")
            await transcript.stream_mock_reply(text)
        finally:
            activity.set_idle()
            self._busy = False
            self._flush_pending_messages()

    async def _live_reply(self, text: str) -> None:
        assert self._agent is not None
        activity = self.query_one("#activity-indicator", ActivityIndicator)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        try:
            activity.set_activity("Cooking...")
            assert self._tools is not None and self._gate is not None

            async def authorize(action) -> bool:
                req = self._gate.decide(action)
                if req.decision.value == "allow":
                    return True
                if req.decision.value == "deny":
                    return False
                activity.set_activity("Waiting for approval...")
                return await self._ask_approval(req)

            loop = AgentLoop(
                self._agent,
                self._tools,
                authorize=authorize,
                max_steps=5,
            )
            pinned = expand_mentions(self._config.paths.project_dir, text)
            send_text = text
            if pinned:
                send_text = text + "\n\n" + pinned
                await transcript.stream_agent_message(
                    "**Pinned context** from `@…` mentions (not sent as a separate turn)."
                )
            if self._tools is not None:
                self._tools.plan_mode = self._plan_mode
                self._tools.begin_action_batch()
            outcome = await loop.run_user_message(send_text)
            if self._tools is not None:
                self._tools.commit_undo_batch()

            for step in outcome.steps:
                result = step.turn
                if result.chat is None and result.error:
                    transcript.write_error_message(result.message)
                    continue
                reply = result.message or "(empty response)"
                activity.set_activity("Writing...")
                await transcript.stream_agent_message(reply)
                for tr in step.tool_results:
                    if tr.status == "denied":
                        transcript.write_error_message(f"Denied: {tr.error or tr.tool}")
                    elif tr.ok:
                        if tr.tool in ("edit", "apply_edit", "write_file") or (
                            tr.data and tr.data.get("path")
                        ):
                            if tr.mutating:
                                self._files_edited += 1
                                self._sync_footer()
                        out = (tr.output or "")[:800]
                        if out:
                            await transcript.stream_agent_message(
                                f"**Tool** `{tr.tool}`\n\n```\n{out}\n```"
                            )
                        else:
                            await transcript.stream_agent_message(
                                f"**Tool** `{tr.tool}` — ok"
                            )
                    else:
                        transcript.write_error_message(
                            f"Tool {tr.tool}: {tr.error or tr.status}"
                        )

            self._persist_current()
            if outcome.last is not None:
                log.debug(
                    "agent loop steps=%d reason=%s",
                    len(outcome.steps),
                    outcome.stopped_reason,
                )
        except LLMRateLimitError as exc:
            self._scheduler.record_rate_limit(exc.retry_after_seconds)
            transcript.write_error_message(
                f"Rate limited. Cooling down"
                f"{f' (~{exc.retry_after_seconds:.0f}s)' if exc.retry_after_seconds else ''}."
            )
            log.warning("rate limited: %s", exc)
        except LLMServerError as exc:
            self._scheduler.record_server_error()
            transcript.write_error_message(f"ApiFreeLLM server error: {exc}")
            log.warning("server error: %s", exc)
        except LLMError as exc:
            transcript.write_error_message(f"ApiFreeLLM error: {exc}")
            log.warning("llm error: %s", exc)
        except Exception as exc:  # noqa: BLE001
            transcript.write_error_message(f"Unexpected error: {exc}")
            log.exception("live reply failed")
        finally:
            activity.set_idle()
            self._busy = False
            self._sync_cooldown_bar()
            self._persist_cooldown()
            self._flush_pending_messages()

    def _flush_pending_messages(self) -> None:
        if not self._pending_messages or self._busy:
            return
        nxt = self._pending_messages.pop(0)
        self.call_later(self._handle_user_text, nxt)

    def _persist_current(self) -> None:
        if self._session_store is None or self._session_id is None or self._agent is None:
            return
        try:
            self._session_store.save_state(self._session_id, self._agent.state)
        except Exception:
            log.exception("failed to persist session")

    def _persist_cooldown(self) -> None:
        if self._cooldown_store is None or self._session_id is None:
            return
        try:
            snap = self._scheduler.snapshot()
            self._cooldown_store.save(
                self._session_id,
                mode=snap.mode.value,
                remaining_seconds=snap.remaining_seconds,
                total_seconds=snap.total_seconds,
            )
        except Exception:
            log.exception("failed to persist cooldown")

    def _sync_cooldown_bar(self) -> None:
        try:
            bar = self.query_one("#cooldown-bar", CooldownBar)
        except Exception:
            return
        snap = self._scheduler.snapshot()
        if snap.mode.value == "cooldown":
            bar.set_cooldown(snap.total_seconds, snap.remaining_seconds)
        elif snap.mode.value == "backoff":
            bar.set_backoff(snap.total_seconds, snap.remaining_seconds)
        else:
            bar.set_idle()

    def _reset_transcript_ui(self) -> None:
        try:
            layout = self.query_one(MainLayout)
            transcript = self.query_one("#transcript-pane", TranscriptPane)
            transcript.clear()
            layout.start_conversation()
        except Exception:
            pass

    def _sync_footer(self) -> None:
        try:
            footer = self.query_one("#footer-stats", FooterStats)
            sid = self._session_id or ""
            provider = self.active_provider() if self._router else ""
            model = self.active_model() if provider == "groq" else None
            if self._plan_mode:
                mode = "plan"
            elif provider == "groq" and model:
                mode = f"groq/{model.split('/')[-1][:18]}"
            elif provider:
                mode = provider
            else:
                mode = "freecode"
            footer.set_stats(
                mode_label=mode,
                session_label=sid[:8] if sid else "",
                files_edited=self._files_edited,
            )
        except Exception:
            pass

    def toggle_plan_mode(self) -> bool:
        self._plan_mode = not self._plan_mode
        if self._tools is not None:
            self._tools.plan_mode = self._plan_mode
        self._sync_footer()
        return self._plan_mode

    def undo_last_tools(self) -> str:
        if self._tools is None:
            return "Tools not ready."
        result = self._tools.undo_last_batch()
        if result.ok:
            self._files_edited = max(0, self._files_edited - 1)
            self._sync_footer()
        return result.output or result.error or ("ok" if result.ok else "failed")

    def set_theme_name(self, name: str) -> bool:
        names = list_theme_names()
        if name not in names:
            return False
        theme = build_theme(name=name)
        self.register_theme(theme)
        self.theme = name
        try:
            persist_theme_name(name)
        except Exception:
            log.exception("failed to persist theme name")
        return True

    def set_provider_name(self, name: str) -> bool:
        if self._router is None:
            self._router = self._build_router()
        ok = self._router.force(name)
        if ok:
            self._sync_footer()
        return ok

    def list_providers(self) -> list[str]:
        if self._router is None:
            self._router = self._build_router()
        return self._router.names()

    def active_provider(self) -> str:
        if self._router is None:
            return "none"
        return self._router.active_name

    def set_model_name(self, model: str) -> bool:
        if self._router is None:
            self._router = self._build_router()
        ok = self._router.set_model(model)
        if ok:
            self._persist_provider_prefs()
            self._sync_footer()
        return ok

    def active_model(self) -> str | None:
        if self._router is None:
            return None
        return self._router.active_model()

    def _persist_provider_prefs(self) -> None:
        try:
            from pathlib import Path
            path = Path(self._config.paths.runtime_dir) / "provider.toml"
            path.parent.mkdir(parents=True, exist_ok=True)
            model = self.active_model() or ""
            provider = self.active_provider()
            path.write_text(
                f'[provider]\nname = "{provider}"\nmodel = "{model}"\n',
                encoding="utf-8",
            )
        except Exception:
            log.exception("failed to persist provider prefs")


def run_tui(config: Config | None = None) -> int:
    FreeCodeApp(config=config).run()
    return 0
