"""Core pipeline for importing CSV transactions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import sqlite3

from fin_cli.shared import models
from fin_cli.shared.config import AppConfig
from fin_cli.shared.logging import Logger

from .categorizer.hybrid import (
    CategoryProposal,
    CategorizationOptions,
    HybridCategorizer,
    HybridCategorizerResult,
    TransactionReview,
)
from .categorizer.rules import CategorizationOutcome
from .importer import CSVImportError, ImportedTransaction, load_csv_transactions


@dataclass(slots=True)
class ImportStats:
    inserted: int = 0
    duplicates: int = 0
    categorized: int = 0
    needs_review: int = 0


@dataclass(slots=True)
class ReviewQueue:
    """Container for reviewable items."""

    transactions: list[TransactionReview]
    category_proposals: list[CategoryProposal]


@dataclass(slots=True)
class ImportResult:
    stats: ImportStats
    review: ReviewQueue
    auto_created_categories: list[tuple[str, str]]


class ImportPipeline:
    def __init__(
        self,
        connection: sqlite3.Connection,
        logger: Logger,
        config: AppConfig,
        *,
        track_usage: bool = True,
    ) -> None:
        self.connection = connection
        self.logger = logger
        self.config = config
        self.categorizer = HybridCategorizer(
            connection,
            config,
            logger,
            track_usage=track_usage,
        )

    def load_transactions(self, csv_paths: Iterable[str | Path]) -> list[ImportedTransaction]:
        transactions: list[ImportedTransaction] = []
        for path in csv_paths:
            path_str = str(path)
            rows = load_csv_transactions(path_str if path_str != '-' else None)
            transactions.extend(rows)
            source_name = "stdin" if path_str == '-' else str(path)
            self.logger.info(f"Loaded {len(rows)} rows from {source_name}")
        return transactions

    def import_transactions(
        self,
        transactions: Sequence[ImportedTransaction],
        *,
        skip_dedupe: bool = False,
        skip_llm: bool = False,
        auto_assign_threshold: float | None = None,
    ) -> ImportResult:
        result = self._run_categorizer(
            transactions,
            skip_llm=skip_llm,
            apply_side_effects=True,
            auto_assign_threshold=auto_assign_threshold,
        )
        stats = self._persist_transactions(
            transactions,
            result.outcomes,
            skip_dedupe=skip_dedupe,
        )
        stats.needs_review = len(result.transaction_reviews)
        review = ReviewQueue(
            transactions=result.transaction_reviews,
            category_proposals=result.category_proposals,
        )
        return ImportResult(
            stats=stats,
            review=review,
            auto_created_categories=result.auto_created_categories,
        )

    def _run_categorizer(
        self,
        transactions: Sequence[ImportedTransaction],
        *,
        skip_llm: bool,
        apply_side_effects: bool,
        auto_assign_threshold: float | None,
    ) -> HybridCategorizerResult:
        needs_review_threshold = self.config.categorization.confidence.needs_review
        effective_auto_threshold = (
            auto_assign_threshold
            if auto_assign_threshold is not None
            else self.config.categorization.confidence.auto_approve
        )
        effective_auto_threshold = max(effective_auto_threshold, needs_review_threshold)
        options = CategorizationOptions(
            skip_llm=skip_llm or not self.config.categorization.llm.enabled,
            apply_side_effects=apply_side_effects,
            auto_assign_threshold=effective_auto_threshold,
            needs_review_threshold=needs_review_threshold,
        )
        return self.categorizer.categorize_transactions(transactions, options=options)

    def _persist_transactions(
        self,
        transactions: Sequence[ImportedTransaction],
        outcomes: Sequence[CategorizationOutcome],
        *,
        skip_dedupe: bool,
    ) -> ImportStats:
        stats = ImportStats()
        for txn, outcome in zip(transactions, outcomes, strict=False):
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
        return stats


def dry_run_preview(
    connection: sqlite3.Connection,
    logger: Logger,
    config: AppConfig,
    transactions: Sequence[ImportedTransaction],
    *,
    skip_llm: bool = False,
    auto_assign_threshold: float | None = None,
) -> ImportResult:
    pipeline = ImportPipeline(connection, logger, config, track_usage=False)
    result = pipeline._run_categorizer(
        transactions,
        skip_llm=skip_llm,
        apply_side_effects=False,
        auto_assign_threshold=auto_assign_threshold,
    )
    stats = ImportStats()
    stats.inserted = len(transactions)
    stats.categorized = sum(1 for outcome in result.outcomes if outcome.category_id)
    stats.needs_review = len(result.transaction_reviews)
    review = ReviewQueue(
        transactions=result.transaction_reviews,
        category_proposals=result.category_proposals,
    )
    return ImportResult(
        stats=stats,
        review=review,
        auto_created_categories=result.auto_created_categories,
    )
