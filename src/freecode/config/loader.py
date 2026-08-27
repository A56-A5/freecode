"""
config.loader - load and merge FreeCode configuration.

Precedence (highest wins):
  1. Explicit overrides passed to load_config()
  2. Environment variables (credentials + a few operational knobs)
  3. User file: <project>/.freecode/config.toml
  4. Packaged defaults: freecode/config/defaults.toml

API keys are read only from the environment. They are never accepted from
TOML so a committed config.toml cannot leak credentials.
"""
from __future__ import annotations

import os
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

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

# Environment variable names.
ENV_API_KEY = "FREECODE_API_KEY"
ENV_API_KEY_ALT = "APIFREELLM_API_KEY"
ENV_API_KEY_PREFIX = "FREECODE_API_KEY_"
ENV_LOG_LEVEL = "FREECODE_LOG_LEVEL"
ENV_ENDPOINT = "FREECODE_LLM_ENDPOINT"
ENV_MODEL = "FREECODE_LLM_MODEL"
ENV_CONFIG_PATH = "FREECODE_CONFIG"

USER_CONFIG_REL = Path(".freecode") / "config.toml"
DEFAULTS_PACKAGE = "freecode.config"
DEFAULTS_NAME = "defaults.toml"

_VALID_POLICIES: frozenset[str] = frozenset({"ask", "auto_readonly", "auto"})
_VALID_LOG_FORMATS: frozenset[str] = frozenset({"text", "json"})


class ConfigError(ValueError):
    """Raised when configuration is invalid or unreadable."""


def _read_toml_bytes(data: bytes, *, source: str) -> dict[str, Any]:
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {source}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"Config root in {source} must be a table")
    return parsed


def load_packaged_defaults() -> dict[str, Any]:
    """Load the shipped defaults.toml from package data."""
    try:
        ref = resources.files(DEFAULTS_PACKAGE).joinpath(DEFAULTS_NAME)
        data = ref.read_bytes()
    except (FileNotFoundError, TypeError, AttributeError) as exc:
        # Fallback for editable installs / odd loaders.
        fallback = Path(__file__).with_name(DEFAULTS_NAME)
        if not fallback.exists():
            raise ConfigError(
                f"Packaged defaults not found ({DEFAULTS_NAME})"
            ) from exc
        data = fallback.read_bytes()
    return _read_toml_bytes(data, source=f"package:{DEFAULTS_NAME}")


def load_user_toml(path: Path) -> dict[str, Any]:
    """Load a user config.toml; missing file yields {}."""
    if not path.exists():
        return {}
    return _read_toml_bytes(path.read_bytes(), source=str(path))


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge override into a copy of base (tables only)."""
    result = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _section(data: Mapping[str, Any], name: str) -> dict[str, Any]:
    raw = data.get(name, {})
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"[{name}] must be a table, got {type(raw).__name__}")
    return raw


def _as_float(value: Any, *, field: str, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} must be a number, got {value!r}") from exc


def _as_int(value: Any, *, field: str, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} must be an integer, got {value!r}") from exc


def _as_bool(value: Any, *, field: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise ConfigError(f"{field} must be a boolean, got {value!r}")


def _as_str(value: Any, *, field: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise ConfigError(f"{field} must be a string, got {value!r}")
    return value


def _as_path(value: Any, *, field: str, default: Path) -> Path:
    if value is None:
        return default
    if not isinstance(value, (str, Path)):
        raise ConfigError(f"{field} must be a path string, got {value!r}")
    return Path(value)


def _as_str_list(value: Any, *, field: str, default: tuple[str, ...]) -> tuple[str, ...]:
    if value is None:
        return default
    if not isinstance(value, list):
        raise ConfigError(f"{field} must be an array of strings, got {value!r}")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ConfigError(f"{field} entries must be strings, got {item!r}")
        out.append(item)
    return tuple(out)


def _policy(value: Any, *, default: ApprovalPolicy) -> ApprovalPolicy:
    if value is None:
        return default
    if not isinstance(value, str) or value not in _VALID_POLICIES:
        raise ConfigError(
            f"approval.default_policy must be one of "
            f"{sorted(_VALID_POLICIES)}, got {value!r}"
        )
    return value  # type: ignore[return-value]


def _log_format(value: Any, *, default: LogFormat) -> LogFormat:
    if value is None:
        return default
    if not isinstance(value, str) or value not in _VALID_LOG_FORMATS:
        raise ConfigError(
            f"logging.format must be one of "
            f"{sorted(_VALID_LOG_FORMATS)}, got {value!r}"
        )
    return value  # type: ignore[return-value]

def _api_keys_from_env(environ: Mapping[str, str]) -> tuple[str, ...]:
    keys: list[str] = []

    # New multi-key format:
    # FREECODE_API_KEY_1
    # FREECODE_API_KEY_2
    # FREECODE_API_KEY_3
    # ...
    index = 1
    while True:
        name = f"{ENV_API_KEY_PREFIX}{index}"
        raw = environ.get(name, "").strip()

        if not raw:
            # Stop at the first missing key.
            break

        keys.append(raw)
        index += 1

    # Backwards compatibility.
    if not keys:
        for name in (ENV_API_KEY, ENV_API_KEY_ALT):
            raw = environ.get(name, "").strip()
            if raw:
                keys.append(raw)
                break

    return tuple(keys)

def apply_env_overrides(
    data: dict[str, Any],
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """
    Apply environment-variable overrides on top of merged TOML data.

    Credentials are injected here only; any `api_key` key present in TOML
    is deliberately ignored.
    """
    env = environ if environ is not None else os.environ
    merged = _deep_merge(data, {})

    llm = dict(_section(merged, "llm"))
    # Strip any accidental TOML credential.
    llm.pop("api_key", None)
    llm.pop("api-key", None)
    llm.pop("key", None)

    if endpoint := env.get(ENV_ENDPOINT, "").strip():
        llm["endpoint"] = endpoint
    if model := env.get(ENV_MODEL, "").strip():
        llm["model"] = model
    merged["llm"] = llm

    if level := env.get(ENV_LOG_LEVEL, "").strip():
        logging_sec = dict(_section(merged, "logging"))
        logging_sec["level"] = level.upper()
        merged["logging"] = logging_sec

    return merged


def build_config(
    data: Mapping[str, Any],
    *,
    api_key: str | None = None,
    api_keys: tuple[str, ...] = (),
) -> Config:
    """Map a merged dict into the typed Config model."""
    # Instance defaults — slotted dataclasses do not expose field defaults
    # as usable class attributes.
    llm_d = LLMSettings()
    sched_d = SchedulerSettings()
    ctx_d = ContextSettings()
    appr_d = ApprovalSettings()
    paths_d = PathSettings()
    log_d = LoggingSettings()

    llm_raw = _section(data, "llm")
    sched_raw = _section(data, "scheduler")
    ctx_raw = _section(data, "context")
    appr_raw = _section(data, "approval")
    paths_raw = _section(data, "paths")
    log_raw = _section(data, "logging")

    llm = LLMSettings(
        endpoint=_as_str(
            llm_raw.get("endpoint"),
            field="llm.endpoint",
            default=llm_d.endpoint,
        ),
        model=_as_str(
            llm_raw.get("model"),
            field="llm.model",
            default=llm_d.model,
        ),
        timeout_seconds=_as_float(
            llm_raw.get("timeout_seconds"),
            field="llm.timeout_seconds",
            default=llm_d.timeout_seconds,
        ),
        api_key=api_key,
        api_keys=api_keys or ((api_key,) if api_key else ()),
    )

    scheduler = SchedulerSettings(
        cooldown_floor_seconds=_as_float(
            sched_raw.get("cooldown_floor_seconds"),
            field="scheduler.cooldown_floor_seconds",
            default=sched_d.cooldown_floor_seconds,
        ),
        backoff_cap_seconds=_as_float(
            sched_raw.get("backoff_cap_seconds"),
            field="scheduler.backoff_cap_seconds",
            default=sched_d.backoff_cap_seconds,
        ),
    )

    context = ContextSettings(
        token_budget=_as_int(
            ctx_raw.get("token_budget"),
            field="context.token_budget",
            default=ctx_d.token_budget,
        ),
        context_window=_as_int(
            ctx_raw.get("context_window"),
            field="context.context_window",
            default=ctx_d.context_window,
        ),
        chars_per_token=_as_float(
            ctx_raw.get("chars_per_token"),
            field="context.chars_per_token",
            default=ctx_d.chars_per_token,
        ),
    )

    approval = ApprovalSettings(
        default_policy=_policy(
            appr_raw.get("default_policy"),
            default=appr_d.default_policy,
        ),
        readonly_allowlist=_as_str_list(
            appr_raw.get("readonly_allowlist"),
            field="approval.readonly_allowlist",
            default=appr_d.readonly_allowlist,
        ),
    )

    paths = PathSettings(
        project_dir=_as_path(
            paths_raw.get("project_dir"),
            field="paths.project_dir",
            default=paths_d.project_dir,
        ),
        runtime_dir=_as_path(
            paths_raw.get("runtime_dir"),
            field="paths.runtime_dir",
            default=paths_d.runtime_dir,
        ),
        state_db=_as_path(
            paths_raw.get("state_db"),
            field="paths.state_db",
            default=paths_d.state_db,
        ),
        log_file=_as_path(
            paths_raw.get("log_file"),
            field="paths.log_file",
            default=paths_d.log_file,
        ),
    )

    logging = LoggingSettings(
        level=_as_str(
            log_raw.get("level"),
            field="logging.level",
            default=log_d.level,
        ).upper(),
        format=_log_format(
            log_raw.get("format"),
            default=log_d.format,
        ),
        to_file=_as_bool(
            log_raw.get("to_file"),
            field="logging.to_file",
            default=log_d.to_file,
        ),
    )

    return Config(
        llm=llm,
        scheduler=scheduler,
        context=context,
        approval=approval,
        paths=paths,
        logging=logging,
    )


def load_config(
    *,
    project_dir: Path | str | None = None,
    config_path: Path | str | None = None,
    environ: Mapping[str, str] | None = None,
    resolve: bool = True,
) -> Config:
    """
    Load configuration for a FreeCode session.

    Args:
        project_dir: Project root. Defaults to cwd.
        config_path: Explicit path to config.toml. When omitted, uses
            FREECODE_CONFIG if set, else <project>/.freecode/config.toml.
        environ: Environment mapping (defaults to os.environ). Injected
            for tests.
        resolve: When True, resolve path fields against project_dir.
    """
    env = environ if environ is not None else os.environ
    root = Path(project_dir) if project_dir is not None else Path.cwd()

    defaults = load_packaged_defaults()

    if config_path is not None:
        user_path = Path(config_path)
    elif env.get(ENV_CONFIG_PATH, "").strip():
        user_path = Path(env[ENV_CONFIG_PATH].strip())
    else:
        user_path = root / USER_CONFIG_REL

    user = load_user_toml(user_path)
    merged = _deep_merge(defaults, user)
    merged = apply_env_overrides(merged, env)

    # Ensure project_dir reflects the caller's root when not overridden.
    paths = dict(_section(merged, "paths"))
    if "project_dir" not in user.get("paths", {}):
        paths["project_dir"] = str(root)
    merged["paths"] = paths

    api_keys = _api_keys_from_env(env)

    config = build_config(
        merged,
        api_key=api_keys[0] if api_keys else None,
        api_keys=api_keys,
    )
    if resolve:
        config = config.resolve_paths(root)
    return config
