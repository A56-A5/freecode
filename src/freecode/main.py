"""
FreeCode entry point.

ph-00 (Foundation) proved the package installs and the console script
works. ph-01 (TUI shell) replaces the placeholder body below with
launching the real Textual app - the permanent layout and theme exist
now, but nothing behind it (agent/LLM/scheduler/MCP) does yet; those
land ph-03 through ph-07.
"""
from __future__ import annotations


def run() -> int:
    """Console-script entry point. Returns a process exit code."""
    from freecode.tui.app import run_tui

    return run_tui()


if __name__ == "__main__":
    raise SystemExit(run())
