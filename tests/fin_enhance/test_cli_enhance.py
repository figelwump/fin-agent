from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_enhance.main import main as enhance_cli
from fin_cli.shared import models, paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect


def _prepare_db(db_path: Path) -> None:
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    with connect(config) as connection:
        account_id = models.upsert_account(
            connection,
            name="Test Account",
            institution="Test Bank",
            account_type="credit",
            auto_detected=False,
        )
        category_id = models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Groceries",
            auto_generated=False,
            user_approved=True,
        )
        connection.execute(
            "INSERT INTO merchant_patterns (pattern, category_id, confidence) VALUES (?, ?, ?)",
            ("WHOLEFDS #10234", category_id, 0.92),
        )


def test_cli_import_persists_transactions(tmp_path: Path, monkeypatch) -> None:
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(
        "date,merchant,amount,original_description,account_id\n"
        "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,1\n"
        "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,1\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    runner = CliRunner()
    result = runner.invoke(enhance_cli, [str(csv_path), "--db", str(db_path)], env=env)
    assert result.exit_code == 0, result.output
    config = load_config(env=env)
    with connect(config) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert rows == 2
        categorized = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NOT NULL"
        ).fetchone()[0]
        assert categorized == 1
        needs_review = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE needs_review = 1"
        ).fetchone()[0]
        assert needs_review == 1


def test_cli_dry_run(tmp_path: Path, monkeypatch) -> None:
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(
        "date,merchant,amount,original_description,account_id\n"
        "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,1\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "db.sqlite"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    with connect(config):
        pass
    runner = CliRunner()
    result = runner.invoke(
        enhance_cli,
        [str(csv_path), "--dry-run", "--db", str(db_path)],
        env=env,
    )
    assert result.exit_code == 0
    config = load_config(env=env)
    with connect(config, read_only=True, apply_migrations=False) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert rows == 0
