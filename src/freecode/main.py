"""
FreeCode entry point.

Phase 0 (Foundation): this just proves the package installs and the console
script (`freecode`) is wired up correctly. It has no real behavior yet.

Phase 1 (TUI shell) replaces the body of `run()` with launching the Textual
app. Nothing outside this function should need to change when that happens -
`run()` is the single entry point the console script calls.
"""
from __future__ import annotations

from freecode import __version__


def run() -> int:
    """Console-script entry point. Returns a process exit code."""
    print(f"freecode {__version__} - foundation phase (ph-00)")
    print("No TUI yet - that's ph-01. This just confirms the package works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
