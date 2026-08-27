"""
FreeCode entry point.

ph-00 Foundation: package installs, console script works.
ph-01 TUI shell: launches the mocked Textual app.
ph-02 Configuration + logging: load config and set up structured logging
before the TUI starts. Agent/LLM/scheduler/MCP still land in later phases.
"""
from __future__ import annotations

from freecode.config import get_logger, load_config, setup_logging


def run() -> int:
    """Console-script entry point. Returns a process exit code."""
    config = load_config()
    setup_logging(config)
    log = get_logger("main")
    log.debug(
        "config loaded endpoint=%s model=%s cooldown_floor=%.1fs "
        "token_budget=%d policy=%s",
        config.llm.endpoint,
        config.llm.model,
        config.scheduler.cooldown_floor_seconds,
        config.context.token_budget,
        config.approval.default_policy,
    )
    if config.llm.api_key:
        log.debug("API key present (from environment)")
    else:
        log.debug("no API key in environment (not required until ph-03)")

    from freecode.tui.app import run_tui

    return run_tui()


if __name__ == "__main__":
    raise SystemExit(run())
