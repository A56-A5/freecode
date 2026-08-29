"""
FreeCode entry point.

ph-00 Foundation: package installs, console script works.
ph-01 TUI shell: launches the Textual app.
ph-02 Configuration + logging.
ph-03..05: client, scheduler, repair — TUI can use live ApiFreeLLM when
FREECODE_API_KEY / APIFREELLM_API_KEY is set; otherwise mock replies.
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
    if config.llm.api_keys or config.llm.groq_api_keys:
        log.info("live ApiFreeLLM mode (API key present)")
    else:
        log.warning("no API key — set FREECODE_API_KEY or GROQ_API_KEY")

    from freecode.tui.app import run_tui

    return run_tui(config)


if __name__ == "__main__":
    raise SystemExit(run())
