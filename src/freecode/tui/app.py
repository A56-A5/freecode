"""
tui.app - FreeCode Textual application.

Live path: slash commands | AgentCore → stream reply → approval modal for
mutating actions → ToolExecutor. Sessions persist via SQLite.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input

from freecode.agent import AgentCore
from freecode.config import Config, get_logger, load_config
from freecode.context import ContextEngine
from freecode.domain.errors import LLMError, LLMRateLimitError, LLMServerError
from freecode.domain.state import AgentPhase, AgentState
from freecode.llm import ApiFreeLLMClient, Scheduler
from freecode.security import ApprovalGate, ApprovalRequest
from freecode.storage import CooldownStore, EventStore, SessionStore
from freecode.tools import ToolExecutor
from freecode.tui.commands import try_handle_slash
from freecode.tui.layout import MainLayout
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import APP_TITLE, build_theme
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.approval import ApprovalModal
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.input import MessageSubmitted

log = get_logger(__name__)


class FreeCodeApp(App):
    CSS_PATH = Path(__file__).parent / "app.tcss"
    TITLE = APP_TITLE
    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+x", "interrupt", "Interrupt"),
    ]

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self._config = (config if config is not None else load_config()).resolve_paths()
        self._scheduler = Scheduler(self._config.scheduler)
        self._agent: AgentCore | None = None
        self._engine: ContextEngine | None = None
        self._busy = False
        self._session_store: SessionStore | None = None
        self._event_store: EventStore | None = None
        self._cooldown_store: CooldownStore | None = None
        self._session_id: str | None = None
        self._gate: ApprovalGate | None = None
        self._tools: ToolExecutor | None = None
        self._pending_prompt: ApprovalRequest | None = None
        self._prompt_result: bool | None = None

    # ── session API used by slash commands ───────────────────────────

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
        sid = self._session_store.create(title=title, state=state)
        self._session_id = sid
        self._agent = self._build_agent(state)
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
        return True

    def compose(self) -> ComposeResult:
        yield MainLayout()

    def on_mount(self) -> None:
        theme = build_theme()
        self.register_theme(theme)
        self.theme = theme.name
        self.query_one("#landing-input").focus()
        self.set_interval(0.25, self._sync_cooldown_bar)

        db = self._config.paths.state_db
        self._session_store = SessionStore(db)
        self._event_store = EventStore(db)
        self._cooldown_store = CooldownStore(db)

        active = self._session_store.active_session_id()
        state = self._session_store.load_state(active) if active else None
        if active and state is not None:
            self._session_id = active
        else:
            self._session_id = self._session_store.create(title="default")
            state = AgentState()

        self._agent = self._build_agent(state)

    def on_unmount(self) -> None:
        self._persist_current()
        for store in (self._session_store, self._event_store, self._cooldown_store):
            if store is not None:
                try:
                    store.close()
                except Exception:
                    pass

    def _build_agent(self, state: AgentState | None = None) -> AgentCore:
        client = ApiFreeLLMClient(self._config.llm)
        engine = ContextEngine(
            root=self._config.paths.project_dir,
            settings=self._config.context,
        )
        engine.refresh_index()
        self._engine = engine

        self._gate = ApprovalGate(
            self._config.approval,
            prompt_fn=self._sync_approval_prompt,
            coalescer=engine.coalescer,
        )
        self._tools = ToolExecutor(
            self._config.paths.project_dir,
            approval=self._config.approval,
            coalescer=engine.coalescer,
        )

        async def send(message: str):
            await self._scheduler.wait_until_ready()
            self._sync_cooldown_bar()
            async with client:
                chat = await client.send(message)
            self._scheduler.record_success(chat.delay_seconds)
            self._sync_cooldown_bar()
            self._persist_cooldown()
            return chat

        return AgentCore(
            send=send,
            state=state if state is not None else AgentState(),
            build_prompt=engine.prompt_builder,
        )

    def _sync_approval_prompt(self, request: ApprovalRequest) -> bool:
        """
        Blocking prompt from worker thread context is awkward in Textual;
        we use a flag + call_from_thread pattern via push_screen_wait in async path instead.
        For ApprovalGate.authorize used from async tool runner, prefer async_approve.
        """
        # Fallback when called outside async UI path: deny (safe).
        if self._prompt_result is not None:
            return self._prompt_result
        return False

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
        if not text or self._busy:
            return

        layout = self.query_one(MainLayout)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        layout.start_conversation()

        # Slash commands (no LLM)
        cmd = try_handle_slash(self, text)
        if cmd.handled:
            transcript.write_user_message(text)
            if cmd.error:
                transcript.write_error_message(cmd.message)
            else:
                # help/sessions render as agent-style markdown
                self.run_worker(transcript.stream_agent_message(cmd.message), exclusive=False)
            return

        transcript.write_user_message(text)

        if not self._config.llm.api_key:
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

    async def _live_reply(self, text: str) -> None:
        assert self._agent is not None
        activity = self.query_one("#activity-indicator", ActivityIndicator)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        try:
            activity.set_activity("Cooking...")
            result = await self._agent.handle_user_message(text)

            if result.chat is None and result.error:
                transcript.write_error_message(result.message)
                return

            reply = result.message or "(empty response)"
            activity.set_activity("Writing...")
            await transcript.stream_agent_message(reply)

            # Run proposed actions with approval modal
            if result.response.actions and self._tools is not None and self._gate is not None:
                await self._run_actions(result.response.actions, transcript, activity)

            self._persist_current()
            log.debug(
                "agent turn phase=%s fallback=%s actions=%d",
                result.phase.value,
                result.response.fallback,
                len(result.response.actions),
            )
        except LLMRateLimitError as exc:
            self._scheduler.record_rate_limit(exc.retry_after_seconds)
            transcript.write_error_message(
                f"Rate limited by ApiFreeLLM. Cooling down"
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

    async def _run_actions(self, actions, transcript: TranscriptPane, activity: ActivityIndicator) -> None:
        assert self._tools is not None and self._gate is not None
        for action in actions:
            req = self._gate.decide(action)
            approved = True
            if req.decision.value == "prompt":
                activity.set_activity("Waiting for approval...")
                approved = await self._ask_approval(req)
                if self._engine is not None:
                    from freecode.domain.events import approval_result_event
                    self._engine.coalescer.emit(
                        approval_result_event(approved, req.summary)
                    )
            elif req.decision.value == "deny":
                approved = False

            if not approved:
                transcript.write_error_message(f"Denied: {req.summary}")
                continue

            activity.set_activity(f"Running: {req.summary[:40]}...")
            # ToolExecutor also checks policy; pass approved=True after gate
            result = await self._tools.execute_action(action, approved=True)
            if result.ok:
                out = (result.output or "")[:500]
                if out:
                    await transcript.stream_agent_message(f"**Tool** `{result.tool}`\n\n```\n{out}\n```")
                else:
                    await transcript.stream_agent_message(f"**Tool** `{result.tool}` — ok")
            else:
                transcript.write_error_message(
                    f"Tool {result.tool}: {result.error or result.status}"
                )
            if self._session_id and self._event_store and self._engine:
                drained = self._engine.coalescer.peek()
                if drained:
                    self._event_store.append_many(self._session_id, drained)

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


def run_tui(config: Config | None = None) -> int:
    FreeCodeApp(config=config).run()
    return 0
