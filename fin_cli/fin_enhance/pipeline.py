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
class EnhancedTransaction:
    """Transaction with categorization results."""
    transaction: ImportedTransaction
    category: str | None = None
    subcategory: str | None = None
    confidence: float | None = None
    method: str | None = None


@dataclass(slots=True)
class ImportResult:
    stats: ImportStats
    review: ReviewQueue
    auto_created_categories: list[tuple[str, str]]
    enhanced_transactions: list[EnhancedTransaction] | None = None


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
        self._account_cache: dict[str, int] = {}

    def load_transactions(self, csv_paths: Iterable[str | Path]) -> list[ImportedTransaction]:
        transactions: list[ImportedTransaction] = []
        for path in csv_paths:
            path_str = str(path)
            source_name = "stdin" if path_str == "-" else str(path)
            self.logger.info(f"Reading transactions from {source_name}…")
            if path_str == "-":
                rows = load_csv_transactions(None)
            else:
                rows = load_csv_transactions(path)
            transactions.extend(rows)
            self.logger.info(f"Loaded {len(rows)} transaction row(s) from {source_name}")
        return transactions

    def import_transactions(
        self,
        transactions: Sequence[ImportedTransaction],
        *,
        skip_dedupe: bool = False,
        skip_llm: bool = False,
        auto_assign_threshold: float | None = None,
        include_enhanced: bool = False,
        force_auto_assign: bool = False,
    ) -> ImportResult:
        total_transactions = len(transactions)
        if total_transactions == 0:
            self.logger.info("No transactions supplied; skipping import pipeline.")
            empty_stats = ImportStats()
            empty_review = ReviewQueue(transactions=[], category_proposals=[])
            return ImportResult(
                stats=empty_stats,
                review=empty_review,
                auto_created_categories=[],
                enhanced_transactions=None,
            )

        self.logger.info(
            f"Stage 1/3: Categorizing {total_transactions} transaction(s)…"
        )
        result = self._run_categorizer(
            transactions,
            skip_llm=skip_llm,
            apply_side_effects=True,
            auto_assign_threshold=auto_assign_threshold,
            force_auto_assign=force_auto_assign,
        )
        if force_auto_assign:
            result.transaction_reviews = []
            result.category_proposals = []

        self.logger.info("Stage 1/3 complete.")

        self.logger.info("Stage 2/3: Persisting transactions to the database…")

        stats = self._persist_transactions(
            transactions,
            result.outcomes,
            skip_dedupe=skip_dedupe,
        )
        stats.needs_review = len(result.transaction_reviews)
        self.logger.info(
            "Database persistence complete: "
            f"inserted {stats.inserted}, duplicates skipped {stats.duplicates}."
        )
        review = ReviewQueue(
            transactions=result.transaction_reviews,
            category_proposals=result.category_proposals,
        )

        enhanced_transactions = None
        if include_enhanced:
            self.logger.info("Stage 3/3: Preparing enhanced transaction output…")
            enhanced_transactions = self._build_enhanced_transactions(
                transactions, result.outcomes
            )
            self.logger.info("Stage 3/3 complete.")

        self.logger.info("Import pipeline processing finished.")

        return ImportResult(
            stats=stats,
            review=review,
            auto_created_categories=result.auto_created_categories,
            enhanced_transactions=enhanced_transactions,
        )

    def _run_categorizer(
        self,
        transactions: Sequence[ImportedTransaction],
        *,
        skip_llm: bool,
        apply_side_effects: bool,
        auto_assign_threshold: float | None,
        force_auto_assign: bool,
    ) -> HybridCategorizerResult:
        effective_auto_threshold = (
            auto_assign_threshold
            if auto_assign_threshold is not None
            else self.config.categorization.confidence.auto_approve
        )
        options = CategorizationOptions(
            skip_llm=skip_llm or not self.config.categorization.llm.enabled,
            apply_side_effects=apply_side_effects,
            auto_assign_threshold=effective_auto_threshold,
            force_auto_assign=force_auto_assign,
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
        total = min(len(transactions), len(outcomes))
        progress_every = 500
        should_log_progress = total > progress_every
        for index, (txn, outcome) in enumerate(
            zip(transactions, outcomes, strict=False),
            start=1,
        ):
            account_id = self._resolve_account_id(txn)
            metadata_payload = None
            if outcome.pattern_key or outcome.pattern_display or outcome.merchant_metadata:
                # Persist merchant enrichment details so downstream analysis/reporting can reuse
                # the canonical display name and any extra metadata emitted by the LLM.
                metadata_payload = {}
                if outcome.pattern_key:
                    metadata_payload["merchant_pattern_key"] = outcome.pattern_key
                if outcome.pattern_display:
                    metadata_payload["merchant_pattern_display"] = outcome.pattern_display
                if outcome.merchant_metadata:
                    metadata_payload["merchant_metadata"] = dict(outcome.merchant_metadata)
            model_txn = models.Transaction(
                date=txn.date,
                merchant=txn.merchant,
                amount=txn.amount,
                account_id=account_id,
                account_key=txn.account_key,
                category_id=outcome.category_id,
                original_description=txn.original_description,
                categorization_confidence=outcome.confidence if outcome.category_id else None,
                categorization_method=outcome.method,
                metadata=metadata_payload,
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
            if should_log_progress and index % progress_every == 0:
                self.logger.info(
                    f"Database progress: processed {index}/{total} transaction(s)…"
                )
        if should_log_progress and total % progress_every != 0:
            self.logger.info(
                f"Database progress: processed {total}/{total} transaction(s)."
            )
        return stats

    def _resolve_account_id(self, txn: ImportedTransaction) -> int:
        """Lookup or create the backing account for an imported transaction."""

        if txn.account_id is not None:
            return txn.account_id
        cache_key = txn.account_key or models.compute_account_key(
            txn.account_name,
            txn.institution,
            txn.account_type,
        )
        if cache_key in self._account_cache:
            account_id = self._account_cache[cache_key]
        else:
            account_id = models.upsert_account(
                self.connection,
                name=txn.account_name,
                institution=txn.institution,
                account_type=txn.account_type,
            )
            self._account_cache[cache_key] = account_id
        txn.account_id = account_id
        txn.account_key = cache_key
        return account_id

    def _build_enhanced_transactions(
        self,
        transactions: Sequence[ImportedTransaction],
        outcomes: Sequence[CategorizationOutcome],
    ) -> list[EnhancedTransaction]:
        """Build enhanced transactions with category information."""
        enhanced = []
        for txn, outcome in zip(transactions, outcomes, strict=False):
            category = None
            subcategory = None
            if outcome.category_id:
                # Fetch category details
                row = self.connection.execute(
                    "SELECT category, subcategory FROM categories WHERE id = ?",
                    (outcome.category_id,),
                ).fetchone()
                if row:
                    category = row["category"]
                    subcategory = row["subcategory"]

            enhanced.append(
                EnhancedTransaction(
                    transaction=txn,
                    category=category,
                    subcategory=subcategory,
                    confidence=outcome.confidence if outcome.category_id else None,
                    method=outcome.method,
                )
            )
        return enhanced


def dry_run_preview(
    connection: sqlite3.Connection,
    logger: Logger,
    config: AppConfig,
    transactions: Sequence[ImportedTransaction],
    *,
    skip_llm: bool = False,
    auto_assign_threshold: float | None = None,
    force_auto_assign: bool = False,
) -> ImportResult:
    pipeline = ImportPipeline(connection, logger, config, track_usage=False)
    result = pipeline._run_categorizer(
        transactions,
        skip_llm=skip_llm,
        apply_side_effects=False,
        auto_assign_threshold=auto_assign_threshold,
        force_auto_assign=force_auto_assign,
    )
    if force_auto_assign:
        result.transaction_reviews = []
        result.category_proposals = []
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


__all__ = [
    "EnhancedTransaction",
    "ImportPipeline",
    "ImportResult",
    "ImportStats",
    "ReviewQueue",
    "dry_run_preview",
]
