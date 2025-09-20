"""Data models and helper functions for database interactions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional

import sqlite3

from .exceptions import DatabaseError


@dataclass(slots=True)
class Account:
    id: int
    name: str
    institution: str
    account_type: str
    auto_detected: bool


@dataclass(slots=True)
class Category:
    id: int
    category: str
    subcategory: str
    auto_generated: bool
    user_approved: bool


@dataclass(slots=True)
class Transaction:
    date: date
    merchant: str
    amount: float
    account_id: int | None = None
    category_id: int | None = None
    original_description: str | None = None
    categorization_confidence: float | None = None
    categorization_method: str | None = None
    needs_review: bool = False

    def fingerprint(self) -> str:
        return compute_transaction_fingerprint(
            self.date,
            self.amount,
            self.merchant,
            self.account_id,
        )


def compute_transaction_fingerprint(
    txn_date: date,
    amount: float,
    merchant: str,
    account_id: int | None,
) -> str:
    """Return a deterministic hash for deduplication."""
    normalized = "|".join(
        [
            txn_date.isoformat(),
            f"{amount:.2f}",
            merchant.strip().lower(),
            str(account_id or 0),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upsert_account(
    connection: sqlite3.Connection,
    *,
    name: str,
    institution: str,
    account_type: str,
    auto_detected: bool = True,
) -> int:
    """Insert a new account if needed and return its ID."""
    row = connection.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO accounts (name, institution, account_type, auto_detected)
        VALUES (?, ?, ?, ?)
        """,
        (name, institution, account_type, auto_detected),
    )
    return int(cursor.lastrowid)


def get_or_create_category(
    connection: sqlite3.Connection,
    *,
    category: str,
    subcategory: str,
    auto_generated: bool = True,
    user_approved: bool = False,
) -> int:
    """Return a category id, creating it if it doesn't exist."""
    row = connection.execute(
        "SELECT id FROM categories WHERE category = ? AND subcategory = ?",
        (category, subcategory),
    ).fetchone()
    if row:
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO categories (category, subcategory, auto_generated, user_approved)
        VALUES (?, ?, ?, ?)
        """,
        (category, subcategory, auto_generated, user_approved),
    )
    return int(cursor.lastrowid)


def insert_transaction(
    connection: sqlite3.Connection,
    transaction: Transaction,
    *,
    allow_update: bool = False,
    skip_dedupe: bool = False,
) -> bool:
    """Insert a transaction if not already present.

    Returns True if inserted, False if considered a duplicate. When allow_update is
    True and a duplicate exists, the existing record is updated with the provided
    category information.
    """
    fingerprint = transaction.fingerprint()
    row = None
    if not skip_dedupe:
        row = connection.execute(
            "SELECT id FROM transactions WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()

    if row:
        if allow_update:
            connection.execute(
                """
                UPDATE transactions
                SET category_id = COALESCE(?, category_id),
                    categorization_confidence = COALESCE(?, categorization_confidence),
                    categorization_method = COALESCE(?, categorization_method),
                    needs_review = ?
                WHERE id = ?
                """,
                (
                    transaction.category_id,
                    transaction.categorization_confidence,
                    transaction.categorization_method,
                    int(transaction.needs_review),
                    int(row[0]),
                ),
            )
        return False

    connection.execute(
        """
        INSERT INTO transactions (
            date,
            merchant,
            amount,
            category_id,
            account_id,
            original_description,
            categorization_confidence,
            categorization_method,
            needs_review,
            fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction.date.isoformat(),
            transaction.merchant,
            transaction.amount,
            transaction.category_id,
            transaction.account_id,
            transaction.original_description,
            transaction.categorization_confidence,
            transaction.categorization_method,
            int(transaction.needs_review),
            fingerprint,
        ),
    )
    return True


def fetch_transaction_by_fingerprint(
    connection: sqlite3.Connection,
    fingerprint: str,
) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM transactions WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()


def apply_review_decision(
    connection: sqlite3.Connection,
    *,
    fingerprint: str,
    category_id: int,
    confidence: float,
    method: str,
) -> None:
    connection.execute(
        """
        UPDATE transactions
        SET category_id = ?,
            categorization_confidence = ?,
            categorization_method = ?,
            needs_review = 0
        WHERE fingerprint = ?
        """,
        (category_id, confidence, method, fingerprint),
    )

def increment_category_usage(
    connection: sqlite3.Connection,
    category_id: int,
    *,
    delta: int = 1,
) -> None:
    """Increment the transaction_count for a category."""
    connection.execute(
        """
        UPDATE categories
        SET transaction_count = COALESCE(transaction_count, 0) + ?,
            last_used = DATE('now')
        WHERE id = ?
        """,
        (delta, category_id),
    )


def record_merchant_pattern(
    connection: sqlite3.Connection,
    *,
    pattern: str,
    category_id: int,
    confidence: float,
) -> None:
    """Insert or update a learned merchant pattern."""
    connection.execute(
        """
        INSERT INTO merchant_patterns (pattern, category_id, confidence, learned_date, usage_count)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0)
        ON CONFLICT(pattern) DO UPDATE SET
            category_id = excluded.category_id,
            confidence = excluded.confidence,
            learned_date = CURRENT_TIMESTAMP
        """,
        (pattern, category_id, confidence),
    )


def fetch_merchant_patterns(
    connection: sqlite3.Connection,
    merchant: str,
) -> list[sqlite3.Row]:
    """Retrieve patterns similar to the provided merchant string."""
    like_expression = f"{merchant[:20]}%"
    rows = connection.execute(
        "SELECT * FROM merchant_patterns WHERE pattern LIKE ? ORDER BY confidence DESC",
        (like_expression,),
    ).fetchall()
    return list(rows)


def bulk_insert_transactions(
    connection: sqlite3.Connection,
    transactions: Iterable[Transaction],
    *,
    allow_updates: bool = False,
) -> tuple[int, int]:
    """Insert many transactions, returning (inserted, duplicates)."""
    inserted = 0
    duplicates = 0
    for txn in transactions:
        try:
            if insert_transaction(connection, txn, allow_update=allow_updates):
                inserted += 1
            else:
                duplicates += 1
        except sqlite3.IntegrityError as exc:  # pragma: no cover - defensive
            raise DatabaseError(str(exc)) from exc
    return inserted, duplicates
