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
)
from fin_cli.fin_enhance.importer import ImportedTransaction
from fin_cli.shared import models
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
            confidence=ConfidenceSettings(auto_approve=0.8),
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
            fingerprint TEXT UNIQUE,
            metadata TEXT
        );
        CREATE TABLE merchant_patterns (
            pattern TEXT PRIMARY KEY,
            category_id INTEGER,
            confidence REAL,
            learned_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            usage_count INTEGER DEFAULT 0,
            pattern_display TEXT,
            metadata TEXT
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
    account_key = models.compute_account_key('Test Account', 'Test Bank', 'credit')
    return ImportedTransaction(
        date=date(2024, 11, 27),
        merchant=merchant,
        amount=-42.00,
        original_description=f"{merchant} POS",
        account_name='Test Account',
        institution='Test Bank',
        account_type='credit',
        account_key=account_key,
        account_id=1,
    )


def test_merchant_pattern_key_strips_noise() -> None:
    key = merchant_pattern_key("UNITED 0164315356024 UNITED.COM TX")
    assert "0164315356024" not in key
    assert ".COM" not in key
    dd_key = merchant_pattern_key("DD DOSAPOINT 855-431-0459 CA")
    assert "855" not in dd_key and "DOSAPOINT" in dd_key
    lyft_key = merchant_pattern_key("LYFT *1 RIDE")
    assert lyft_key == "RIDE"
    amazon_a = merchant_pattern_key("Amazon.com*random123 AMZN.COM/BILL WA")
    amazon_b = merchant_pattern_key("Amazon.com*NEWID123 AMZN.COM/BILL WA")
    assert amazon_a == amazon_b


def test_hybrid_auto_assigns_high_confidence() -> None:
    conn = _init_db()
    conn.execute("INSERT INTO categories (category, subcategory, auto_generated, user_approved) VALUES (?, ?, ?, ?)",
                 ("Food & Dining", "Groceries", False, True))
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = merchant_pattern_key("NEW SHOP")
    suggestion = LLMSuggestion(
        category="Food & Dining",
        subcategory="Groceries",
        confidence=0.92,
        is_new_category=False,
    )
    mapping = {
        merchant_key: LLMResult(
            merchant_normalized=merchant_key,
            pattern_key="NEW SHOP",
            pattern_display="New Shop",
            merchant_metadata={"platform": "Test"},
            suggestions=[suggestion],
        )
    }
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("NEW SHOP")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
        ),
    )

    assert result.outcomes[0].category_id == 1
    assert result.outcomes[0].needs_review is False
    assert result.outcomes[0].pattern_key == merchant_key
    assert result.outcomes[0].pattern_display == "New Shop"
    assert result.outcomes[0].merchant_metadata == {"platform": "Test"}
    assert not result.transaction_reviews
    cache_row = conn.execute("SELECT response_json FROM llm_cache WHERE merchant_normalized = ?", (merchant_key,)).fetchone()
    assert cache_row is not None
    pattern_row = conn.execute(
        "SELECT pattern_display, metadata FROM merchant_patterns WHERE pattern = ?",
        (merchant_key,),
    ).fetchone()
    assert pattern_row is not None
    assert pattern_row["pattern_display"] == "New Shop"
    assert "platform" in (pattern_row["metadata"] or "")


def test_hybrid_creates_missing_category_for_high_confidence() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    example_merchant = "Amazon.com*random123 AMZN.COM/BILL WA"
    merchant_key = merchant_pattern_key(example_merchant)
    suggestion = LLMSuggestion(
        category="Shopping",
        subcategory="Online Retail",
        confidence=0.9,
        is_new_category=False,
    )
    mapping = {
        merchant_key: LLMResult(
            merchant_normalized=merchant_key,
            pattern_key="AMAZON",
            pattern_display="Amazon",
            merchant_metadata=None,
            suggestions=[suggestion],
        )
    }
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction(example_merchant)]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
        ),
    )

    row = conn.execute(
        "SELECT id FROM categories WHERE category = ? AND subcategory = ?",
        ("Shopping", "Online Retail"),
    ).fetchone()
    assert row is None  # new categories are not auto-created

    assert result.outcomes[0].category_id is None
    assert result.outcomes[0].needs_review is True
    assert result.transaction_reviews  # unresolved transaction queued for review
    assert not result.category_proposals  # proposals reserved for new taxonomy entries
    assert result.auto_created_categories == []

    categorizer.llm_client.calls.clear()
    second_transactions = [_make_transaction("Amazon.com*NEWID123 AMZN.COM/BILL WA")]
    result_second = categorizer.categorize_transactions(
        second_transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
        ),
    )

    assert result_second.outcomes[0].category_id is None
    assert result_second.outcomes[0].needs_review is True
    assert result_second.transaction_reviews  # still queued because category not approved yet
    assert categorizer.llm_client.calls == []  # cache satisfied without new LLM call
    cache_row = conn.execute(
        "SELECT response_json FROM llm_cache WHERE merchant_normalized = ?",
        (merchant_key,),
    ).fetchone()
    assert cache_row is not None


def test_hybrid_flags_review_when_below_auto_threshold() -> None:
    conn = _init_db()
    conn.execute("INSERT INTO categories (category, subcategory, auto_generated, user_approved) VALUES (?, ?, ?, ?)",
                 ("Food & Dining", "Groceries", False, True))
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = merchant_pattern_key("AMBIG SHOP")
    suggestion = LLMSuggestion(
        category="Food & Dining",
        subcategory="Groceries",
        confidence=0.6,
        is_new_category=False,
    )
    mapping = {
        merchant_key: LLMResult(
            merchant_normalized=merchant_key,
            pattern_key="AMBIG SHOP",
            pattern_display="Ambig Shop",
            merchant_metadata=None,
            suggestions=[suggestion],
        )
    }
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("AMBIG SHOP")]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
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
        ),
    )

    assert result.outcomes[0].category_id is None
    assert result.transaction_reviews


def test_hybrid_new_category_requires_review_even_with_support() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant_key = merchant_pattern_key("GREEN CO")
    suggestion = LLMSuggestion(
        category="Eco Living",
        subcategory="Sustainable Goods",
        confidence=0.9,
        is_new_category=True,
    )
    mapping = {
        merchant_key: LLMResult(
            merchant_normalized=merchant_key,
            pattern_key="GREEN CO",
            pattern_display="Green Co",
            merchant_metadata=None,
            suggestions=[suggestion],
        )
    }
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction("GREEN CO") for _ in range(3)]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.8,
        ),
    )

    auto_created = conn.execute(
        "SELECT id FROM categories WHERE category = ? AND subcategory = ?",
        ("Eco Living", "Sustainable Goods"),
    ).fetchone()
    assert auto_created is None
    assert result.auto_created_categories == []


def test_force_auto_assign_creates_category() -> None:
    conn = _init_db()
    logger = Logger(verbose=False)
    config = _make_config()
    categorizer = HybridCategorizer(conn, config, logger, track_usage=False)
    merchant = "Fresh Greens"
    merchant_key = merchant_pattern_key(merchant)
    suggestion = LLMSuggestion(
        category="Farmers Market",
        subcategory="Local Produce",
        confidence=0.2,
        is_new_category=True,
    )
    mapping = {
        merchant_key: LLMResult(
            merchant_normalized=merchant_key,
            pattern_key="FRESH GREENS",
            pattern_display="Fresh Greens",
            merchant_metadata={"platform": "Local"},
            suggestions=[suggestion],
        )
    }
    categorizer.llm_client = DummyLLMClient(mapping)

    transactions = [_make_transaction(merchant)]
    result = categorizer.categorize_transactions(
        transactions,
        options=CategorizationOptions(
            skip_llm=False,
            apply_side_effects=True,
            auto_assign_threshold=0.9,
            force_auto_assign=True,
        ),
    )

    outcome = result.outcomes[0]
    assert outcome.needs_review is False
    assert outcome.method == "llm:auto-force"
    assert outcome.category_id is not None
    row = conn.execute(
        "SELECT category, subcategory FROM categories WHERE id = ?",
        (outcome.category_id,),
    ).fetchone()
    assert row is not None
    assert row["category"] == "Farmers Market"
    assert row["subcategory"] == "Local Produce"
    assert result.transaction_reviews == []
