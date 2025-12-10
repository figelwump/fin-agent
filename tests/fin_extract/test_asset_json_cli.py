from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_extract.main import main as extract_cli
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "asset_tracking"


def _setup_db(tmp_path: Path):
    db_path = tmp_path / "asset-extract.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    with connect(config) as connection:
        connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?)",
            ("UBS-INV-001", "UBS", "brokerage"),
        )
    return db_path, env


def test_asset_json_validate_only(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    result = runner.invoke(
        extract_cli,
        ["--db", str(db_path), "asset-json", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    # No imports when --apply not passed
    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 0


def test_asset_json_apply_imports(tmp_path: Path) -> None:
    db_path, env = _setup_db(tmp_path)
    runner = CliRunner()
    fixture = FIXTURE_ROOT / "ubs_statement.json"

    result = runner.invoke(
        extract_cli,
        ["--db", str(db_path), "asset-json", "--apply", str(fixture)],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(load_config(env=env), apply_migrations=False, read_only=True) as connection:
        hv_count = connection.execute("SELECT COUNT(*) FROM holding_values").fetchone()[0]
        assert hv_count == 3
        doc_hash = connection.execute("SELECT document_hash FROM documents").fetchone()[0]
        assert doc_hash == "ubs-2024-12-31-demo-hash"
