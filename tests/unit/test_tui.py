"""
Phase 1 (TUI shell) tests — landing → conversation flow.

Uses Textual's headless Pilot (App.run_test()).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from freecode.config.settings import Config, PathSettings
from freecode.tui.app import FreeCodeApp
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import DEFAULTS, build_theme
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats
from freecode.tui.widgets.input import FreeCodeComposer, MessageSubmitted


@pytest.fixture
def app_config(tmp_path: Path) -> Config:
    """Isolated config so on_mount SQLite never hits a bad path."""
    cfg = Config(
        paths=PathSettings(
            project_dir=tmp_path,
            runtime_dir=tmp_path / ".freecode",
            state_db=tmp_path / ".freecode" / "state.db",
            log_file=tmp_path / ".freecode" / "logs" / "freecode.log",
        )
    )
    return cfg.resolve_paths(tmp_path)


def _app(cfg: Config) -> FreeCodeApp:
    return FreeCodeApp(config=cfg)


@pytest.mark.asyncio
async def test_app_composes_landing_and_conversation_widgets(app_config: Config):
    app = _app(app_config)
    async with app.run_test():
        assert app.query_one("#landing-input") is not None
        assert app.query_one("#transcript-pane", TranscriptPane) is not None
        assert app.query_one("#activity-indicator", ActivityIndicator) is not None
        assert app.query_one("#chat-input", FreeCodeComposer) is not None
        assert app.query_one("#cooldown-bar", CooldownBar) is not None
        assert app.query_one("#footer-stats", FooterStats) is not None


@pytest.mark.asyncio
async def test_old_diff_and_commands_panes_are_gone(app_config: Config):
    app = _app(app_config)
    async with app.run_test():
        assert len(app.query("#diff-pane")) == 0
        assert len(app.query("#commands-pane")) == 0
        assert len(app.query("#transcript-log")) == 0


@pytest.mark.asyncio
async def test_landing_input_is_focused_on_start(app_config: Config):
    app = _app(app_config)
    async with app.run_test():
        assert app.focused is not None
        assert app.focused.id == "landing-input"


@pytest.mark.asyncio
async def test_message_submitted_starts_conversation(app_config: Config):
    app = _app(app_config)
    async with app.run_test() as pilot:
        conversation = app.query_one("#conversation")
        app.post_message(MessageSubmitted("hello from test"))
        await pilot.pause()
        transcript = app.query_one("#transcript-pane", TranscriptPane)
        assert len(list(transcript.children)) >= 1
        assert conversation.display is not False


@pytest.mark.asyncio
async def test_empty_message_is_ignored(app_config: Config):
    app = _app(app_config)
    async with app.run_test() as pilot:
        before = len(list(app.query_one("#transcript-pane", TranscriptPane).children))
        app.post_message(MessageSubmitted("   "))
        await pilot.pause()
        after = len(list(app.query_one("#transcript-pane", TranscriptPane).children))
        assert after == before


@pytest.mark.asyncio
async def test_activity_indicator_starts_idle(app_config: Config):
    app = _app(app_config)
    async with app.run_test():
        activity = app.query_one("#activity-indicator", ActivityIndicator)
        assert activity.display is False


@pytest.mark.asyncio
async def test_cooldown_bar_present(app_config: Config):
    app = _app(app_config)
    async with app.run_test():
        assert app.query_one("#cooldown-bar", CooldownBar) is not None


class TestThemeBuilder:
    def test_build_theme_without_user_file_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        theme = build_theme()
        assert theme.accent == DEFAULTS["accent"]
        assert theme.background == DEFAULTS["background"]
        assert theme.foreground == DEFAULTS["foreground"]
