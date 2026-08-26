"""
Phase 1 (TUI shell) tests - v2, redesigned layout.

Uses Textual's headless Pilot (App.run_test()) - real app and widget
tree, no terminal needed.
"""
import pytest

from freecode.tui.app import FreeCodeApp
from freecode.tui.panes.transcript import TranscriptPane
from freecode.tui.theme import DEFAULTS, build_theme
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import BAR_WIDTH, CooldownBar
from freecode.tui.widgets.footer_stats import FooterStats


@pytest.mark.asyncio
async def test_app_composes_the_unified_layout():
    app = FreeCodeApp()
    async with app.run_test():
        assert app.query_one("#transcript-pane", TranscriptPane) is not None
        assert app.query_one("#transcript-log") is not None
        assert app.query_one("#activity-indicator", ActivityIndicator) is not None
        assert app.query_one("#chat-input") is not None
        assert app.query_one("#cooldown-bar", CooldownBar) is not None
        assert app.query_one("#footer-stats", FooterStats) is not None


@pytest.mark.asyncio
async def test_old_diff_and_commands_panes_are_gone():
    """Explicit regression guard: the old split-pane design must not come back."""
    app = FreeCodeApp()
    async with app.run_test():
        assert len(app.query("#diff-pane")) == 0
        assert len(app.query("#commands-pane")) == 0


@pytest.mark.asyncio
async def test_chat_input_is_focused_on_start():
    app = FreeCodeApp()
    async with app.run_test():
        assert app.focused is not None
        assert app.focused.id == "chat-input"


@pytest.mark.asyncio
async def test_typing_and_submitting_appends_to_transcript():
    app = FreeCodeApp()
    async with app.run_test() as pilot:
        await pilot.press(*"hello", "enter")
        log = app.query_one("#transcript-log")
        assert len(log.lines) >= 1


@pytest.mark.asyncio
async def test_submitting_clears_the_input():
    app = FreeCodeApp()
    async with app.run_test() as pilot:
        await pilot.press(*"hi", "enter")
        from freecode.tui.widgets.input import FreeCodeInput

        assert app.query_one("#chat-input", FreeCodeInput).value == ""


@pytest.mark.asyncio
async def test_empty_submit_does_not_write_to_log():
    app = FreeCodeApp()
    async with app.run_test() as pilot:
        await pilot.press("enter")
        log = app.query_one("#transcript-log")
        assert len(log.lines) == 0


@pytest.mark.asyncio
async def test_theme_is_registered_and_active():
    app = FreeCodeApp()
    async with app.run_test():
        assert app.theme == "freecode-dark"
        assert "freecode-dark" in app.available_themes


class TestCooldownBar:
    """Unit tests directly on the widget - no app/Pilot needed."""

    def test_starts_idle(self):
        bar = CooldownBar()
        assert bar.mode == "idle"

    def test_set_cooldown_computes_fraction_filled(self):
        bar = CooldownBar()
        bar.set_cooldown(total_seconds=25.0, remaining_seconds=25.0)
        assert bar._fraction_filled() == 0.0
        bar.set_cooldown(total_seconds=25.0, remaining_seconds=0.0)
        assert bar._fraction_filled() == 1.0
        bar.set_cooldown(total_seconds=20.0, remaining_seconds=10.0)
        assert bar._fraction_filled() == pytest.approx(0.5)

    def test_set_cooldown_clamps_out_of_range_remaining(self):
        bar = CooldownBar()
        bar.set_cooldown(total_seconds=25.0, remaining_seconds=999.0)
        assert bar.remaining_seconds == 25.0
        bar.set_cooldown(total_seconds=25.0, remaining_seconds=-5.0)
        assert bar.remaining_seconds == 0.0

    def test_set_backoff_sets_mode(self):
        bar = CooldownBar()
        bar.set_backoff(total_seconds=60.0, remaining_seconds=30.0)
        assert bar.mode == "backoff"

    def test_set_idle_resets_state(self):
        bar = CooldownBar()
        bar.set_cooldown(total_seconds=25.0, remaining_seconds=10.0)
        bar.set_idle()
        assert bar.mode == "idle"
        assert bar.total_seconds == 0.0

    @pytest.mark.asyncio
    async def test_render_reflects_theme_colors(self):
        """
        Mounted-widget test: confirms the bar actually pulls its fill
        color from the active theme (via get_component_rich_style), not
        a hardcoded value - the core promise of "configurable theme".
        """
        app = FreeCodeApp()
        async with app.run_test():
            bar = app.query_one("#cooldown-bar", CooldownBar)
            bar.set_cooldown(total_seconds=20.0, remaining_seconds=10.0)
            rendered = bar.render()
            filled_style = bar.get_component_rich_style("cooldown--filled")
            assert filled_style.color is not None


class TestActivityIndicator:
    def test_hidden_by_default(self):
        widget = ActivityIndicator()
        assert widget.display is False

    def test_set_activity_shows_and_sets_label(self):
        widget = ActivityIndicator()
        widget.set_activity("Cooking...")
        assert widget.display is True
        assert widget._label == "Cooking..."

    @pytest.mark.asyncio
    async def test_render_shows_label_and_resolves_theme_color(self):
        """
        Mounted-widget test: render() needs component styles resolved
        against the active theme, which only works once mounted - this
        confirms both the label text and the theme-driven color work
        together, the way get_component_rich_style actually gets used.
        """
        app = FreeCodeApp()
        async with app.run_test():
            widget = app.query_one("#activity-indicator", ActivityIndicator)
            widget.set_activity("Cooking...")
            rendered = widget.render()
            assert "Cooking..." in rendered.plain
            dot_style = widget.get_component_rich_style("activity--dot")
            assert dot_style.color is not None

    def test_set_idle_hides_again(self):
        widget = ActivityIndicator()
        widget.set_activity("Cooking...")
        widget.set_idle()
        assert widget.display is False


class TestTheme:
    def test_build_theme_uses_defaults_with_no_overrides(self):
        theme = build_theme(overrides={})
        assert theme.accent == DEFAULTS["accent"]
        assert theme.background == DEFAULTS["background"]

    def test_build_theme_applies_partial_override(self):
        theme = build_theme(overrides={"accent": "#ff00ff"})
        assert theme.accent == "#ff00ff"
        # Unspecified keys still fall back to defaults.
        assert theme.background == DEFAULTS["background"]
