"""
tui.theme - FreeCode's color theme, built on Textual's native Theme API.

This is real configurability, not hardcoded hex values sprinkled through
.tcss files: Theme.variables (primary, accent, success, background, ...)
become Textual CSS variables ($primary, $accent, ...) automatically once
registered, and every widget's DEFAULT_CSS in this package references
those variables instead of literal colors.

Users override the palette by creating `.freecode/theme.toml` in their
project (see config/theme.toml for the template with every key). Missing
keys fall back to DEFAULTS - a partial override (e.g. just `accent`) is
valid and expected.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from textual.theme import Theme

THEME_NAME = "freecode-dark"
APP_TITLE = "FreeCode"

# Dark, low-chrome palette in the spirit of Claude Code / opencode: near-
# black background, muted foreground, a single accent color used for both
# "success" and "the model is doing something" (the activity dot, the
# cooldown bar fill) so the UI doesn't juggle multiple "good" colors.
DEFAULTS: dict[str, str] = {
    "primary": "#5f87ff",
    "secondary": "#3a3a3a",
    "accent": "#00d787",
    "success": "#00d787",
    "warning": "#ffaf00",
    "error": "#ff5f5f",
    "background": "#0c0c0c",
    "surface": "#131313",
    "panel": "#1e1e1e",
    "foreground": "#d4d4d4",
}

USER_THEME_PATH = Path(".freecode") / "theme.toml"


def _load_user_overrides(path: Path = USER_THEME_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data.get("theme", {})


def build_theme(overrides: dict[str, str] | None = None) -> Theme:
    """
    Builds the registered Theme. `overrides` is exposed as a parameter
    (rather than always reading the file) so tests can inject a palette
    without touching the filesystem.
    """
    values = {**DEFAULTS, **(overrides if overrides is not None else _load_user_overrides())}
    return Theme(
        name=THEME_NAME,
        primary=values["primary"],
        secondary=values["secondary"],
        accent=values["accent"],
        success=values["success"],
        warning=values["warning"],
        error=values["error"],
        background=values["background"],
        surface=values["surface"],
        panel=values["panel"],
        foreground=values["foreground"],
        dark=True,
    )
