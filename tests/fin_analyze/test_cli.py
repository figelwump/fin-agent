from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_analyze.main import main
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import run_migrations

from . import test_analyzers


def _prepare_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "analyze-cli.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    test_analyzers._seed_spending_dataset(config)
    return db_path


def test_cli_outputs_json(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "merchant-frequency",
            "--month",
            "2025-08",
            "--format",
            "json",
            "--db",
            str(db_path),
            "--min-visits",
            "1",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["title"] == "Merchant Frequency"
    merchants = {entry["canonical"] for entry in payload["payload"]["merchants"]}
    assert "AMAZON" in merchants


def test_cli_renders_text(tmp_path: Path) -> None:
    db_path = _prepare_db(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "spending-patterns",
            "--month",
            "2025-08",
            "--db",
            str(db_path),
            "--by",
            "day",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Spending Patterns" in result.output
    assert "Tuesday" in result.output

