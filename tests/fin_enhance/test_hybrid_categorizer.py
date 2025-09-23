from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Dict

import sqlite3

from fin_cli.fin_enhance.categorizer.hybrid import (
    CategorizationOptions,
    HybridCategorizer,
)
from fin_cli.fin_enhance.categorizer.llm_client import (
    LLMClientError,
    LLMResult,
    LLMSuggestion,
    merchant_pattern_key,
    normalize_merchant,
)
from fin_cli.fin_enhance.importer import ImportedTransaction
from fin_cli.shared.config import (
    AppConfig,
    CategorizationSettings,
    ConfidenceSettings,
    DatabaseSettings,
    DynamicCategoriesSettings,
    ExtractionSettings,
    LLMSettings,
)
from fin_cli.shared.logging import Logger


class DummyLLMClient:
    def __init__(self, responses: Dict[str, LLMResult]) -> None:
        self._responses = responses
        self.enabled = True
        self.calls: list[Dict[str, list[object]]] = []

    def categorize_batch(self, items, *, known_categories=None, max_batch_merchants: int = 6):  # noqa: ANN001 - interface compatibility
        self.calls.append(items)
        return self._responses



def _make_config(*, llm_enabled: bool = True) -> AppConfig:
    return AppConfig(
        source_path=Path("test-config.yaml"),
        database=DatabaseSettings(path=Path("/tmp/test.db")),
        extraction=ExtractionSettings(auto_detect_accounts=True, supported_banks=("chase",)),
        categorization=CategorizationSettings(
            llm=LLMSettings(
                enabled=llm_enabled,
                provider="openai",
                model="gpt-4o-mini",
                api_key_env="OPENAI_API_KEY",
            ),
            dynamic_categories=DynamicCategoriesSettings(
                enabled=True,
                min_transactions_for_new=3,
                auto_approve_confidence=0.85,
                max_pending_categories=20,
            ),
            confidence=ConfidenceSettings(auto_approve=0.8, needs_review=0.5),
        ),
    )


def _init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transaction_count INTEGER DEFAULT 0,
            last_used DATE,
            user_approved BOOLEAN DEFAULT FALSE,
            auto_generated BOOLEAN DEFAULT TRUE,
            UNIQUE(category, subcategory)
        );
        CREATE TABLE transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date DATE,
            merchant TEXT,
            amount REAL,
            category_id INTEGER,
            account_id INTEGER,
            original_description TEXT,
            import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            categorization_confidence REAL,
            categorization_method TEXT,
            needs_review BOOLEAN,
            fingerprint TEXT UNIQUE
        );
        CREATE TABLE merchant_patterns (
            pattern TEXT PRIMARY KEY,
            category_id INTEGER,
            confidence REAL,
            learned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0
        );
        CREATE TABLE llm_cache (
            merchant_normalized TEXT PRIMARY KEY,
            response_json TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE category_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            support_count INTEGER NOT NULL DEFAULT 0,
            total_amount REAL NOT NULL DEFAULT 0,
            max_confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, subcategory)
        );
        """
    )
    return conn


def _make_transaction(merchant: str) -> ImportedTransaction:
    return ImportedTransaction(
        date=date(2024, 11, 27),
        merchant=merchant,
        amount=-42.00,
        original_description=f"{merchant} POS",
        account_id=1,
    )


def test_hybrid_auto_assigns_high_confidence() -> None:
    conn = _init_db()
    conn.execute("INSERT INTO categories (category, subcategory, auto_generated, user_approved) VALUES (?, ?, ?, ?)",
                 ("Food & Dining", "Groceries", False, True))
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = normalize_merchant("NEW SHOP")
    suggestion = LLMSuggestion(
        category="Food & Dining",
        subcategory="Groceries",
        confidence=0.92,
        is_new_category=False,
    )
    mapping = {merchant_key: LLMResult(merchant_key, [suggestion])}
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("NEW SHOP")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    assert result.outcomes[0].category_id == 1
    assert result.outcomes[0].needs_review is False
    assert not result.transaction_reviews
    cache_row = conn.execute("SELECT response_json FROM llm_cache WHERE merchant_normalized = ?", (merchant_key,)).fetchone()
    assert cache_row is not None


def test_hybrid_creates_missing_category_for_high_confidence() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = normalize_merchant("AMAZON")
    suggestion = LLMSuggestion(
        category="Shopping",
        subcategory="Online Retail",
        confidence=0.9,
        is_new_category=False,
    )
    mapping = {merchant_key: LLMResult(merchant_key, [suggestion])}
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("AMAZON")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    row = conn.execute(
        "SELECT id, auto_generated, user_approved FROM categories WHERE category = ? AND subcategory = ?",
        ("Shopping", "Online Retail"),
    ).fetchone()
    assert row is not None
    assert row[1] == 1  # auto_generated
    assert row[2] == 0  # user_approved remains False until reviewed
    assert result.outcomes[0].category_id == int(row[0])
    assert result.outcomes[0].needs_review is False
    assert not result.transaction_reviews
    assert ("Shopping", "Online Retail") in result.auto_created_categories

    # Ensure merchant pattern stored for reuse
    pattern_row = conn.execute(
        "SELECT category_id FROM merchant_patterns WHERE pattern = ?",
        (merchant_pattern_key("Amazon.com*random123 AMZN.COM/BILL WA"),),
    ).fetchone()
    assert pattern_row is not None
    assert int(pattern_row[0]) == int(row[0])

    categorizer.llm_client.calls.clear()
    second_transactions = [_make_transaction("Amazon.com*NEWID123 AMZN.COM/BILL WA")]
    result_second = categorizer.categorize_transactions(
        second_transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    assert result_second.outcomes[0].category_id == int(row[0])
    assert result_second.outcomes[0].method == "rule:pattern"
    assert result_second.outcomes[0].needs_review is False
    assert not result_second.transaction_reviews
    assert not categorizer.llm_client.calls


def test_hybrid_flags_review_when_below_auto_threshold() -> None:
    conn = _init_db()
    conn.execute("INSERT INTO categories (category, subcategory, auto_generated, user_approved) VALUES (?, ?, ?, ?)",
                 ("Food & Dining", "Groceries", False, True))
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = normalize_merchant("AMBIG SHOP")
    suggestion = LLMSuggestion(
        category="Food & Dining",
        subcategory="Groceries",
        confidence=0.6,
        is_new_category=False,
    )
    mapping = {merchant_key: LLMResult(merchant_key, [suggestion])}
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("AMBIG SHOP")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    assert result.outcomes[0].category_id is None
    assert result.outcomes[0].needs_review is True
    assert len(result.transaction_reviews) == 1
    assert result.transaction_reviews[0].suggestions[0].confidence == 0.6


def test_hybrid_handles_llm_failure() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    failing_client = DummyLLMClient({})
    failing_client.enabled = True

    def _raise(*_args, **_kwargs):  # noqa: ANN001 - signature compatibility
        raise LLMClientError("boom")

    failing_client.categorize_batch = _raise  # type: ignore[assignment]
    categorizer.llm_client = failing_client

    transactions = [_make_transaction("FAIL SHOP")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    assert result.outcomes[0].category_id is None
    assert result.transaction_reviews


def test_hybrid_auto_creates_new_category_after_threshold() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = normalize_merchant("GREEN CO")
    suggestion = LLMSuggestion(
        category="Eco Living",
        subcategory="Sustainable Goods",
        confidence=0.9,
        is_new_category=True,
    )
    mapping = {merchant_key: LLMResult(merchant_key, [suggestion])}
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("GREEN CO") for _ in range(3)]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
            needs_review_threshold=0.5,
        ),
    )

    auto_created = conn.execute(
        "SELECT id FROM categories WHERE category = ? AND subcategory = ?",
        ("Eco Living", "Sustainable Goods"),
    ).fetchone()
    assert auto_created is not None
    assert len(result.auto_created_categories) == 1
    assert result.auto_created_categories[0] == ("Eco Living", "Sustainable Goods")
