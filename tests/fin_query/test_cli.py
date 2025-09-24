from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_query.main import cli
from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations


def _prepare_database(tmp_path: Path) -> str:
    db_path = tmp_path / "cli-query.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    with connect(config) as connection:
        cat_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Shopping", "Online"),
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO transactions (
                date, merchant, amount, category_id, account_id, original_description,
                import_date, categorization_confidence, categorization_method, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2025-08-01",
                "Amazon",
                -25.00,
                cat_id,
                None,
                "AMAZON MKTPLACE",
                None,
                0.9,
                "rule:pattern",
                "2025-08-01--25.00-Amazon",
            ),
        )
    return str(db_path)


def test_cli_saved_query(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "saved",
            "category_summary",
            "--db",
            db_path,
            "--param",
            "month=2025-08",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert "Shopping" in result.output


def test_cli_schema_command(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["schema", "--db", db_path, "--table", "transactions", "--format", "json"],
    )

    assert result.exit_code == 0
    assert "transactions" in result.output
