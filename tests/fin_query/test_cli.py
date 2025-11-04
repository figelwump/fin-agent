from __future__ import annotations

import json
import re
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
        connection.executemany(
            """
            INSERT INTO transactions (
                date, merchant, amount, category_id, account_id, original_description,
                import_date, categorization_confidence, categorization_method, fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
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
                (
                    "2025-08-15",
                    "Amazon",
                    -10.00,
                    cat_id,
                    None,
                    "AMAZON MKTPLACE",
                    None,
                    0.85,
                    "rule:pattern",
                    "2025-08-15--10.00-Amazon",
                ),
                (
                    "2025-08-20",
                    "Target",
                    -55.00,
                    cat_id,
                    None,
                    "TARGET 123",
                    None,
                    0.92,
                    "rule:pattern",
                    "2025-08-20--55.00-Target",
                ),
            ],
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


def test_cli_merchants_query(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "saved",
            "merchants",
            "--db",
            db_path,
            "--format",
            "json",
            "--min-count",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert "Amazon" in result.output
    assert "Target" not in result.output


def test_cli_sql_supports_tsv_and_limit(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "sql",
            "SELECT merchant, amount FROM transactions ORDER BY date",
            "--db",
            db_path,
            "--limit",
            "1",
            "--format",
            "tsv",
        ],
        env={"NO_COLOR": "1"},
    )

    assert result.exit_code == 0, result.output
    lines = [line for line in result.output.splitlines() if line.strip()]
    warning_parts: list[str] = []
    while lines and (lines[0].startswith("Result truncated to") or lines[0].startswith("output.")):
        warning_parts.append(lines.pop(0))
    warning_text = " ".join(warning_parts)
    if not warning_text and result.stderr:
        warning_text = result.stderr
    stripped_warning = re.sub(r"\x1b\[[0-9;]*m", "", warning_text)
    assert "Result truncated to 1 rows" in stripped_warning
    assert lines[0] == "merchant\tamount"
    assert lines[1].startswith("Amazon\t-25")


def test_cli_sql_rejects_empty_query(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "sql",
            "",
            "--db",
            db_path,
        ],
    )

    assert result.exit_code != 0
    assert "Query text must not be empty" in result.output


def test_cli_sql_validates_param_format(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "sql",
            "SELECT 1",
            "--db",
            db_path,
            "--param",
            "invalid",
        ],
    )

    assert result.exit_code != 0
    assert "must be in KEY=VALUE format" in result.output


def test_cli_list_outputs_catalog(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "list",
            "--db",
            db_path,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "category_summary" in result.output
    assert "merchant_patterns" in result.output


def test_cli_schema_respects_db_override(tmp_path: Path) -> None:
    db_path = _prepare_database(tmp_path)
    unused_db = tmp_path / "unused.db"
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "schema",
            "--db",
            db_path,
            "--format",
            "json",
        ],
        env={paths.DATABASE_PATH_ENV: str(unused_db)},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["database"].endswith("cli-query.db")
    table_names = {table["name"] for table in payload["tables"]}
    assert "transactions" in table_names
