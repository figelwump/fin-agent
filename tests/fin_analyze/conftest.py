"""Shared pytest fixtures for fin-analyze tests.

The fixtures here provide a consistently migrated SQLite database and
helpers to seed canonical datasets from JSON fixtures so analyzers and the
CLI can be exercised under reproducible conditions. The JSON format is kept
LLM-friendly: explicit keys, deterministic defaults, and minimal inference.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

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
    arrays. Accounts and categories use a `key` field so transactions can
    reference them symbolically. Missing optional fields fall back to
    deterministic defaults to keep fingerprints stable across runs.
    """

    def _loader(name: str) -> AppConfig:
        path = FIXTURE_ROOT / f"{name}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown fin-analyze fixture: {name}")

        payload = json.loads(path.read_text())
        accounts = payload.get("accounts", [])
        categories = payload.get("categories", [])
        transactions = payload.get("transactions", [])

        with connect(app_config) as connection:
            # Wipe prior data so each fixture load is isolated.
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

        return app_config

    return _loader


@pytest.fixture()
def analysis_context(
    cli_context: CLIContext,
    app_config: AppConfig,
) -> Callable[[TimeWindow, TimeWindow | None, dict[str, object], bool, float | None, str], AnalysisContext]:
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

