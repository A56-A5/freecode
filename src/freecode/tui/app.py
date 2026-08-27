"""
tui.app - the FreeCode Textual application.

Live path: user message -> Scheduler.wait_until_ready ->
ApiFreeLLMClient.send -> repair_response -> streamed transcript reveal.

Falls back to mock replies when no API key is configured.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input

from freecode.config import Config, get_logger, load_config
from freecode.domain.errors import LLMError, LLMRateLimitError, LLMServerError
from freecode.llm import ApiFreeLLMClient, Scheduler, repair_response
from freecode.tui.layout import MainLayout
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import APP_TITLE, build_theme
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.input import MessageSubmitted

log = get_logger(__name__)


class FreeCodeApp(App):
    CSS_PATH = Path(__file__).parent / "app.tcss"
    TITLE = APP_TITLE
    BINDINGS = [("ctrl+c", "quit", "Quit")]

    def __init__(self, config: Config | None = None) -> None:
        super().__init__()
        self._config = config if config is not None else load_config()
        self._scheduler = Scheduler(self._config.scheduler)
        self._busy = False

    def compose(self) -> ComposeResult:
        yield MainLayout()

    def on_mount(self) -> None:
        theme = build_theme()
        self.register_theme(theme)
        self.theme = theme.name
        self.query_one("#landing-input").focus()
        self.set_interval(0.25, self._sync_cooldown_bar)

    def on_message_submitted(self, event: MessageSubmitted) -> None:
        """Landing Input and conversation TextArea both post this."""
        self._handle_user_text(event.text)
        event.stop()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        # Back-compat if something still uses bare Input.Submitted.
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
        transcript.write_user_message(text)

        if not self._config.llm.api_key:
            self._busy = True
            self.run_worker(self._mock_reply(text), exclusive=True)
            return

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
        activity = self.query_one("#activity-indicator", ActivityIndicator)
        transcript = self.query_one("#transcript-pane", TranscriptPane)
        try:
            activity.set_activity("Waiting for slot...")
            await self._scheduler.wait_until_ready()
            self._sync_cooldown_bar()

            activity.set_activity("Cooking...")
            async with ApiFreeLLMClient(self._config.llm) as client:
                chat = await client.send(text)

            self._scheduler.record_success(chat.delay_seconds)
            agent = repair_response(chat.text)
            reply = agent.message or chat.text or "(empty response)"

            activity.set_activity("Writing...")
            await transcript.stream_agent_message(reply)
            log.debug(
                "live reply ok fallback=%s status=%s actions=%d",
                agent.fallback,
                agent.status,
                len(agent.actions),
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
    """Launches the interactive TUI. Called from freecode.main.run()."""
    FreeCodeApp(config=config).run()
    return 0
