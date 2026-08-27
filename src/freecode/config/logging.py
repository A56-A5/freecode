"""
config.logging - structured application logging for FreeCode.

Configures the root `freecode` logger once per process. Safe to call
multiple times; subsequent calls with the same settings are no-ops,
and a force=True reconfigure replaces handlers.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from freecode.config.settings import Config, LoggingSettings

LOGGER_NAME = "freecode"
_CONFIGURED_KEY = "_freecode_logging_configured"


class JSONFormatter(logging.Formatter):
    """One JSON object per line — suitable for log shipping."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        # Attach any extra non-standard attributes callers may have set.
        for key, value in record.__dict__.items():
            if key in (
                "name",
                "msg",
                "args",
                "levelname",
                "levelno",
                "pathname",
                "filename",
                "module",
                "exc_info",
                "exc_text",
                "stack_info",
                "lineno",
                "funcName",
                "created",
                "msecs",
                "relativeCreated",
                "thread",
                "threadName",
                "processName",
                "process",
                "message",
                "taskName",
            ):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except (TypeError, ValueError):
                payload[key] = repr(value)
        return json.dumps(payload, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Compact human-readable format for the terminal."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )


def _level_from_name(name: str) -> int:
    level = logging.getLevelNamesMapping().get(name.upper())
    if level is None:
        return logging.INFO
    return level


def setup_logging(
    settings: LoggingSettings | Config,
    *,
    log_file: Path | None = None,
    force: bool = False,
    stream: Any | None = None,
) -> logging.Logger:
    """
    Configure the `freecode` logger.

    Args:
        settings: LoggingSettings, or a full Config (uses .logging and
            .paths.log_file when to_file is set).
        log_file: Explicit log file path. Overrides Config.paths.log_file
            when provided.
        force: Replace existing handlers even if already configured.
        stream: Destination stream for the console handler (default stderr).
    """
    if isinstance(settings, Config):
        log_settings = settings.logging
        if log_file is None and log_settings.to_file:
            log_file = settings.paths.log_file
    else:
        log_settings = settings

    logger = logging.getLogger(LOGGER_NAME)

    if getattr(logger, _CONFIGURED_KEY, False) and not force:
        return logger

    # Reset handlers on reconfigure.
    logger.handlers.clear()
    logger.setLevel(_level_from_name(log_settings.level))
    logger.propagate = False

    if log_settings.format == "json":
        formatter: logging.Formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    console = logging.StreamHandler(stream if stream is not None else sys.stderr)
    console.setFormatter(formatter)
    console.setLevel(logger.level)
    logger.addHandler(console)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logger.level)
        logger.addHandler(file_handler)

    setattr(logger, _CONFIGURED_KEY, True)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Return a child of the freecode logger.

    Usage:
        log = get_logger(__name__)
        log.info("ready")
    """
    if name is None or name == LOGGER_NAME:
        return logging.getLogger(LOGGER_NAME)
    if name.startswith(LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{LOGGER_NAME}.{name}")
