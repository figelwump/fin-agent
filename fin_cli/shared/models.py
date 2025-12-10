"""Data models and helper functions for database interactions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

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


# ---------------------------------------------------------------------------
# Asset tracking helpers


def find_account_id_by_key(connection: sqlite3.Connection, account_key: str) -> int | None:
    """Resolve an account_id using multiple stable keys.

    Matching precedence:
    1. Exact name match (for human-readable keys like 'UBS-INV-001')
    2. v2 key (institution + account_type + last_4_digits) when last4 is present
    3. v1 key (name + institution + account_type) legacy hash
    """

    rows = connection.execute(
        "SELECT id, name, institution, account_type, last_4_digits FROM accounts"
    ).fetchall()

    matches: list[int] = []
    for row in rows:
        if row["name"] == account_key:
            matches.append(int(row["id"]))
            continue
        if row["last_4_digits"]:
            v2 = compute_account_key_v2(
                institution=row["institution"],
                account_type=row["account_type"],
                last_4_digits=row["last_4_digits"],
            )
            if v2 == account_key:
                matches.append(int(row["id"]))
                continue
        v1 = compute_account_key(
            row["name"],
            row["institution"],
            row["account_type"],
        )
        if v1 == account_key:
            matches.append(int(row["id"]))

    if not matches:
        return None
    if len(matches) > 1:
        raise DatabaseError(f"Account key '{account_key}' matched multiple accounts.")
    return matches[0]


def get_or_create_asset_source(
    connection: sqlite3.Connection,
    *,
    name: str,
    source_type: str,
    priority: int,
) -> int:
    """Find or insert an asset source."""
    row = connection.execute(
        "SELECT id FROM asset_sources WHERE name = ?",
        (name,),
    ).fetchone()
    if row:
        return int(row["id"])
    cursor = connection.execute(
        """
        INSERT INTO asset_sources (name, source_type, priority)
        VALUES (?, ?, ?)
        """,
        (name, source_type, priority),
    )
    return int(cursor.lastrowid)


def _load_identifiers(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    try:
        return json.loads(row["identifiers"]) if row["identifiers"] else {}
    except json.JSONDecodeError:
        return {}


def _instrument_matches_identifiers(row: sqlite3.Row, identifiers: Mapping[str, Any]) -> bool:
    if not identifiers:
        return False
    row_identifiers = _load_identifiers(row)
    for key, value in identifiers.items():
        if value and row_identifiers.get(key) == value:
            return True
    return False


def upsert_instrument(
    connection: sqlite3.Connection,
    *,
    name: str,
    symbol: str | None,
    exchange: str | None,
    currency: str,
    vehicle_type: str | None = None,
    identifiers: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | str | None = None,
) -> int:
    """Insert or update an instrument, matching on symbol+exchange or identifiers."""

    identifiers_json = _serialize_metadata(identifiers)
    metadata_json = _serialize_metadata(metadata)

    row = None
    if symbol:
        row = connection.execute(
            """
            SELECT * FROM instruments
            WHERE symbol = ?
              AND (exchange IS ? OR exchange = ? OR (exchange IS NULL AND ? IS NULL))
            """,
            (symbol, exchange, exchange, exchange),
        ).fetchone()

    if row is None and identifiers:
        # Fallback: scan instruments with identifiers and look for matching keys.
        candidates = connection.execute(
            "SELECT * FROM instruments WHERE identifiers IS NOT NULL"
        ).fetchall()
        for candidate in candidates:
            if _instrument_matches_identifiers(candidate, identifiers):
                row = candidate
                break

    if row:
        connection.execute(
            """
            UPDATE instruments
            SET name = COALESCE(?, name),
                exchange = COALESCE(?, exchange),
                currency = COALESCE(?, currency),
                vehicle_type = COALESCE(?, vehicle_type),
                identifiers = COALESCE(?, identifiers),
                metadata = COALESCE(?, metadata)
            WHERE id = ?
            """,
            (
                name,
                exchange,
                currency,
                vehicle_type,
                identifiers_json,
                metadata_json,
                int(row["id"]),
            ),
        )
        return int(row["id"])

    cursor = connection.execute(
        """
        INSERT INTO instruments (name, symbol, exchange, currency, vehicle_type, identifiers, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (name, symbol, exchange, currency, vehicle_type, identifiers_json, metadata_json),
    )
    return int(cursor.lastrowid)


def get_or_create_holding(
    connection: sqlite3.Connection,
    *,
    account_id: int,
    instrument_id: int,
    status: str = "active",
    position_side: str = "long",
    opened_at: str | None = None,
    closed_at: str | None = None,
    metadata: Mapping[str, Any] | str | None = None,
) -> int:
    """Return a holding id, creating if an active record doesn't exist."""

    row = connection.execute(
        """
        SELECT id FROM holdings
        WHERE account_id = ? AND instrument_id = ? AND status = 'active'
        """,
        (account_id, instrument_id),
    ).fetchone()
    if row:
        return int(row["id"])

    metadata_json = _serialize_metadata(metadata)
    cursor = connection.execute(
        """
        INSERT INTO holdings (
            account_id,
            instrument_id,
            status,
            position_side,
            opened_at,
            closed_at,
            metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (account_id, instrument_id, status, position_side, opened_at, closed_at, metadata_json),
    )
    return int(cursor.lastrowid)


def upsert_holding_value(
    connection: sqlite3.Connection,
    *,
    holding_id: int,
    as_of_date: str,
    quantity: float,
    price: float | None,
    market_value: float | None,
    source_id: int,
    document_id: int | None,
    valuation_currency: str = "USD",
    fx_rate_used: float = 1.0,
    as_of_datetime: str | None = None,
    accrued_interest: float | None = None,
    fees: float | None = None,
    metadata: Mapping[str, Any] | str | None = None,
) -> None:
    """Upsert a holding value row keyed by (holding_id, as_of_date, source_id)."""

    metadata_json = _serialize_metadata(metadata)
    connection.execute(
        """
        INSERT INTO holding_values (
            holding_id, as_of_date, as_of_datetime, quantity, price, market_value,
            accrued_interest, fees, source_id, document_id, valuation_currency,
            fx_rate_used, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(holding_id, as_of_date, source_id) DO UPDATE SET
            quantity = excluded.quantity,
            price = excluded.price,
            market_value = excluded.market_value,
            accrued_interest = excluded.accrued_interest,
            fees = excluded.fees,
            as_of_datetime = excluded.as_of_datetime,
            valuation_currency = excluded.valuation_currency,
            fx_rate_used = excluded.fx_rate_used,
            document_id = excluded.document_id,
            metadata = COALESCE(excluded.metadata, holding_values.metadata),
            ingested_at = CURRENT_TIMESTAMP
        """,
        (
            holding_id,
            as_of_date,
            as_of_datetime,
            quantity,
            price,
            market_value,
            accrued_interest,
            fees,
            source_id,
            document_id,
            valuation_currency,
            fx_rate_used,
            metadata_json,
        ),
    )


def register_document(
    connection: sqlite3.Connection,
    *,
    document_hash: str,
    source_id: int,
    broker: str | None = None,
    period_end_date: str | None = None,
    file_path: str | None = None,
    metadata: Mapping[str, Any] | str | None = None,
) -> int:
    """Insert a document if missing, otherwise return existing id."""

    row = connection.execute(
        "SELECT id FROM documents WHERE document_hash = ?",
        (document_hash,),
    ).fetchone()
    if row:
        return int(row["id"])

    metadata_json = _serialize_metadata(metadata)
    cursor = connection.execute(
        """
        INSERT INTO documents (document_hash, source_id, broker, period_end_date, file_path, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (document_hash, source_id, broker, period_end_date, file_path, metadata_json),
    )
    return int(cursor.lastrowid)


def find_asset_class_id(
    connection: sqlite3.Connection, *, main_class: str, sub_class: str
) -> int | None:
    """Look up an asset class id by main/sub labels."""

    row = connection.execute(
        """
        SELECT id FROM asset_classes
        WHERE LOWER(main_class) = LOWER(?) AND LOWER(sub_class) = LOWER(?)
        LIMIT 1
        """,
        (main_class, sub_class),
    ).fetchone()
    return int(row["id"]) if row else None


def ensure_instrument_classification(
    connection: sqlite3.Connection,
    *,
    instrument_id: int,
    asset_class_id: int,
    is_primary: bool = True,
    metadata: Mapping[str, Any] | str | None = None,
) -> int:
    """Idempotently attach an instrument to an asset class."""

    row = connection.execute(
        """
        SELECT id FROM instrument_classifications
        WHERE instrument_id = ? AND asset_class_id = ?
        """,
        (instrument_id, asset_class_id),
    ).fetchone()
    if row:
        return int(row["id"])

    metadata_json = _serialize_metadata(metadata)
    cursor = connection.execute(
        """
        INSERT INTO instrument_classifications (instrument_id, asset_class_id, is_primary, metadata)
        VALUES (?, ?, ?, ?)
        """,
        (instrument_id, asset_class_id, int(is_primary), metadata_json),
    )
    return int(cursor.lastrowid)


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
