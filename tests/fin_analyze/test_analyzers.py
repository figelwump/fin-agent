from __future__ import annotations

from datetime import date

import pytest

from fin_cli.fin_analyze.analyzers import (
    category_suggestions,
    merchant_frequency,
    spending_patterns,
    subscription_detect,
    unusual_spending,
)
from fin_cli.fin_analyze.types import AnalysisContext, TimeWindow
from fin_cli.shared import paths
from fin_cli.shared.cli import CLIContext
from fin_cli.shared.config import load_config
from fin_cli.shared.database import connect, run_migrations
from fin_cli.shared.logging import get_logger


@pytest.fixture()
def app_config(tmp_path):
    db_path = tmp_path / "analytics.db"
    env = {paths.DATABASE_PATH_ENV: str(db_path)}
    config = load_config(env=env)
    run_migrations(config)
    return config


def _cli_context(config):
    return CLIContext(
        config=config,
        db_path=config.database.path,
        dry_run=False,
        verbose=False,
        logger=get_logger(verbose=False),
    )


def _window(year: int, month: int) -> TimeWindow:
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)
    return TimeWindow(label=f"month_{year}_{month:02d}", start=start, end=end)


def _insert_transaction(connection, *, txn_date: date, merchant: str, amount: float, category_id: int) -> None:
    connection.execute(
        """
        INSERT INTO transactions (
            date, merchant, amount, category_id, account_id,
            original_description, import_date, categorization_confidence,
            categorization_method, fingerprint
        ) VALUES (?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP, 0.9, 'rule:test', ?)
        """,
        (
            txn_date.isoformat(),
            merchant,
            amount,
            category_id,
            merchant,
            f"{txn_date.isoformat()}-{merchant}-{amount}",
        ),
    )


def _seed_subscription_dataset(config) -> None:
    with connect(config) as connection:
        account_id = connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
            ("Primary", "TestBank", "checking"),
        ).fetchone()[0]
        connection.execute("UPDATE accounts SET id = 1 WHERE id = ?", (account_id,))
        connection.execute("DELETE FROM accounts WHERE id <> 1")
        subscription_cat = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Subscriptions", "Streaming"),
        ).fetchone()[0]

        # July charges (comparison window)
        _insert_transaction(connection, txn_date=date(2025, 7, 5), merchant="NETFLIX", amount=-15.99, category_id=subscription_cat)
        _insert_transaction(connection, txn_date=date(2025, 7, 18), merchant="SPOTIFY", amount=-12.99, category_id=subscription_cat)
        _insert_transaction(connection, txn_date=date(2025, 7, 10), merchant="HULU", amount=-11.99, category_id=subscription_cat)

        # August charges (analysis window)
        _insert_transaction(connection, txn_date=date(2025, 8, 5), merchant="NETFLIX", amount=-19.99, category_id=subscription_cat)
        _insert_transaction(connection, txn_date=date(2025, 8, 18), merchant="SPOTIFY", amount=-12.99, category_id=subscription_cat)
        _insert_transaction(connection, txn_date=date(2025, 8, 20), merchant="DISNEY+", amount=-13.99, category_id=subscription_cat)


def _seed_spending_dataset(config) -> None:
    with connect(config) as connection:
        account_id = connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
            ("Primary", "TestBank", "checking"),
        ).fetchone()[0]
        connection.execute("UPDATE accounts SET id = 1 WHERE id = ?", (account_id,))
        connection.execute("DELETE FROM accounts WHERE id <> 1")
        shopping_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Shopping", "Online"),
        ).fetchone()[0]
        dining_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Food & Dining", "Restaurants"),
        ).fetchone()[0]

        # Baseline month (July)
        _insert_transaction(connection, txn_date=date(2025, 7, 8), merchant="AMAZON", amount=-45.00, category_id=shopping_id)
        _insert_transaction(connection, txn_date=date(2025, 7, 15), merchant="AMAZON", amount=-35.00, category_id=shopping_id)
        _insert_transaction(connection, txn_date=date(2025, 7, 12), merchant="LOCAL CAFE", amount=-22.00, category_id=dining_id)
        _insert_transaction(connection, txn_date=date(2025, 7, 20), merchant="TARGET", amount=-80.00, category_id=shopping_id)

        # Analysis month (August)
        for day, amt in [(5, -120.0), (12, -95.0), (20, -110.0)]:
            _insert_transaction(connection, txn_date=date(2025, 8, day), merchant="AMAZON", amount=amt, category_id=shopping_id)
        _insert_transaction(connection, txn_date=date(2025, 8, 10), merchant="LOCAL CAFE", amount=-18.00, category_id=dining_id)
        _insert_transaction(connection, txn_date=date(2025, 8, 22), merchant="TESLA SUPERCHARGER", amount=-60.00, category_id=shopping_id)



def _seed_category_overlap_dataset(config) -> None:
    with connect(config) as connection:
        account_id = connection.execute(
            "INSERT INTO accounts (name, institution, account_type) VALUES (?, ?, ?) RETURNING id",
            ("Primary", "TestBank", "checking"),
        ).fetchone()[0]
        connection.execute("UPDATE accounts SET id = 1 WHERE id = ?", (account_id,))
        connection.execute("DELETE FROM accounts WHERE id <> 1")
        coffee_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Coffee", "General"),
        ).fetchone()[0]
        coffee_shops_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Coffee Shops", "Specialty"),
        ).fetchone()[0]
        tea_id = connection.execute(
            "INSERT INTO categories (category, subcategory) VALUES (?, ?) RETURNING id",
            ("Beverages", "Tea"),
        ).fetchone()[0]

        for merchant in ["BLUE BOTTLE", "STARBUCKS", "PHILZ COFFEE"]:
            _insert_transaction(connection, txn_date=date(2025, 8, 5), merchant=merchant, amount=-12.50, category_id=coffee_id)
            _insert_transaction(connection, txn_date=date(2025, 8, 12), merchant=merchant, amount=-13.75, category_id=coffee_shops_id)

        _insert_transaction(connection, txn_date=date(2025, 8, 9), merchant="PEETS TEA BAR", amount=-9.50, category_id=tea_id)
        _insert_transaction(connection, txn_date=date(2025, 8, 16), merchant="MATCHA PLACE", amount=-11.25, category_id=tea_id)


def test_subscription_detection_flags_new_and_price_increase(app_config):
    _seed_subscription_dataset(app_config)
    context = AnalysisContext(
        cli_ctx=_cli_context(app_config),
        app_config=app_config,
        window=_window(2025, 8),
        comparison_window=_window(2025, 7),
        output_format="json",
        compare=True,
        threshold=0.05,
        options={"include_inactive": True},
    )

    result = subscription_detect.analyze(context)
    payload = result.json_payload

    merchants = {entry["merchant"] for entry in payload["subscriptions"]}
    assert "NETFLIX" in merchants

    price_merchants = {entry["merchant"] for entry in payload["price_increases"]}
    assert "NETFLIX" in price_merchants

    new_names = {entry["merchant"] for entry in payload["new_merchants"]}
    assert "DISNEY+" in new_names

    cancelled_names = {entry["merchant"] for entry in payload["cancelled"]}
    assert "HULU" in cancelled_names


def test_unusual_spending_flags_large_increase(app_config):
    _seed_spending_dataset(app_config)
    context = AnalysisContext(
        cli_ctx=_cli_context(app_config),
        app_config=app_config,
        window=_window(2025, 8),
        comparison_window=_window(2025, 7),
        output_format="json",
        compare=True,
        threshold=0.10,
        options={"sensitivity": 3},
    )

    result = unusual_spending.analyze(context)
    payload = result.json_payload

    anomaly_merchants = {entry["merchant"] for entry in payload["anomalies"]}
    assert "AMAZON" in anomaly_merchants

    assert "TESLA SUPERCHARGER" in payload["new_merchants"]



def test_merchant_frequency_reports_new_and_dropped(app_config):
    _seed_spending_dataset(app_config)
    context = AnalysisContext(
        cli_ctx=_cli_context(app_config),
        app_config=app_config,
        window=_window(2025, 8),
        comparison_window=_window(2025, 7),
        output_format="json",
        compare=True,
        threshold=0.10,
        options={"min_visits": 1},
    )

    result = merchant_frequency.analyze(context)
    payload = result.json_payload

    merchants = {entry["canonical"]: entry for entry in payload["merchants"]}
    amazon = merchants.get("AMAZON")
    assert amazon and amazon["visits"] == 3
    assert any(name.startswith("Tesla") for name in payload["new_merchants"])
    assert any(name.startswith("Target") for name in payload["dropped_merchants"])


def test_spending_patterns_day_group(app_config):
    _seed_spending_dataset(app_config)
    context = AnalysisContext(
        cli_ctx=_cli_context(app_config),
        app_config=app_config,
        window=_window(2025, 8),
        comparison_window=_window(2025, 7),
        output_format="json",
        compare=True,
        threshold=0.10,
        options={"group_by": "day"},
    )

    result = spending_patterns.analyze(context)
    patterns = {entry["label"]: entry for entry in result.json_payload["patterns"]}
    assert "Tuesday" in patterns
    assert "Sunday" in patterns
    assert patterns["Tuesday"]["spend"] > patterns["Sunday"]["spend"]


def test_category_suggestions_overlap(app_config):
    _seed_category_overlap_dataset(app_config)
    context = AnalysisContext(
        cli_ctx=_cli_context(app_config),
        app_config=app_config,
        window=_window(2025, 8),
        comparison_window=None,
        output_format="json",
        compare=False,
        threshold=0.10,
        options={"min_overlap": 0.8},
    )

    result = category_suggestions.analyze(context)
    suggestions = result.json_payload["suggestions"]
    assert any(
        suggestion["from"] == "Coffee > General" and suggestion["to"] == "Coffee Shops > Specialty"
        for suggestion in suggestions
    )
