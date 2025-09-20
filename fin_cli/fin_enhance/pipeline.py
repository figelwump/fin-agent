"""Core pipeline for importing CSV transactions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import sqlite3

from fin_cli.shared import models
from fin_cli.shared.logging import Logger

from .categorizer.rules import CategorizationOutcome, RuleCategorizer
from .importer import CSVImportError, ImportedTransaction, load_csv_transactions


@dataclass(slots=True)
class ImportStats:
    inserted: int = 0
    duplicates: int = 0
    categorized: int = 0
    needs_review: int = 0


@dataclass(slots=True)
class ReviewCandidate:
    fingerprint: str
    date: str
    merchant: str
    amount: float
    original_description: str
    account_id: int | None


@dataclass(slots=True)
class ImportResult:
    stats: ImportStats
    review_items: list[ReviewCandidate]


class ImportPipeline:
    def __init__(
        self,
        connection: sqlite3.Connection,
        logger: Logger,
        *,
        track_usage: bool = True,
    ) -> None:
        self.connection = connection
        self.logger = logger
        self.categorizer = RuleCategorizer(connection, track_usage=track_usage)

    def load_transactions(self, csv_paths: Iterable[str | Path]) -> list[ImportedTransaction]:
        transactions: list[ImportedTransaction] = []
        for path in csv_paths:
            rows = load_csv_transactions(path)
            transactions.extend(rows)
            self.logger.info(f"Loaded {len(rows)} rows from {path}")
        return transactions

    def import_transactions(
        self,
        transactions: Iterable[ImportedTransaction],
        *,
        skip_dedupe: bool = False,
    ) -> ImportResult:
        stats = ImportStats()
        review_items: list[ReviewCandidate] = []
        for txn in transactions:
            outcome = self.categorizer.categorize(txn.merchant)
            model_txn = models.Transaction(
                date=txn.date,
                merchant=txn.merchant,
                amount=txn.amount,
                account_id=txn.account_id,
                category_id=outcome.category_id,
                original_description=txn.original_description,
                categorization_confidence=outcome.confidence if outcome.category_id else None,
                categorization_method=outcome.method,
                needs_review=outcome.needs_review,
            )
            inserted = models.insert_transaction(
                self.connection,
                model_txn,
                allow_update=True,
                skip_dedupe=skip_dedupe,
            )
            if inserted:
                stats.inserted += 1
                if outcome.category_id:
                    stats.categorized += 1
                    models.increment_category_usage(
                        self.connection,
                        outcome.category_id,
                    )
            else:
                stats.duplicates += 1
            if outcome.needs_review:
                stats.needs_review += 1
                review_items.append(
                    ReviewCandidate(
                        fingerprint=model_txn.fingerprint(),
                        date=txn.date.isoformat(),
                        merchant=txn.merchant,
                        amount=txn.amount,
                        original_description=txn.original_description,
                        account_id=txn.account_id,
                    )
                )
        return ImportResult(stats=stats, review_items=review_items)


def dry_run_preview(
    connection: sqlite3.Connection,
    logger: Logger,
    transactions: Iterable[ImportedTransaction],
) -> ImportResult:
    pipeline = ImportPipeline(connection, logger, track_usage=False)
    stats = ImportStats()
    review_items: list[ReviewCandidate] = []
    items = list(transactions)
    for txn in items:
        outcome = pipeline.categorizer.categorize(txn.merchant)
        if outcome.category_id:
            stats.categorized += 1
        else:
            stats.needs_review += 1
            review_items.append(
                ReviewCandidate(
                    fingerprint=models.compute_transaction_fingerprint(
                        txn.date,
                        txn.amount,
                        txn.merchant,
                        txn.account_id,
                    ),
                    date=txn.date.isoformat(),
                    merchant=txn.merchant,
                    amount=txn.amount,
                    original_description=txn.original_description,
                    account_id=txn.account_id,
                )
            )
    stats.inserted = len(items)
    return ImportResult(stats=stats, review_items=review_items)
