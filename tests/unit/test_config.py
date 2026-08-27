"""
Phase 2 (Configuration + logging) unit tests.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from freecode.config import (
    Config,
    ConfigError,
    get_logger,
    load_config,
    setup_logging,
)
from freecode.config.loader import (
    ENV_API_KEY,
    ENV_API_KEY_ALT,
    ENV_LOG_LEVEL,
    apply_env_overrides,
    build_config,
    load_packaged_defaults,
)
from freecode.config.logging import JSONFormatter, LOGGER_NAME
from freecode.config.settings import LLMSettings, LoggingSettings


class TestPackagedDefaults:
    def test_defaults_load_and_have_required_sections(self):
        data = load_packaged_defaults()
        for section in (
            "llm",
            "scheduler",
            "context",
            "approval",
            "paths",
            "logging",
        ):
            assert section in data
            assert isinstance(data[section], dict)

    def test_default_endpoint_and_model(self):
        data = load_packaged_defaults()
        assert data["llm"]["endpoint"].startswith("https://")
        assert data["llm"]["model"] == "apifreellm"

    def test_defaults_contain_no_api_key(self):
        data = load_packaged_defaults()
        assert "api_key" not in data.get("llm", {})


class TestLoadConfig:
    def test_load_config_returns_typed_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(project_dir=tmp_path, environ={})
        assert isinstance(cfg, Config)
        assert cfg.llm.model == "apifreellm"
        assert cfg.scheduler.cooldown_floor_seconds == 20.0
        assert cfg.context.token_budget == 26000
        assert cfg.approval.default_policy == "auto_readonly"
        assert cfg.llm.api_key is None

    def test_user_toml_overrides_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            """
[llm]
model = "custom-model"
timeout_seconds = 90

[scheduler]
cooldown_floor_seconds = 25

[context]
token_budget = 20000

[approval]
default_policy = "ask"

[logging]
level = "DEBUG"
""".strip(),
            encoding="utf-8",
        )
        cfg = load_config(project_dir=tmp_path, environ={})
        assert cfg.llm.model == "custom-model"
        assert cfg.llm.timeout_seconds == 90.0
        assert cfg.scheduler.cooldown_floor_seconds == 25.0
        assert cfg.context.token_budget == 20000
        assert cfg.approval.default_policy == "ask"
        assert cfg.logging.level == "DEBUG"
        # Unspecified keys keep defaults.
        assert cfg.llm.endpoint.startswith("https://")
        assert cfg.context.context_window == 32000

    def test_partial_override_keeps_nested_defaults(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            "[scheduler]\ncooldown_floor_seconds = 22\n",
            encoding="utf-8",
        )
        cfg = load_config(project_dir=tmp_path, environ={})
        assert cfg.scheduler.cooldown_floor_seconds == 22.0
        assert cfg.scheduler.backoff_cap_seconds == 120.0

    def test_api_key_from_freecode_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(
            project_dir=tmp_path,
            environ={ENV_API_KEY: "secret-from-env"},
        )
        assert cfg.llm.api_key == "secret-from-env"

    def test_api_key_from_alt_env(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(
            project_dir=tmp_path,
            environ={ENV_API_KEY_ALT: "alt-secret"},
        )
        assert cfg.llm.api_key == "alt-secret"

    def test_freecode_api_key_wins_over_alt(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(
            project_dir=tmp_path,
            environ={
                ENV_API_KEY: "primary",
                ENV_API_KEY_ALT: "secondary",
            },
        )
        assert cfg.llm.api_key == "primary"

    def test_toml_api_key_is_ignored(self, tmp_path, monkeypatch):
        """Credentials must not come from committed config.toml."""
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            """
[llm]
api_key = "leaked-from-toml"
model = "x"
""".strip(),
            encoding="utf-8",
        )
        cfg = load_config(project_dir=tmp_path, environ={})
        assert cfg.llm.api_key is None
        assert cfg.llm.model == "x"

    def test_log_level_env_override(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(
            project_dir=tmp_path,
            environ={ENV_LOG_LEVEL: "warning"},
        )
        assert cfg.logging.level == "WARNING"

    def test_explicit_config_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        custom = tmp_path / "custom.toml"
        custom.write_text(
            "[llm]\nmodel = \"from-explicit\"\n",
            encoding="utf-8",
        )
        cfg = load_config(
            project_dir=tmp_path,
            config_path=custom,
            environ={},
        )
        assert cfg.llm.model == "from-explicit"

    def test_paths_are_resolved(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(project_dir=tmp_path, environ={})
        assert cfg.paths.project_dir == tmp_path.resolve()
        assert cfg.paths.runtime_dir == (tmp_path / ".freecode").resolve()
        assert cfg.paths.state_db == (tmp_path / ".freecode" / "state.db").resolve()

    def test_invalid_policy_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            '[approval]\ndefault_policy = "never"\n',
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="default_policy"):
            load_config(project_dir=tmp_path, environ={})

    def test_invalid_toml_raises(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            "this is not = valid [[ toml",
            encoding="utf-8",
        )
        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(project_dir=tmp_path, environ={})

    def test_readonly_allowlist_from_user_toml(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        freecode_dir = tmp_path / ".freecode"
        freecode_dir.mkdir()
        (freecode_dir / "config.toml").write_text(
            """
[approval]
readonly_allowlist = ["pytest", "ruff check"]
""".strip(),
            encoding="utf-8",
        )
        cfg = load_config(project_dir=tmp_path, environ={})
        assert cfg.approval.readonly_allowlist == ("pytest", "ruff check")


class TestBuildConfig:
    def test_empty_dict_uses_dataclass_defaults(self):
        cfg = build_config({})
        assert cfg.llm.endpoint == LLMSettings().endpoint
        assert cfg.scheduler.cooldown_floor_seconds == 20.0

    def test_apply_env_strips_toml_key(self):
        data = {"llm": {"api_key": "nope", "model": "m"}}
        out = apply_env_overrides(data, environ={})
        assert "api_key" not in out["llm"]
        assert out["llm"]["model"] == "m"


class TestLogging:
    def test_setup_logging_text_format(self, capsys):
        logger = setup_logging(
            LoggingSettings(level="INFO", format="text", to_file=False),
            force=True,
        )
        assert logger.name == LOGGER_NAME
        logger.info("hello-ph02")
        # Ensure handler is attached.
        assert logger.handlers
        assert logger.level == logging.INFO

    def test_setup_logging_json_format(self):
        logger = setup_logging(
            LoggingSettings(level="DEBUG", format="json", to_file=False),
            force=True,
        )
        assert any(isinstance(h.formatter, JSONFormatter) for h in logger.handlers)

    def test_json_formatter_output(self):
        record = logging.LogRecord(
            name="freecode.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="event happened",
            args=(),
            exc_info=None,
        )
        line = JSONFormatter().format(record)
        payload = json.loads(line)
        assert payload["msg"] == "event happened"
        assert payload["level"] == "INFO"
        assert "ts" in payload

    def test_file_logging_creates_parent_dirs(self, tmp_path):
        log_path = tmp_path / "nested" / "run.log"
        logger = setup_logging(
            LoggingSettings(level="INFO", format="text", to_file=True),
            log_file=log_path,
            force=True,
        )
        logger.info("written-to-file")
        for h in logger.handlers:
            if isinstance(h, logging.FileHandler):
                h.flush()
        assert log_path.exists()
        content = log_path.read_text(encoding="utf-8")
        assert "written-to-file" in content

    def test_get_logger_namespaces(self):
        setup_logging(LoggingSettings(level="WARNING"), force=True)
        child = get_logger("config.loader")
        assert child.name == "freecode.config.loader"
        root = get_logger()
        assert root.name == "freecode"

    def test_setup_from_full_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        cfg = load_config(project_dir=tmp_path, environ={})
        logger = setup_logging(cfg, force=True)
        assert logger.level == logging.INFO

    def test_force_reconfigure_changes_level(self):
        setup_logging(LoggingSettings(level="INFO"), force=True)
        logger = logging.getLogger(LOGGER_NAME)
        assert logger.level == logging.INFO
        setup_logging(LoggingSettings(level="ERROR"), force=True)
        assert logger.level == logging.ERROR
