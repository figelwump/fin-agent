"""Data models and helper functions for database interactions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping

import sqlite3
import json

from .exceptions import DatabaseError


@dataclass(slots=True)
class Account:
    id: int
    name: str
    institution: str
    account_type: str
    auto_detected: bool
    # Optional last 4 digits for stable identification; may be null for legacy rows
    last_4_digits: str | None = None


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
    account_key: str | None = None
    category_id: int | None = None
    original_description: str | None = None
    categorization_confidence: float | None = None
    categorization_method: str | None = None
    metadata: Mapping[str, Any] | None = None

    def fingerprint(self) -> str:
        return compute_transaction_fingerprint(
            self.date,
            self.amount,
            self.merchant,
            self.account_id,
            self.account_key,
        )


def compute_transaction_fingerprint(
    txn_date: date,
    amount: float,
    merchant: str,
    account_id: int | None,
    account_key: str | None = None,
) -> str:
    """Return a deterministic hash for deduplication.

    Prefer a stable `account_key` (v2 when available); fall back to `account_id` only
    as a defensive measure. This keeps fingerprints independent of DB row ids.
    """
    if account_key:
        account_identifier = account_key
    elif account_id is not None:
        account_identifier = str(account_id)
    else:
        account_identifier = "0"
    normalized = "|".join(
        [
            txn_date.isoformat(),
            f"{amount:.2f}",
            merchant.strip().lower(),
            account_identifier,
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_account_key(name: str, institution: str, account_type: str) -> str:
    """Legacy v1 key: hash of name+institution+account_type.

    Kept for compatibility with older CSVs and extractors that do not provide last4.
    """

    normalized = "|".join(
        [
            name.strip().lower(),
            institution.strip().lower(),
            account_type.strip().lower(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_account_key_v2(*, institution: str, account_type: str, last_4_digits: str) -> str:
    """Stable key based on institution + account_type + last_4_digits.

    This excludes the display `name` to avoid formatting drift and is preferred
    for fingerprints and matching when last4 is available.
    """
    normalized = "|".join(
        [
            institution.strip().lower(),
            account_type.strip().lower(),
            last_4_digits.strip(),
        ]
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def upsert_account(
    connection: sqlite3.Connection,
    *,
    name: str,
    institution: str,
    account_type: str,
    last_4_digits: str | None = None,
    auto_detected: bool = True,
) -> int:
    """Insert a new account if needed and return its ID.

    Primary match by (institution, account_type, last_4_digits) when last4 is provided.
    Fallback to exact name match for legacy scenarios.
    """
    if last_4_digits:
        row = connection.execute(
            """
            SELECT id FROM accounts
            WHERE institution = ? AND account_type = ? AND last_4_digits = ?
            """,
            (institution, account_type, last_4_digits),
        ).fetchone()
        if row:
            return int(row[0])

    row = connection.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    if row:
        return int(row[0])
    cursor = connection.execute(
        """
        INSERT INTO accounts (name, institution, account_type, last_4_digits, auto_detected)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, institution, account_type, last_4_digits, auto_detected),
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


def find_category_id(
    connection: sqlite3.Connection,
    *,
    category: str,
    subcategory: str,
) -> int | None:
    """Return an existing category id if present."""

    row = connection.execute(
        "SELECT id FROM categories WHERE category = ? AND subcategory = ?",
        (category, subcategory),
    ).fetchone()
    return int(row[0]) if row else None


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

    metadata_json = _serialize_metadata(transaction.metadata)

    if row:
        if allow_update:
            connection.execute(
                """
                UPDATE transactions
                SET category_id = COALESCE(?, category_id),
                    categorization_confidence = COALESCE(?, categorization_confidence),
                    categorization_method = COALESCE(?, categorization_method),
                    metadata = COALESCE(?, metadata)
                WHERE id = ?
                """,
                (
                    transaction.category_id,
                    transaction.categorization_confidence,
                    transaction.categorization_method,
                    metadata_json,
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
            fingerprint,
            metadata
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
            fingerprint,
            metadata_json,
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
            categorization_method = ?
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
    pattern_display: str | None = None,
    metadata: Mapping[str, Any] | str | None = None,
) -> None:
    """Insert or update a learned merchant pattern."""

    metadata_json = _serialize_metadata(metadata)
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
        )
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, 0, ?, ?)
        ON CONFLICT(pattern) DO UPDATE SET
            category_id = excluded.category_id,
            confidence = excluded.confidence,
            pattern_display = COALESCE(excluded.pattern_display, merchant_patterns.pattern_display),
            metadata = CASE
                WHEN excluded.metadata IS NOT NULL THEN excluded.metadata
                ELSE merchant_patterns.metadata
            END,
            learned_date = CURRENT_TIMESTAMP
        """,
        (pattern, category_id, confidence, pattern_display, metadata_json),
    )


def fetch_merchant_patterns(
    connection: sqlite3.Connection,
    pattern_key: str,
) -> list[sqlite3.Row]:
    """Retrieve learned patterns for the provided merchant key."""

    rows = connection.execute(
        "SELECT * FROM merchant_patterns WHERE pattern = ? ORDER BY confidence DESC",
        (pattern_key,),
    ).fetchall()
    return list(rows)


def fetch_llm_cache_entry(
    connection: sqlite3.Connection,
    merchant_normalized: str,
) -> sqlite3.Row | None:
    """Return cached LLM categorization suggestions for a merchant."""

    return connection.execute(
        "SELECT * FROM llm_cache WHERE merchant_normalized = ?",
        (merchant_normalized,),
    ).fetchone()


def upsert_llm_cache_entry(
    connection: sqlite3.Connection,
    *,
    merchant_normalized: str,
    response_json: str,
    model: str,
) -> None:
    """Store LLM response payload for a merchant.

    The cache stores the most recent response per normalized merchant string.
    """

    connection.execute(
        """
        INSERT INTO llm_cache (merchant_normalized, response_json, model)
        VALUES (?, ?, ?)
        ON CONFLICT(merchant_normalized) DO UPDATE SET
            response_json = excluded.response_json,
            model = excluded.model,
            updated_at = CURRENT_TIMESTAMP
        """,
        (merchant_normalized, response_json, model),
    )


def fetch_all_categories(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return every category record ordered for stable prompting."""

    rows = connection.execute(
        """
        SELECT category, subcategory
        FROM categories
        ORDER BY LOWER(category), LOWER(subcategory)
        """,
    ).fetchall()
    return list(rows)


def record_category_suggestion(
    connection: sqlite3.Connection,
    *,
    category: str,
    subcategory: str,
    amount: float,
    confidence: float,
) -> sqlite3.Row:
    """Track support metrics for a dynamically suggested category."""

    connection.execute(
        """
        INSERT INTO category_suggestions (
            category,
            subcategory,
            support_count,
            total_amount,
            max_confidence
        ) VALUES (?, ?, 1, ?, ?)
        ON CONFLICT(category, subcategory) DO UPDATE SET
            support_count = category_suggestions.support_count + 1,
            total_amount = category_suggestions.total_amount + excluded.total_amount,
            max_confidence = CASE
                WHEN excluded.max_confidence > category_suggestions.max_confidence
                THEN excluded.max_confidence
                ELSE category_suggestions.max_confidence
            END,
            last_seen = CURRENT_TIMESTAMP
        """,
        (category, subcategory, abs(amount), confidence),
    )
    return connection.execute(
        "SELECT * FROM category_suggestions WHERE category = ? AND subcategory = ?",
        (category, subcategory),
    ).fetchone()


def set_category_suggestion_status(
    connection: sqlite3.Connection,
    *,
    category: str,
    subcategory: str,
    status: str,
) -> None:
    connection.execute(
        """
        UPDATE category_suggestions
        SET status = ?, last_seen = CURRENT_TIMESTAMP
        WHERE category = ? AND subcategory = ?
        """,
        (status, category, subcategory),
    )


def fetch_category_suggestions(
    connection: sqlite3.Connection,
    *,
    status: str = "pending",
) -> list[sqlite3.Row]:
    return list(
        connection.execute(
            "SELECT * FROM category_suggestions WHERE status = ? ORDER BY support_count DESC",
            (status,),
        ).fetchall()
    )


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


def _serialize_metadata(metadata: Mapping[str, Any] | str | None) -> str | None:
    """Return a stable JSON string for metadata storage."""

    if metadata is None:
        return None
    if isinstance(metadata, str):
        stripped = metadata.strip()
        return stripped or None
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping, string, or None")
    if not metadata:
        return None
    return json.dumps(metadata, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
