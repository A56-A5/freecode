"""
tui.theme - FreeCode color themes (named presets + live switch).
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from textual.theme import Theme

THEME_NAME = "freecode-dark"
APP_TITLE = "FreeCode"

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

PRESETS: dict[str, dict[str, str]] = {
    "freecode-dark": {**DEFAULTS},
    "freecode-light": {
        "primary": "#3b5bdb",
        "secondary": "#adb5bd",
        "accent": "#0ca678",
        "success": "#0ca678",
        "warning": "#f08c00",
        "error": "#e03131",
        "background": "#f8f9fa",
        "surface": "#ffffff",
        "panel": "#e9ecef",
        "foreground": "#212529",
    },
    "freecode-hc": {  # high contrast
        "primary": "#ffff00",
        "secondary": "#888888",
        "accent": "#00ff00",
        "success": "#00ff00",
        "warning": "#ffaa00",
        "error": "#ff0000",
        "background": "#000000",
        "surface": "#000000",
        "panel": "#111111",
        "foreground": "#ffffff",
    },
}

USER_THEME_PATH = Path(".freecode") / "theme.toml"


def list_theme_names() -> list[str]:
    return sorted(PRESETS.keys())


def _load_user_overrides(path: Path = USER_THEME_PATH) -> dict[str, str]:
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    # Support [theme] name = "..." and/or color keys
    block = data.get("theme", {})
    return {k: v for k, v in block.items() if k != "name" and isinstance(v, str)}


def preferred_theme_name(path: Path = USER_THEME_PATH) -> str:
    if path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        name = data.get("theme", {}).get("name")
        if isinstance(name, str) and name in PRESETS:
            return name
    return THEME_NAME


def build_theme(
    name: str | None = None,
    overrides: dict[str, str] | None = None,
) -> Theme:
    """
    Build a Theme. `name` picks a preset; `overrides` merge on top
    (or load `.freecode/theme.toml` when overrides is None).
    """
    preset_name = name or preferred_theme_name()
    base = dict(PRESETS.get(preset_name, DEFAULTS))
    if overrides is not None:
        base.update(overrides)
    else:
        base.update(_load_user_overrides())
    dark = preset_name != "freecode-light"
    return Theme(
        name=preset_name,
        primary=base["primary"],
        secondary=base["secondary"],
        accent=base["accent"],
        success=base["success"],
        warning=base["warning"],
        error=base["error"],
        background=base["background"],
        surface=base["surface"],
        panel=base["panel"],
        foreground=base["foreground"],
        dark=dark,
    )
