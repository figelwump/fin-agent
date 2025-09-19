from __future__ import annotations

from datetime import date

from fin_cli.shared import paths
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared import models


def _config(tmp_path):
    env = {paths.DATABASE_PATH_ENV: str(tmp_path / "models.db")}
    return load_config(env=env)


def test_upsert_account_and_dedup_transactions(tmp_path) -> None:
    config = _config(tmp_path)
    run_migrations(config)
    with connect(config) as connection:
        account_id = models.upsert_account(
            connection,
            name="Chase Freedom",
            institution="Chase",
            account_type="credit",
        )
        assert account_id > 0
        txn = models.Transaction(
            date=date(2024, 11, 1),
            merchant="WHOLEFDS #10234",
            amount=-127.34,
            account_id=account_id,
            original_description="WHOLEFDS #10234 BERKELEY",
        )
        inserted = models.insert_transaction(connection, txn)
        assert inserted is True
        duplicate = models.insert_transaction(connection, txn)
        assert duplicate is False


def test_get_or_create_category_updates_usage(tmp_path) -> None:
    config = _config(tmp_path)
    run_migrations(config)
    with connect(config) as connection:
        category_id = models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Groceries",
        )
        models.increment_category_usage(connection, category_id, delta=2)
        row = connection.execute(
            "SELECT transaction_count FROM categories WHERE id = ?",
            (category_id,),
        ).fetchone()
        assert row[0] == 2


def test_record_merchant_pattern_overwrites(tmp_path) -> None:
    config = _config(tmp_path)
    run_migrations(config)
    with connect(config) as connection:
        category_id = models.get_or_create_category(
            connection,
            category="Food & Dining",
            subcategory="Coffee Shops",
        )
        models.record_merchant_pattern(
            connection,
            pattern="STARBUCKS",
            category_id=category_id,
            confidence=0.9,
        )
        models.record_merchant_pattern(
            connection,
            pattern="STARBUCKS",
            category_id=category_id,
            confidence=0.8,
        )
        rows = connection.execute(
            "SELECT confidence FROM merchant_patterns WHERE pattern = ?",
            ("STARBUCKS",),
        ).fetchone()
        assert abs(rows[0] - 0.8) < 1e-6
