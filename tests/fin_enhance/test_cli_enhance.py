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


def test_cli_review_mode_json_outputs_file(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(
        "date,merchant,amount,original_description,account_id\n"
        "2024-11-27,WHOLEFDS #10234,-127.34,WHOLEFDS #10234,1\n"
        "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,1\n",
        encoding="utf-8",
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
            "--review-mode",
            "json",
            "--review-output",
            str(review_path),
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    data = review_path.read_text(encoding="utf-8")
    assert "UNKNOWN MERCHANT" in data


def test_apply_review_updates_transaction(tmp_path: Path) -> None:
    csv_path = tmp_path / "transactions.csv"
    csv_path.write_text(
        "date,merchant,amount,original_description,account_id\n"
        "2024-11-28,UNKNOWN MERCHANT,-42.00,UNKNOWN MERCHANT,1\n",
        encoding="utf-8",
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
            "--review-mode",
            "json",
            "--review-output",
            str(review_path),
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
            "SELECT category_id, needs_review FROM transactions WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        assert row["category_id"] is not None
        assert row["needs_review"] == 0
        pattern_row = connection.execute(
            "SELECT category_id FROM merchant_patterns WHERE pattern = ?",
            ("UNKNOWN MERCHANT",),
        ).fetchone()
        assert pattern_row is not None
