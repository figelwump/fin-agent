from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_enhance.main import main as enhance_cli
from fin_cli.shared import models, paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect
from fin_cli.shared.merchants import merchant_pattern_key


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
        pattern = merchant_pattern_key("WHOLEFDS #10234")
        connection.execute(
            """
            INSERT INTO merchant_patterns (
                pattern,
                category_id,
                confidence,
                learned_date,
                usage_count,
                pattern_display,
                metadata
            ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, ?, ?)
            """,
            (pattern, category_id, 0.92, "Whole Foods Market", '{"platform":"InStore"}'),
        )
        connection.execute(
            "UPDATE accounts SET id = ? WHERE id = ?",
            (account_id, account_id),
        )


def _write_sample_csv(path: Path, rows: list[str]) -> None:
    header = "date,merchant,amount,original_description,account_name,institution,account_type,account_id\n"
    path.write_text(header + "".join(rows), encoding="utf-8")


def test_cli_import_persists_transactions(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    _write_sample_csv(
        csv_path,
        [
            "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,Test Account,Test Bank,credit,1\n",
            "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,Test Account,Test Bank,credit,1\n",
        ],
    )
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    runner = CliRunner()
    result = runner.invoke(
        enhance_cli, [str(csv_path), "--db", str(db_path), "--skip-llm"], env=env
    )
    assert result.exit_code == 0, result.output
    config = load_config(env=env)
    with connect(config) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert rows == 2
        categorized = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NOT NULL"
        ).fetchone()[0]
        assert categorized == 1
        uncategorized = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
        ).fetchone()[0]
        assert uncategorized == 1
        pattern = merchant_pattern_key("WHOLEFDS #10234")
        txn_row = connection.execute(
            "SELECT metadata FROM transactions WHERE merchant = ?",
            ("WHOLEFDS #10234",),
        ).fetchone()
        assert txn_row is not None and txn_row["metadata"]
        metadata = json.loads(txn_row["metadata"])
        assert metadata["merchant_pattern_key"] == pattern
        assert metadata["merchant_pattern_display"] == "Whole Foods Market"

    review_file = csv_path.with_name(f"{csv_path.stem}-review.json")
    assert review_file.exists()
    assert "UNKNOWN MERCHANT" in review_file.read_text(encoding="utf-8")


def test_cli_auto_skips_review(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    _write_sample_csv(
        csv_path,
        [
            "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,Test Account,Test Bank,credit,1\n",
            "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,Test Account,Test Bank,credit,1\n",
        ],
    )
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    runner = CliRunner()
    result = runner.invoke(
        enhance_cli,
        [str(csv_path), "--db", str(db_path), "--auto"],
        env=env,
    )
    assert result.exit_code == 0, result.output
    default_review = csv_path.with_name(f"{csv_path.stem}-review.json")
    assert not default_review.exists()
    config = load_config(env=env)
    with connect(config) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert rows == 2
        pending = connection.execute(
            "SELECT COUNT(*) FROM transactions WHERE category_id IS NULL"
        ).fetchone()[0]
        # UNKNOWN MERCHANT remains uncategorized but we should not have review artifacts
        assert pending == 1


def test_cli_dry_run(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    _write_sample_csv(
        csv_path,
        [
            "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,Test Account,Test Bank,credit,1\n",
        ],
    )
    db_path = tmp_path / "db.sqlite"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    with connect(config):
        pass
    runner = CliRunner()
    result = runner.invoke(
        enhance_cli,
        [str(csv_path), "--dry-run", "--db", str(db_path), "--skip-llm"],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        rows = connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        assert rows == 0
    default_review = csv_path.with_name(f"{csv_path.stem}-review.json")
    assert not default_review.exists()


def test_cli_review_output_writes_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    _write_sample_csv(
        csv_path,
        [
            "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,Test Account,Test Bank,credit,1\n",
            "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,Test Account,Test Bank,credit,1\n",
        ],
    )
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    review_path = tmp_path / "review.json"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    runner = CliRunner()
    result = runner.invoke(
        enhance_cli,
        [
            str(csv_path),
            "--db",
            str(db_path),
            "--review-output",
            str(review_path),
            "--skip-llm",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    data = review_path.read_text(encoding="utf-8")
    assert "UNKNOWN MERCHANT" in data


def test_apply_review_updates_transaction(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    _write_sample_csv(
        csv_path,
        [
            "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,Test Account,Test Bank,credit,1\n",
        ],
    )
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    review_path = tmp_path / "review.json"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    runner = CliRunner()
    runner.invoke(
        enhance_cli,
        [
            str(csv_path),
            "--db",
            str(db_path),
            "--review-output",
            str(review_path),
            "--skip-llm",
        ],
        env=env,
    )
    import json

    review_data = json.loads(review_path.read_text(encoding="utf-8"))
    fingerprint = review_data["review_needed"][0]["id"]
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(
        json.dumps(
            {
                "decisions": [
                    {
                        "id": fingerprint,
                        "category": "Misc",
                        "subcategory": "Other",
                        "learn": True,
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        enhance_cli,
        ["--apply-review", str(decisions_path), "--db", str(db_path)],
        env=env,
    )
    assert result.exit_code == 0, result.output
    config = load_config(env=env)
    with connect(config) as connection:
        row = connection.execute(
            "SELECT category_id FROM transactions WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        assert row["category_id"] is not None
        pattern_row = connection.execute(
            "SELECT category_id FROM merchant_patterns WHERE pattern = ?",
            ("UNKNOWN MERCHANT",),
        ).fetchone()
        assert pattern_row is not None
