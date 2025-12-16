"""Shared pytest fixtures for fin-analyze tests.

The fixtures here provide a consistently migrated SQLite database and
helpers to seed canonical datasets from JSON fixtures so analyzers and the
CLI can be exercised under reproducible conditions. The JSON format is kept
LLM-friendly: explicit keys, deterministic defaults, and minimal inference.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from fin_cli.fin_analyze.types import AnalysisContext, TimeWindow
from fin_cli.shared import paths
from fin_cli.shared.cli import CLIContext
from fin_cli.shared.config import AppConfig, load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared.logging import get_logger

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "analyze"


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    """Return an AppConfig backed by a temp SQLite database with migrations applied."""

    db_path = tmp_path / "fin-analyze.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config


@pytest.fixture()
def cli_context(app_config: AppConfig) -> CLIContext:
    """Construct a CLIContext with deterministic logging for analyzer tests."""

    return CLIContext(
        config=app_config,
        db_path=app_config.database.path,
        dry_run=False,
        verbose=False,
        logger=get_logger(verbose=False),
    )


@pytest.fixture()
def window_factory() -> Callable[[str, str, str], TimeWindow]:
    """Build TimeWindow instances from ISO date strings.

    This keeps TimeWindow construction succinct inside tests while staying
    explicit about the labels applied to analysis vs comparison windows.
    """

    def _factory(label: str, start: str, end: str) -> TimeWindow:
        return TimeWindow(label=label, start=_iso_date(start), end=_iso_date(end))

    return _factory


def _iso_date(value: str):
    from datetime import date

    year, month, day = map(int, value.split("-"))
    return date(year, month, day)


@pytest.fixture()
def load_analysis_dataset(app_config: AppConfig) -> Callable[[str], AppConfig]:
    """Load a JSON fixture by name into the migrated SQLite database.

    The JSON contract supports `accounts`, `categories`, and `transactions`
    arrays for spending analyses, plus optional asset-tracking blocks:
    `asset_sources`, `documents`, `instruments`, `holdings`, `holding_values`,
    and `portfolio_targets`. Accounts and categories use a `key` field so
    transactions and holdings can reference them symbolically. Missing optional
    fields fall back to deterministic defaults to keep fingerprints stable
    across runs.
    """

    def _loader(name: str) -> AppConfig:
        path = FIXTURE_ROOT / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown fin-analyze fixture: {name}")

        payload = json.loads(path.read_text())
        accounts = payload.get("accounts", [])
        categories = payload.get("categories", [])
        transactions = payload.get("transactions", [])

        asset_sources = payload.get("asset_sources", [])
        documents = payload.get("documents", [])
        instruments = payload.get("instruments", [])
        holdings = payload.get("holdings", [])
        holding_values = payload.get("holding_values", [])
        portfolio_targets = payload.get("portfolio_targets", [])

        with connect(app_config) as connection:
            # Wipe prior data so each fixture load is isolated.
            connection.execute("DELETE FROM holding_values")
            connection.execute("DELETE FROM asset_prices")
            connection.execute("DELETE FROM holdings")
            connection.execute("DELETE FROM instrument_classifications")
            connection.execute("DELETE FROM instruments")
            connection.execute("DELETE FROM documents")
            connection.execute("DELETE FROM asset_sources")
            connection.execute("DELETE FROM portfolio_targets")
            connection.execute("DELETE FROM transactions")
            connection.execute("DELETE FROM categories")
            connection.execute("DELETE FROM accounts")

            account_ids: dict[str, int] = {}
            for acct in accounts:
                key = acct.get("key") or acct["name"]
                cursor = connection.execute(
                    """
                    INSERT INTO accounts (name, institution, account_type, auto_detected)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        acct["name"],
                        acct["institution"],
                        acct["account_type"],
                        True,
                    ),
                )
                account_ids[key] = cursor.lastrowid

            category_ids: dict[str, int] = {}
            for category in categories:
                key = category.get("key") or f"{category['category']}::{category['subcategory']}"
                cursor = connection.execute(
                    """
                    INSERT INTO categories (
                        category, subcategory, user_approved, auto_generated
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        category["category"],
                        category["subcategory"],
                        bool(category.get("user_approved", False)),
                        bool(category.get("auto_generated", True)),
                    ),
                )
                category_ids[key] = cursor.lastrowid

            for index, txn in enumerate(transactions, start=1):
                account_key = txn.get("account")
                category_key = txn.get("category")
                if account_key not in account_ids:
                    raise KeyError(f"Account key '{account_key}' not defined in fixture '{name}'")
                if category_key not in category_ids:
                    raise KeyError(f"Category key '{category_key}' not defined in fixture '{name}'")

                metadata = txn.get("metadata")
                metadata_blob = json.dumps(metadata) if metadata is not None else None
                fingerprint = txn.get("fingerprint") or f"fixture-{name}-{index}"

                connection.execute(
                    """
                    INSERT INTO transactions (
                        date,
                        merchant,
                        amount,
                        category_id,
                        account_id,
                        original_description,
                        import_date,
                        categorization_confidence,
                        categorization_method,
                        fingerprint,
                        metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?)
                    """,
                    (
                        txn["date"],
                        txn["merchant"],
                        txn["amount"],
                        category_ids[category_key],
                        account_ids[account_key],
                        txn.get("original_description", txn["merchant"]),
                        float(txn.get("categorization_confidence", 0.95)),
                        txn.get("categorization_method", "fixture:test"),
                        fingerprint,
                        metadata_blob,
                    ),
                )

            if asset_sources or instruments or holdings or holding_values or portfolio_targets:
                source_ids: dict[str, int] = {}
                for source in asset_sources:
                    key = source.get("key") or source["name"]
                    cursor = connection.execute(
                        """
                        INSERT INTO asset_sources (name, source_type, priority, contact_url, metadata)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            source["name"],
                            source.get("source_type", "statement"),
                            int(source.get("priority", 1)),
                            source.get("contact_url"),
                            json.dumps(source.get("metadata")) if source.get("metadata") else None,
                        ),
                    )
                    source_ids[key] = cursor.lastrowid

                document_ids: dict[str, int] = {}
                for doc in documents:
                    key = doc.get("key") or doc.get("document_hash")
                    source_key = doc.get("source")
                    if source_key not in source_ids:
                        raise KeyError(
                            f"Document source '{source_key}' missing in fixture '{name}'"
                        )
                    cursor = connection.execute(
                        """
                        INSERT INTO documents (document_hash, source_id, broker, period_end_date, file_path, metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doc["document_hash"],
                            source_ids[source_key],
                            doc.get("broker"),
                            doc.get("period_end_date"),
                            doc.get("file_path"),
                            json.dumps(doc.get("metadata")) if doc.get("metadata") else None,
                        ),
                    )
                    document_ids[key] = cursor.lastrowid

                instrument_ids: dict[str, int] = {}
                for instrument in instruments:
                    key = instrument.get("key") or instrument["symbol"]
                    identifiers = instrument.get("identifiers") or {}
                    cursor = connection.execute(
                        """
                        INSERT INTO instruments (name, symbol, exchange, currency, vehicle_type, identifiers, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            instrument["name"],
                            instrument.get("symbol"),
                            instrument.get("exchange"),
                            instrument.get("currency", "USD"),
                            instrument.get("vehicle_type"),
                            json.dumps(identifiers) if identifiers else None,
                            (
                                json.dumps(instrument.get("metadata"))
                                if instrument.get("metadata")
                                else None
                            ),
                        ),
                    )
                    instrument_id = cursor.lastrowid
                    instrument_ids[key] = instrument_id

                    classification = instrument.get("classification")
                    if classification:
                        main = classification.get("main") or classification.get("main_class")
                        sub = classification.get("sub") or classification.get("sub_class")
                        row = connection.execute(
                            "SELECT id FROM asset_classes WHERE main_class = ? AND sub_class = ?",
                            (main, sub),
                        ).fetchone()
                        if not row:
                            raise KeyError(f"Asset class {main}/{sub} not seeded; fixture '{name}'")
                        connection.execute(
                            """
                            INSERT INTO instrument_classifications (instrument_id, asset_class_id, is_primary)
                            VALUES (?, ?, 1)
                            """,
                            (instrument_id, int(row["id"])),
                        )

                holding_ids: dict[str, int] = {}
                for holding in holdings:
                    account_key = holding.get("account")
                    instrument_key = holding.get("instrument")
                    if account_key not in account_ids:
                        raise KeyError(
                            f"Holding account '{account_key}' missing in fixture '{name}'"
                        )
                    if instrument_key not in instrument_ids:
                        raise KeyError(
                            f"Holding instrument '{instrument_key}' missing in fixture '{name}'"
                        )

                    cursor = connection.execute(
                        """
                        INSERT INTO holdings (
                            account_id, instrument_id, status, opened_at, closed_at, position_side, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            account_ids[account_key],
                            instrument_ids[instrument_key],
                            holding.get("status", "active"),
                            holding.get("opened_at"),
                            holding.get("closed_at"),
                            holding.get("position_side", "long"),
                            (
                                json.dumps(holding.get("metadata"))
                                if holding.get("metadata")
                                else None
                            ),
                        ),
                    )
                    holding_ids[holding.get("key") or f"holding-{cursor.lastrowid}"] = (
                        cursor.lastrowid
                    )

                for hv in holding_values:
                    holding_key = hv.get("holding")
                    source_key = hv.get("source")
                    document_key = hv.get("document")
                    if holding_key not in holding_ids:
                        raise KeyError(
                            f"Holding value missing holding '{holding_key}' in fixture '{name}'"
                        )
                    if source_key not in source_ids:
                        raise KeyError(
                            f"Holding value source '{source_key}' missing in fixture '{name}'"
                        )

                    document_id = document_ids.get(document_key) if document_key else None
                    connection.execute(
                        """
                        INSERT INTO holding_values (
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
                            metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            holding_ids[holding_key],
                            hv["as_of_date"],
                            hv.get("as_of_datetime"),
                            float(hv.get("quantity", 0.0)),
                            float(hv.get("price", 0.0)) if hv.get("price") is not None else None,
                            float(hv.get("market_value", 0.0)),
                            float(hv.get("accrued_interest", 0.0)),
                            float(hv.get("fees", 0.0)),
                            source_ids[source_key],
                            document_id,
                            hv.get("valuation_currency", "USD"),
                            float(hv.get("fx_rate_used", 1.0)),
                            json.dumps(hv.get("metadata")) if hv.get("metadata") else None,
                        ),
                    )

                for target in portfolio_targets:
                    class_ref = target.get("asset_class") or {}
                    main = class_ref.get("main") or class_ref.get("main_class")
                    sub = class_ref.get("sub") or class_ref.get("sub_class")
                    row = connection.execute(
                        "SELECT id FROM asset_classes WHERE main_class = ? AND sub_class = ?",
                        (main, sub),
                    ).fetchone()
                    if not row:
                        raise KeyError(
                            f"Portfolio target asset class {main}/{sub} missing in fixture '{name}'"
                        )

                    scope = target.get("scope", "portfolio")
                    scope_id = None
                    if scope == "account":
                        acct_key = target.get("account") or target.get("scope_id")
                        if acct_key not in account_ids:
                            raise KeyError(
                                f"Portfolio target account '{acct_key}' missing in fixture '{name}'"
                            )
                        scope_id = account_ids[acct_key]

                    connection.execute(
                        """
                        INSERT INTO portfolio_targets (scope, scope_id, asset_class_id, target_weight, as_of_date, metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scope,
                            scope_id,
                            int(row["id"]),
                            float(target["target_weight"]),
                            target.get("as_of_date"),
                            json.dumps(target.get("metadata")) if target.get("metadata") else None,
                        ),
                    )

        return app_config

    return _loader


@pytest.fixture()
def analysis_context(
    cli_context: CLIContext,
    app_config: AppConfig,
) -> Callable[
    [TimeWindow, TimeWindow | None, dict[str, object], bool, float | None, str], AnalysisContext
]:
    """Factory to build AnalysisContext instances for individual analyzers."""

    def _builder(
        window: TimeWindow,
        comparison: TimeWindow | None,
        options: dict[str, object] | None = None,
        compare: bool = False,
        threshold: float | None = None,
        output_format: str = "json",
    ) -> AnalysisContext:
        return AnalysisContext(
            cli_ctx=cli_context,
            app_config=app_config,
            window=window,
            comparison_window=comparison,
            output_format=output_format,
            compare=compare,
            threshold=threshold,
            options=options or {},
        )

    return _builder
