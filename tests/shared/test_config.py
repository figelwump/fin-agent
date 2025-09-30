from __future__ import annotations

from pathlib import Path

import pytest

from fin_cli.shared import paths
from fin_cli.shared.config import AppConfig, load_config
from fin_cli.shared.exceptions import ConfigurationError


def test_load_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(paths.CONFIG_DIR_ENV, str(tmp_path / "config"))
    monkeypatch.setenv(paths.DATA_DIR_ENV, str(tmp_path / "data"))
    cfg = load_config(env={})
    assert isinstance(cfg, AppConfig)
    assert cfg.database.path == paths.default_database_path(env={})
    assert cfg.extraction.auto_detect_accounts is True
    assert cfg.categorization.llm.enabled is True


def test_load_config_from_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.yaml"
    cfg_file.write_text(
        """
        database:
          path: ~/alt.db
        extraction:
          auto_detect_accounts: false
          supported_banks: [chase, amex]
        categorization:
          llm:
            enabled: false
            provider: anthropic
            model: claude-mini
            api_key_env: ANTHROPIC_API_KEY
        """,
        encoding="utf-8",
    )
    env = {
        paths.CONFIG_DIR_ENV: str(cfg_dir),
        paths.DATA_DIR_ENV: str(tmp_path / "data"),
    }
    cfg = load_config(config_path=cfg_file, env=env)
    assert cfg.database.path == paths.resolve_path("~/alt.db")
    assert cfg.extraction.supported_banks == ("chase", "amex")
    assert cfg.categorization.llm.provider == "anthropic"


def test_load_config_env_overrides(tmp_path: Path) -> None:
    custom_db = tmp_path / "custom.db"
    env = {
        "FINAGENT_DATABASE_PATH": str(custom_db),
        "FINCLI_LLM_ENABLED": "false",
        "FINCLI_EXTRACTION_SUPPORTED_BANKS": "chase,amex",
        "FINCLI_DYNAMIC_CATEGORIES_MIN_TRANSACTIONS": "5",
    }
    cfg = load_config(env=env)
    assert cfg.database.path == paths.resolve_path(custom_db)
    assert cfg.categorization.llm.enabled is False
    assert cfg.extraction.supported_banks == ("chase", "amex")
    assert cfg.categorization.dynamic_categories.min_transactions_for_new == 5


def test_invalid_yaml_raises_configuration_error(tmp_path: Path) -> None:
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("- just a list", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(config_path=cfg_file)
