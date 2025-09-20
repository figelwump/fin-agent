from __future__ import annotations

import sqlite3
from datetime import date

from fin_cli.fin_enhance.categorizer.rules import RuleCategorizer
from fin_cli.shared import models


def _setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            subcategory TEXT,
            created_date TIMESTAMP,
            transaction_count INTEGER,
            last_used DATE,
            user_approved BOOLEAN,
            auto_generated BOOLEAN
        );
        CREATE TABLE merchant_patterns (
            pattern TEXT PRIMARY KEY,
            category_id INTEGER,
            confidence REAL,
            learned_date TIMESTAMP,
            usage_count INTEGER DEFAULT 0
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            merchant TEXT,
            amount REAL,
            category_id INTEGER,
            account_id INTEGER,
            original_description TEXT,
            import_date TIMESTAMP,
            categorization_confidence REAL,
            categorization_method TEXT,
            needs_review BOOLEAN,
            fingerprint TEXT UNIQUE
        );
        """
    )
    return conn


def test_rule_categorizer_uses_patterns() -> None:
    conn = _setup_db()
    conn.execute("INSERT INTO categories (category, subcategory) VALUES ('Food', 'Groceries')")
    conn.execute(
        "INSERT INTO merchant_patterns (pattern, category_id, confidence) VALUES (?, ?, ?)",
        ("WHOLEFDS #10234", 1, 0.95),
    )
    categorizer = RuleCategorizer(conn)
    outcome = categorizer.categorize("WHOLEFDS #10234")
    assert outcome.category_id == 1
    assert outcome.needs_review is False
    updated = conn.execute(
        "SELECT usage_count FROM merchant_patterns WHERE pattern = ?",
        ("WHOLEFDS #10234",),
    ).fetchone()[0]
    assert updated == 1


def test_rule_categorizer_falls_back_to_history() -> None:
    conn = _setup_db()
    conn.execute("INSERT INTO categories (category, subcategory) VALUES ('Dining', 'Restaurants')")
    txn = models.Transaction(
        date=date(2024, 11, 27),
        merchant="SWEETGREEN #123",
        amount=-18.47,
        category_id=1,
    )
    models.insert_transaction(conn, txn, skip_dedupe=True)
    categorizer = RuleCategorizer(conn)
    outcome = categorizer.categorize("SWEETGREEN #123")
    assert outcome.category_id == 1
    assert outcome.method == "rule:history"
