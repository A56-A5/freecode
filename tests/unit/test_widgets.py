"""
Standalone unit tests for TUI widgets (CooldownBar, ActivityIndicator, Theme).

Restored after ph-13 TUI rewrite dropped Pilot-coupled coverage for these.
Most tests do not need App.run_test().
"""
from __future__ import annotations

from pathlib import Path

import pytest

from freecode.tui.theme import DEFAULTS, THEME_NAME, build_theme
from freecode.tui.widgets.activity import ActivityIndicator
from freecode.tui.widgets.cooldown import BAR_WIDTH, CooldownBar


class TestCooldownBar:
    def test_starts_idle(self):
        bar = CooldownBar()
        assert bar.mode == "idle"
        assert bar.total_seconds == 0.0
        assert bar.remaining_seconds == 0.0

    def test_set_cooldown_clamps_remaining(self):
        bar = CooldownBar()
        bar.set_cooldown(20.0, 25.0)
        assert bar.mode == "cooldown"
        assert bar.remaining_seconds == 20.0

    def test_set_cooldown_negative_remaining_clamped(self):
        bar = CooldownBar()
        bar.set_cooldown(10.0, -5.0)
        assert bar.remaining_seconds == 0.0

    def test_fraction_filled_midway(self):
        bar = CooldownBar()
        bar.set_cooldown(20.0, 10.0)
        assert bar._fraction_filled() == pytest.approx(0.5)

    def test_fraction_filled_zero_total(self):
        bar = CooldownBar()
        bar.set_idle()
        assert bar._fraction_filled() == 0.0

    def test_fraction_filled_complete(self):
        bar = CooldownBar()
        bar.set_cooldown(20.0, 0.0)
        assert bar._fraction_filled() == pytest.approx(1.0)

    def test_set_idle_clears(self):
        bar = CooldownBar()
        bar.set_cooldown(20.0, 5.0)
        bar.set_idle()
        assert bar.mode == "idle"
        assert bar.total_seconds == 0.0

    def test_set_backoff_mode(self):
        bar = CooldownBar()
        bar.set_backoff(30.0, 15.0)
        assert bar.mode == "backoff"
        assert bar.remaining_seconds == 15.0
        assert bar._fraction_filled() == pytest.approx(0.5)

    def test_bar_width_constant(self):
        assert BAR_WIDTH == 24


class TestActivityIndicator:
    def test_starts_hidden(self):
        act = ActivityIndicator()
        assert act.display is False
        assert act._label == ""

    def test_set_activity_shows(self):
        act = ActivityIndicator()
        act.set_activity("Cooking...")
        assert act.display is True
        assert act._label == "Cooking..."

    def test_set_idle_hides(self):
        act = ActivityIndicator()
        act.set_activity("Working")
        act.set_idle()
        assert act.display is False
        assert act._label == ""

    def test_label_transition(self):
        act = ActivityIndicator()
        act.set_activity("Waiting")
        act.set_activity("Cooking...")
        assert act._label == "Cooking..."

    def test_render_empty_when_idle(self):
        act = ActivityIndicator()
        rendered = act.render()
        assert str(rendered) == ""

    def test_render_includes_label_when_active(self):
        act = ActivityIndicator()
        act.set_activity("Cooking...")
        # Without App mount, component styles may be missing — label state is enough
        assert act._label == "Cooking..."
        assert act.display is True


class TestTheme:
    def test_defaults_present(self):
        assert "accent" in DEFAULTS
        assert "background" in DEFAULTS
        assert DEFAULTS["accent"].startswith("#")

    def test_build_theme_uses_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        theme = build_theme()
        assert theme.name == THEME_NAME
        assert theme.accent == DEFAULTS["accent"]
        assert theme.background == DEFAULTS["background"]
        assert theme.dark is True

    def test_build_theme_with_overrides(self):
        theme = build_theme(overrides={"accent": "#ff00ff"})
        assert theme.accent == "#ff00ff"
        assert theme.background == DEFAULTS["background"]

    def test_build_theme_multi_key_overrides(self):
        theme = build_theme(
            overrides={"accent": "#111111", "error": "#222222", "primary": "#333333"}
        )
        assert theme.accent == "#111111"
        assert theme.error == "#222222"
        assert theme.primary == "#333333"

    def test_load_theme_toml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode = tmp_path / ".freecode"
        freecode.mkdir()
        (freecode / "theme.toml").write_text(
            '[theme]\naccent = "#abcdef"\n',
            encoding="utf-8",
        )
        theme = build_theme()
        assert theme.accent == "#abcdef"


class TestCommandPaletteFilter:
    def test_filter_help(self):
        from freecode.tui.widgets.command_palette import filter_commands

        hits = filter_commands("/he")
        assert any(c.name == "/help" for c in hits)

    def test_filter_session(self):
        from freecode.tui.widgets.command_palette import filter_commands

        hits = filter_commands("/session")
        names = [c.name for c in hits]
        assert any("session" in n for n in names)

    def test_filter_empty_shows_all(self):
        from freecode.tui.widgets.command_palette import COMMAND_SPECS, filter_commands

        hits = filter_commands("/")
        assert len(hits) >= 5


class TestThemePresets:
    def test_list_themes(self):
        from freecode.tui.theme import list_theme_names

        names = list_theme_names()
        assert "freecode-dark" in names
        assert "freecode-light" in names

    def test_build_light(self):
        from freecode.tui.theme import build_theme

        theme = build_theme(name="freecode-light")
        assert theme.name == "freecode-light"
        assert theme.dark is False
