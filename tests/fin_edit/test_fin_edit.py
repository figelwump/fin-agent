from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from click.testing import CliRunner
import re

from fin_cli.fin_edit.main import main as edit_cli
from fin_cli.shared import models, paths
from fin_cli.shared.merchants import merchant_pattern_key
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


def _write_enriched_csv(path: Path, rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "date",
        "merchant",
        "amount",
        "original_description",
        "account_name",
        "institution",
        "account_type",
        "last_4_digits",
        "category",
        "subcategory",
        "confidence",
        "account_key",
        "fingerprint",
        "method",
        "pattern_key",
        "pattern_display",
        "merchant_metadata",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _make_enriched_row(
    txn_date: date,
    merchant: str,
    amount: float,
    original_description: str,
    category: tuple[str, str],
    confidence: str,
    *,
    method: str | None = None,
    account_name: str = "Test Account",
    institution: str = "Test Bank",
    account_type: str = "checking",
    pattern_key: str | None = None,
    pattern_display: str | None = None,
    merchant_metadata: dict[str, object] | None = None,
    last_4_digits: str = "6033",
) -> dict[str, str]:
    # Prefer v2 key based on institution+type+last4
    account_key = models.compute_account_key_v2(
        institution=institution,
        account_type=account_type,
        last_4_digits=last_4_digits,
    )
    fingerprint = models.compute_transaction_fingerprint(
        txn_date,
        amount,
        merchant,
        None,
        account_key,
    )
    row: dict[str, str] = {
        "date": txn_date.isoformat(),
        "merchant": merchant,
        "amount": f"{amount:.2f}",
        "original_description": original_description,
        "account_name": account_name,
        "institution": institution,
        "account_type": account_type,
        "last_4_digits": last_4_digits,
        "category": category[0],
        "subcategory": category[1],
        "confidence": confidence,
        "account_key": account_key,
        "fingerprint": fingerprint,
    }
    if method is not None:
        row["method"] = method
    if pattern_key:
        row["pattern_key"] = pattern_key
    if pattern_display:
        row["pattern_display"] = pattern_display
    if merchant_metadata:
        row["merchant_metadata"] = json.dumps(merchant_metadata)
    return row


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


def test_import_transactions_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    csv_path = tmp_path / "enriched.csv"
    rows = [
        _make_enriched_row(
            txn_date=date(2025, 9, 15),
            merchant="ACME GROCERY",
            amount=42.50,
            original_description="ACME GROCERY #123",
            category=("Food & Dining", "Groceries"),
            confidence="0.95",
        )
    ]
    _write_enriched_csv(csv_path, rows)

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "import-transactions",
            str(csv_path),
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        txn_count = connection.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
        assert txn_count == 0
        category_row = connection.execute(
            "SELECT COUNT(*) AS c FROM categories WHERE category = ? AND subcategory = ?",
            ("Food & Dining", "Groceries"),
        ).fetchone()
        assert category_row["c"] == 0


def test_import_transactions_apply_and_dedupe(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    csv_path = tmp_path / "enriched.csv"
    rows = [
        _make_enriched_row(
            txn_date=date(2025, 9, 15),
            merchant="ACME GROCERY",
            amount=42.50,
            original_description="ACME GROCERY #123",
            category=("Food & Dining", "Groceries"),
            confidence="0.95",
        ),
        _make_enriched_row(
            txn_date=date(2025, 9, 16),
            merchant="CITY PARKING",
            amount=18.75,
            original_description="CITY PARKING GARAGE",
            category=("Auto & Transport", "Parking"),
            confidence="",
            method="review:manual",
        ),
    ]
    _write_enriched_csv(csv_path, rows)

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "import-transactions",
            str(csv_path),
            "--default-confidence",
            "0.82",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        rows_db = connection.execute(
            "SELECT merchant, amount, categorization_confidence, categorization_method FROM transactions ORDER BY date"
        ).fetchall()
        assert len(rows_db) == 2
        assert rows_db[0]["merchant"] == "ACME GROCERY"
        assert abs(float(rows_db[0]["categorization_confidence"]) - 0.95) < 1e-6
        assert rows_db[0]["categorization_method"] == "manual:fin-edit"
        assert rows_db[1]["merchant"] == "CITY PARKING"
        assert abs(float(rows_db[1]["categorization_confidence"]) - 0.82) < 1e-6
        assert rows_db[1]["categorization_method"] == "review:manual"

        groceries_category = connection.execute(
            "SELECT transaction_count FROM categories WHERE category = ? AND subcategory = ?",
            ("Food & Dining", "Groceries"),
        ).fetchone()
        parking_category = connection.execute(
            "SELECT transaction_count FROM categories WHERE category = ? AND subcategory = ?",
            ("Auto & Transport", "Parking"),
        ).fetchone()
        assert groceries_category is not None and int(groceries_category[0]) == 1
        assert parking_category is not None and int(parking_category[0]) == 1

    # Re-running should not create duplicates
    second = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "import-transactions",
            str(csv_path),
        ],
        env=env,
    )
    assert second.exit_code == 0, second.output
    with connect(config, read_only=True, apply_migrations=False) as connection:
        count = connection.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
        assert count == 2
        parking_category = connection.execute(
            "SELECT transaction_count FROM categories WHERE category = ? AND subcategory = ?",
            ("Auto & Transport", "Parking"),
        ).fetchone()
        assert parking_category is not None and int(parking_category[0]) == 1


def test_import_transactions_learn_patterns_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    csv_path = tmp_path / "enriched.csv"
    rows = [
        _make_enriched_row(
            txn_date=date(2025, 9, 20),
            merchant="STARBUCKS #1234",
            amount=5.50,
            original_description="STARBUCKS #1234",
            category=("Food & Dining", "Coffee"),
            confidence="0.95",
            pattern_key="STARBUCKS",
            pattern_display="Starbucks",
            merchant_metadata={"platform": "InStore"},
        )
    ]
    _write_enriched_csv(csv_path, rows)

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "import-transactions",
            str(csv_path),
            "--learn-patterns",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        pattern_row = connection.execute(
            "SELECT category_id, confidence, pattern_display, metadata FROM merchant_patterns WHERE pattern = ?",
            ("STARBUCKS",),
        ).fetchone()
        assert pattern_row is not None
        assert abs(float(pattern_row["confidence"]) - 0.95) < 1e-6
        assert pattern_row["pattern_display"] == "Starbucks"
        metadata = json.loads(pattern_row["metadata"])
        assert metadata == {"platform": "InStore"}

        txn_row = connection.execute(
            "SELECT metadata FROM transactions WHERE merchant = ?",
            ("STARBUCKS #1234",),
        ).fetchone()
        assert txn_row is not None and txn_row["metadata"] is not None
        txn_meta = json.loads(txn_row["metadata"])
        assert txn_meta["merchant_pattern_key"] == "STARBUCKS"
        assert txn_meta["merchant_pattern_display"] == "Starbucks"
        assert txn_meta["merchant_metadata"] == {"platform": "InStore"}


def test_import_transactions_learn_patterns_threshold(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    csv_path = tmp_path / "enriched.csv"
    rows = [
        _make_enriched_row(
            txn_date=date(2025, 9, 21),
            merchant="LOCAL BAKERY",
            amount=12.25,
            original_description="LOCAL BAKERY",
            category=("Food & Dining", "Restaurants"),
            confidence="0.60",
            pattern_display="Local Bakery",
        )
    ]
    _write_enriched_csv(csv_path, rows)

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "import-transactions",
            str(csv_path),
            "--learn-patterns",
            "--learn-threshold",
            "0.9",
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        pattern_count = connection.execute(
            "SELECT COUNT(*) AS c FROM merchant_patterns"
        ).fetchone()["c"]
        assert pattern_count == 0

        txn_row = connection.execute(
            "SELECT metadata FROM transactions WHERE merchant = ?",
            ("LOCAL BAKERY",),
        ).fetchone()
        assert txn_row is not None
        txn_meta = json.loads(txn_row["metadata"])
        assert txn_meta["merchant_pattern_key"] == merchant_pattern_key("LOCAL BAKERY")
        assert txn_meta["merchant_pattern_display"] == "Local Bakery"

def test_import_transactions_missing_category_without_creation(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    csv_path = tmp_path / "enriched.csv"
    rows = [
        _make_enriched_row(
            txn_date=date(2025, 9, 15),
            merchant="NEW SHOP",
            amount=12.00,
            original_description="NEW SHOP 123",
            category=("Shopping", "Online"),
            confidence="0.9",
        )
    ]
    _write_enriched_csv(csv_path, rows)

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "import-transactions",
            str(csv_path),
            "--no-create-categories",
        ],
        env=env,
    )
    assert result.exit_code != 0
    assert "Missing categories" in result.output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        count = connection.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
        assert count == 0


def test_delete_transactions_preview_then_apply(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)

    with connect(config) as connection:
        account_id = models.upsert_account(
            connection,
            name="Mercury Checking",
            institution="Mercury",
            account_type="checking",
            last_4_digits="2550",
            auto_detected=False,
        )
        category_id = models.get_or_create_category(
            connection,
            category="Bills & Utilities",
            subcategory="Credit Card Payment",
            auto_generated=False,
            user_approved=True,
        )
        for idx, merchant in enumerate(["Apple Card", "Chase"], start=1):
            txn = models.Transaction(
                date=date(2025, 9, 1 + idx),
                merchant=merchant,
                amount=5000.00 + idx,
                account_id=account_id,
                category_id=category_id,
                original_description=f"{merchant} ACH Pull",
                categorization_confidence=0.95,
                categorization_method="pattern:auto",
            )
            inserted = models.insert_transaction(connection, txn, skip_dedupe=True)
            assert inserted

        rows = connection.execute(
            "SELECT id FROM transactions WHERE merchant IN ('Apple Card', 'Chase') ORDER BY id"
        ).fetchall()
        txn_ids = [int(row["id"]) for row in rows]

    runner = CliRunner()
    # Preview (dry-run)
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "delete-transactions",
            "--id",
            str(txn_ids[0]),
            "--id",
            str(txn_ids[1]),
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    preview_output = _strip_ansi(result.output)
    assert "[dry-run]" in preview_output
    assert f"id={txn_ids[0]}" in preview_output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE id IN (?, ?)",
            txn_ids,
        ).fetchone()
        assert remaining["count"] == 2

    # Apply deletion
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "--apply",
            "delete-transactions",
            "--id",
            str(txn_ids[0]),
            "--id",
            str(txn_ids[1]),
        ],
        env=env,
    )
    assert result.exit_code == 0, result.output
    apply_output = _strip_ansi(result.output)
    assert "Deleted 2 transaction(s)." in apply_output

    with connect(config, read_only=True, apply_migrations=False) as connection:
        remaining = connection.execute(
            "SELECT COUNT(*) AS count FROM transactions WHERE id IN (?, ?)",
            txn_ids,
        ).fetchone()
        assert remaining["count"] == 0


def test_delete_transactions_missing_id(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    _prepare_db(db_path)
    env = {paths.DATABASE_PATH_ENV: str(db_path)}

    runner = CliRunner()
    result = runner.invoke(
        edit_cli,
        [
            "--db",
            str(db_path),
            "delete-transactions",
            "--id",
            "999",
        ],
        env=env,
    )
    assert result.exit_code != 0
    assert "Transactions not found" in result.output
ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")


def _strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)
