from __future__ import annotations

from datetime import date
from pathlib import Path

from click.testing import CliRunner

from fin_cli.fin_edit.main import main as edit_cli
from fin_cli.shared import models, paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect


def _prepare_db(db_path: Path) -> None:
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    # Ensure DB and base schema exist
    with connect(config) as connection:
        # Create a sample account used by inserted transactions
        models.upsert_account(
            connection,
            name="Test Account",
            institution="Test Bank",
            account_type="checking",
            auto_detected=False,
        )


def test_set_category_dry_run_then_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    with connect(config) as connection:
        # Ensure target category exists
        cat_id = models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Coffee",
            auto_generated=False,
            user_approved=True,
        )
        # Insert an uncategorized transaction
        txn = models.Transaction(
            date=date(2025, 9, 15),
            merchant="STARBUCKS #1234",
            amount=-5.50,
            account_id=1,
            original_description="STARBUCKS #1234",
        )
        assert models.insert_transaction(connection, txn)
        row = connection.execute(
            "SELECT id, fingerprint, category_id FROM transactions WHERE merchant = ?",
            ("STARBUCKS #1234",),
        ).fetchone()
        txn_id = int(row["id"])  # type: ignore[assignment]
        fingerprint = row["fingerprint"]
        assert row["category_id"] is None

    runner = CliRunner()
    # Dry-run (default, no --apply)
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "set-category",
            "--transaction-id",
            str(txn_id),
            "--category",
            "Food & Dining",
            "--subcategory",
            "Coffee",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        row = connection.execute(
            "SELECT category_id FROM transactions WHERE id = ?",
            (txn_id,),
        ).fetchone()
        assert row["category_id"] is None

    # Apply
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "set-category",
            "--fingerprint",
            fingerprint,
            "--category",
            "Food & Dining",
            "--subcategory",
            "Coffee",
            "--confidence",
            "0.9",
            "--method",
            "claude:interactive",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        row = connection.execute(
            "SELECT category_id, categorization_confidence, categorization_method FROM transactions WHERE id = ?",
            (txn_id,),
        ).fetchone()
        assert row["category_id"] == cat_id
        assert abs(float(row["categorization_confidence"]) - 0.9) < 1e-6
        assert row["categorization_method"] == "claude:interactive"


def test_add_merchant_pattern_dry_run_then_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    with connect(config) as connection:
        models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Coffee",
            auto_generated=False,
            user_approved=True,
        )

    runner = CliRunner()
    # Dry-run
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "add-merchant-pattern",
            "--pattern",
            "STARBUCKS%",
            "--category",
            "Food & Dining",
            "--subcategory",
            "Coffee",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS c FROM merchant_patterns WHERE pattern = ?",
            ("STARBUCKS%",),
        ).fetchone()
        assert int(row["c"]) == 0

    # Apply
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "add-merchant-pattern",
            "--pattern",
            "STARBUCKS%",
            "--category",
            "Food & Dining",
            "--subcategory",
            "Coffee",
            "--confidence",
            "0.96",
            "--display",
            "Starbucks",
            "--metadata",
            '{"source":"user","note":"training"}',
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        row = connection.execute(
            "SELECT category_id, confidence, pattern_display, metadata FROM merchant_patterns WHERE pattern = ?",
            ("STARBUCKS%",),
        ).fetchone()
        assert row is not None
        assert abs(float(row["confidence"]) - 0.96) < 1e-6
        assert row["pattern_display"] == "Starbucks"
        assert row["metadata"] is None or '"source":"user"' in row["metadata"]
