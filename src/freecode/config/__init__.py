"""
config/ - configuration loading and structured application logging (ph-02).

Public surface:
  load_config()     - merge packaged defaults, user TOML, and env
  setup_logging()   - configure the `freecode` logger
  get_logger()      - obtain a namespaced logger
  Config, *Settings - typed configuration model
  ConfigError       - raised on invalid config
"""
from freecode.config.loader import ConfigError, load_config
from freecode.config.logging import get_logger, setup_logging
from freecode.config.settings import (
    ApprovalPolicy,
    ApprovalSettings,
    Config,
    ContextSettings,
    LLMSettings,
    LogFormat,
    LoggingSettings,
    PathSettings,
    SchedulerSettings,
)

__all__ = [
    "ApprovalPolicy",
    "ApprovalSettings",
    "Config",
    "ConfigError",
    "ContextSettings",
    "LLMSettings",
    "LogFormat",
    "LoggingSettings",
    "PathSettings",
    "SchedulerSettings",
    "get_logger",
    "load_config",
    "setup_logging",
]
