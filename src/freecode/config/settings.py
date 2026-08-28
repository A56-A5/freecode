"""
config.settings - typed configuration model for FreeCode.

These dataclasses are pure data. They do not load files, read the
environment, or configure logging. That lives in loader.py / logging.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


ApprovalPolicy = Literal["ask", "auto_readonly", "auto"]
LogFormat = Literal["text", "json"]


@dataclass(frozen=True, slots=True)
class LLMSettings:
    endpoint: str = "https://apifreellm.com/api/v1/chat"
    model: str = "apifreellm"
    timeout_seconds: float = 120.0

    # Backwards-compatible single key.
    api_key: str | None = None

    # Multiple API keys, populated only from environment variables.
    api_keys: tuple[str, ...] = ()

    # Ordered provider names: apifreellm, groq
    providers: tuple[str, ...] = ("apifreellm", "groq")

    # Groq (env-only keys)
    groq_model: str = "llama-3.1-8b-instant"
    groq_api_keys: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SchedulerSettings:
    cooldown_floor_seconds: float = 20.0
    backoff_cap_seconds: float = 120.0


@dataclass(frozen=True, slots=True)
class ContextSettings:
    token_budget: int = 26000
    context_window: int = 32000
    chars_per_token: float = 4.0


@dataclass(frozen=True, slots=True)
class ApprovalSettings:
    default_policy: ApprovalPolicy = "auto_readonly"
    readonly_allowlist: tuple[str, ...] = (
        "git status",
        "git diff",
        "git log",
        "git show",
        "git branch",
        "pytest",
        "python -m pytest",
        "rg ",
        "grep ",
        "ls ",
        "find ",
        "cat ",
        "head ",
        "tail ",
        "wc ",
    )


@dataclass(frozen=True, slots=True)
class PathSettings:
    """Paths relative to project_dir unless already absolute."""

    project_dir: Path = field(default_factory=lambda: Path("."))
    runtime_dir: Path = field(default_factory=lambda: Path(".freecode"))
    state_db: Path = field(default_factory=lambda: Path(".freecode/state.db"))
    log_file: Path = field(default_factory=lambda: Path(".freecode/logs/freecode.log"))


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    level: str = "INFO"
    format: LogFormat = "text"
    to_file: bool = False


@dataclass(frozen=True, slots=True)
class Config:
    """Top-level application configuration."""

    llm: LLMSettings = field(default_factory=LLMSettings)
    scheduler: SchedulerSettings = field(default_factory=SchedulerSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    approval: ApprovalSettings = field(default_factory=ApprovalSettings)
    paths: PathSettings = field(default_factory=PathSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)

    def resolve_paths(self, base: Path | None = None) -> Config:
        """
        Return a copy with path fields resolved against `base` (or
        paths.project_dir). Absolute paths are left unchanged.
        """
        root = (base or self.paths.project_dir).resolve()

        def _resolve(p: Path) -> Path:
            return p if p.is_absolute() else (root / p).resolve()

        return Config(
            llm=self.llm,
            scheduler=self.scheduler,
            context=self.context,
            approval=self.approval,
            paths=PathSettings(
                project_dir=root,
                runtime_dir=_resolve(self.paths.runtime_dir),
                state_db=_resolve(self.paths.state_db),
                log_file=_resolve(self.paths.log_file),
            ),
            logging=self.logging,
        )
