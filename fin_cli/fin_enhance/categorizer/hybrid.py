"""Hybrid categorization pipeline combining rules and LLM suggestions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Mapping, Sequence

import sqlite3

from fin_cli.shared import models
from fin_cli.shared.config import AppConfig
from fin_cli.shared.logging import Logger

from .llm_client import (
    LLMClient,
    LLMClientError,
    LLMRequestItem,
    LLMResult,
    LLMSuggestion,
    deserialize_llm_results,
    merchant_pattern_key,
    normalize_merchant,
    serialize_llm_results,
)
from .rules import CategorizationOutcome, RuleCategorizer
from ..importer import ImportedTransaction


@dataclass(slots=True)
class ReviewSuggestion:
    category: str
    subcategory: str
    confidence: float
    is_new_category: bool
    notes: str | None = None


@dataclass(slots=True)
class SimilarTransaction:
    category: str
    subcategory: str
    count: int


@dataclass(slots=True)
class ReviewExample:
    fingerprint: str
    date: str
    merchant: str
    amount: float
    original_description: str
    account_id: int | None


@dataclass(slots=True)
class TransactionReview:
    example: ReviewExample
    suggestions: list[ReviewSuggestion]
    similar: list[SimilarTransaction]


@dataclass(slots=True)
class CategoryProposal:
    category: str
    subcategory: str
    confidence: float
    transaction_examples: list[ReviewExample] = field(default_factory=list)
    support_count: int = 0
    total_amount: float = 0.0


@dataclass(slots=True)
class HybridCategorizerResult:
    outcomes: list[CategorizationOutcome]
    transaction_reviews: list[TransactionReview]
    category_proposals: list[CategoryProposal]
    auto_created_categories: list[tuple[str, str]]


@dataclass(slots=True)
class CategorizationOptions:
    skip_llm: bool
    apply_side_effects: bool
    auto_assign_threshold: float
    needs_review_threshold: float


class HybridCategorizer:
    """Coordinate rules + LLM categorization."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        config: AppConfig,
        logger: Logger,
        *,
        track_usage: bool = True,
    ) -> None:
        self.connection = connection
        self.config = config
        self.logger = logger
        self.rule_categorizer = RuleCategorizer(connection, track_usage=track_usage)
        self.llm_client = LLMClient(config, logger)
        self._dynamic_cfg = config.categorization.dynamic_categories

    def categorize_transactions(
        self,
        transactions: Sequence[ImportedTransaction],
        *,
        options: CategorizationOptions,
    ) -> HybridCategorizerResult:
        outcomes: list[CategorizationOutcome] = []
        transaction_reviews: list[TransactionReview] = []
        category_proposals_map: dict[tuple[str, str], CategoryProposal] = {}
        auto_created: list[tuple[str, str]] = []

        merchant_batches: Dict[str, list[tuple[int, ImportedTransaction]]] = defaultdict(list)

        for idx, txn in enumerate(transactions):
            outcome = self.rule_categorizer.categorize(txn.merchant)
            outcomes.append(outcome)
            if outcome.category_id is None:
                if options.skip_llm:
                    detail = self._fallback_review(txn)
                    outcomes[idx] = detail.outcome
                    if detail.review is not None:
                        transaction_reviews.append(detail.review)
                else:
                    merchant_key = normalize_merchant(txn.merchant)
                    merchant_batches[merchant_key].append((idx, txn))

        if merchant_batches and not self.llm_client.enabled:
            self.logger.warning(
                "LLM categorization requested but client is disabled. Falling back to review queue only."
            )

        llm_results: dict[str, LLMResult] = {}
        known_categories = self._fetch_known_categories()
        if merchant_batches:
            cached_results, pending_batches = self._resolve_cache(merchant_batches)
            llm_results.update(cached_results)
            if pending_batches:
                fetched = self._fetch_from_llm(pending_batches, known_categories)
                llm_results.update(fetched)
                self._persist_cache(fetched)

        for merchant_key, entries in merchant_batches.items():
            result = llm_results.get(merchant_key)
            for idx, txn in entries:
                if result:
                    detail = self._apply_llm_suggestions(
                        txn,
                        result.suggestions,
                        options,
                        category_proposals_map,
                        auto_created,
                    )
                else:
                    detail = self._fallback_review(txn)
                outcomes[idx] = detail.outcome
                if detail.review is not None:
                    transaction_reviews.append(detail.review)

        category_proposals = list(category_proposals_map.values())
        return HybridCategorizerResult(
            outcomes=outcomes,
            transaction_reviews=transaction_reviews,
            category_proposals=category_proposals,
            auto_created_categories=auto_created,
        )

    def _resolve_cache(
        self,
        merchant_batches: Mapping[str, list[tuple[int, ImportedTransaction]]],
    ) -> tuple[dict[str, LLMResult], dict[str, list[LLMRequestItem]]]:
        cached: dict[str, LLMResult] = {}
        pending: dict[str, list[LLMRequestItem]] = {}
        for merchant_key, entries in merchant_batches.items():
            row = models.fetch_llm_cache_entry(self.connection, merchant_key)
            if row:
                cached_payload = deserialize_llm_results(str(row["response_json"]))
                if merchant_key in cached_payload:
                    cached[merchant_key] = cached_payload[merchant_key]
                    continue
            pending[merchant_key] = [
                LLMRequestItem(
                    merchant=txn.merchant,
                    original_description=txn.original_description,
                    amount=txn.amount,
                    date=txn.date.isoformat(),
                )
                for _, txn in entries
            ]
        return cached, pending

    def _fetch_from_llm(
        self,
        batches: Mapping[str, list[LLMRequestItem]],
        known_categories: Sequence[dict[str, str]] | None,
    ) -> dict[str, LLMResult]:
        try:
            return self.llm_client.categorize_batch(batches, known_categories=known_categories)
        except LLMClientError as exc:
            self.logger.warning(f"LLM categorization failed: {exc}")
            return {}

    def _fetch_known_categories(self) -> list[dict[str, str]]:
        rows = models.fetch_all_categories(self.connection)
        return [
            {"category": str(row["category"]), "subcategory": str(row["subcategory"])}
            for row in rows
            if row["category"] and row["subcategory"]
        ]

    def _persist_cache(self, results: Mapping[str, LLMResult]) -> None:
        if not results:
            return
        for merchant_key, result in results.items():
            models.upsert_llm_cache_entry(
                self.connection,
                merchant_normalized=merchant_key,
                response_json=serialize_llm_results({merchant_key: result}),
                model=self.config.categorization.llm.model,
            )

    @dataclass(slots=True)
    class _LLMDetail:
        outcome: CategorizationOutcome
        review: TransactionReview | None

    def _apply_llm_suggestions(
        self,
        txn: ImportedTransaction,
        suggestions: Sequence[LLMSuggestion],
        options: CategorizationOptions,
        category_proposals_map: dict[tuple[str, str], CategoryProposal],
        auto_created: list[tuple[str, str]],
    ) -> "HybridCategorizer._LLMDetail":
        if not suggestions:
            return self._fallback_review(txn)

        sorted_suggestions = sorted(suggestions, key=lambda s: s.confidence, reverse=True)
        best = sorted_suggestions[0]
        review_suggestions = [
            ReviewSuggestion(
                category=s.category,
                subcategory=s.subcategory,
                confidence=s.confidence,
                is_new_category=s.is_new_category,
                notes=s.notes,
            )
            for s in sorted_suggestions
        ]

        review_entry = TransactionReview(
            example=self._build_example(txn),
            suggestions=review_suggestions,
            similar=self._fetch_similar_transactions(txn.merchant),
        )

        category_id = None
        needs_review = True
        method: str | None = None
        confidence = best.confidence

        existing_category_id = models.find_category_id(
            self.connection,
            category=best.category,
            subcategory=best.subcategory,
        )

        created_missing_category = False
        if (
            existing_category_id is None
            and confidence >= options.auto_assign_threshold
            and options.apply_side_effects
        ):
            # The LLM referenced a known taxonomy entry that we have not seen locally yet.
            # Create it on the fly so we can honor the high-confidence suggestion.
            existing_category_id = models.get_or_create_category(
                self.connection,
                category=best.category,
                subcategory=best.subcategory,
                auto_generated=True,
                user_approved=False,
            )
            created_missing_category = True
            key = (best.category, best.subcategory)
            if key not in auto_created:
                auto_created.append(key)

        if existing_category_id is not None and confidence >= options.auto_assign_threshold:
            category_id = existing_category_id
            needs_review = False
            method = "llm:auto"
        elif best.is_new_category:
            category_id, needs_review, method = self._handle_new_category_suggestion(
                txn,
                best,
                options,
                category_proposals_map,
                auto_created,
            )
        elif existing_category_id is not None and confidence >= options.needs_review_threshold:
            # Suggestion is plausible but below auto threshold; mark for review with hint.
            category_id = None
            needs_review = True
            method = None
        else:
            # Low confidence or unknown category; keep review entry only.
            category_id = None
            needs_review = True
            method = None

        outcome = CategorizationOutcome(
            category_id=category_id,
            confidence=confidence if category_id else 0.0,
            method=method,
            needs_review=needs_review,
        )

        if not needs_review:
            if category_id is not None and options.apply_side_effects:
                self._record_merchant_pattern(txn, category_id, confidence)
            return HybridCategorizer._LLMDetail(outcome=outcome, review=None)
        return HybridCategorizer._LLMDetail(outcome=outcome, review=review_entry)

    def _handle_new_category_suggestion(
        self,
        txn: ImportedTransaction,
        suggestion: LLMSuggestion,
        options: CategorizationOptions,
        category_proposals_map: dict[tuple[str, str], CategoryProposal],
        auto_created: list[tuple[str, str]],
    ) -> tuple[int | None, bool, str | None]:
        key = (suggestion.category, suggestion.subcategory)
        existing_row = self.connection.execute(
            "SELECT * FROM category_suggestions WHERE category = ? AND subcategory = ?",
            key,
        ).fetchone()
        support_count = int(existing_row["support_count"]) if existing_row else 0
        total_amount = float(existing_row["total_amount"]) if existing_row else 0.0
        max_conf = float(existing_row["max_confidence"]) if existing_row else 0.0
        status = str(existing_row["status"]) if existing_row else "pending"

        pending_support = support_count + 1
        pending_amount = total_amount + abs(txn.amount)
        pending_conf = max(max_conf, suggestion.confidence)

        if status == "auto-approved":
            category_id = models.find_category_id(
                self.connection,
                category=suggestion.category,
                subcategory=suggestion.subcategory,
            )
            if category_id is not None:
                return category_id, False, "llm:auto-new-category"

        auto_threshold = self._dynamic_cfg.auto_approve_confidence
        min_support = self._dynamic_cfg.min_transactions_for_new

        if (
            suggestion.confidence >= auto_threshold
            and pending_support >= min_support
            and options.apply_side_effects
        ):
            category_id = models.get_or_create_category(
                self.connection,
                category=suggestion.category,
                subcategory=suggestion.subcategory,
                auto_generated=True,
                user_approved=True,
            )
            models.record_category_suggestion(
                self.connection,
                category=suggestion.category,
                subcategory=suggestion.subcategory,
                amount=txn.amount,
                confidence=suggestion.confidence,
            )
            models.set_category_suggestion_status(
                self.connection,
                category=suggestion.category,
                subcategory=suggestion.subcategory,
                status="auto-approved",
            )
            auto_created.append(key)
            self._record_merchant_pattern(txn, category_id, suggestion.confidence)
            return category_id, False, "llm:auto-new-category"

        proposal = category_proposals_map.get(key)
        if proposal is None:
            proposal = CategoryProposal(
                category=suggestion.category,
                subcategory=suggestion.subcategory,
                confidence=pending_conf,
            )
            category_proposals_map[key] = proposal
        proposal.transaction_examples.append(self._build_example(txn))
        proposal.total_amount = max(proposal.total_amount, pending_amount)
        proposal.confidence = max(proposal.confidence, suggestion.confidence)
        proposal.support_count = max(proposal.support_count, pending_support)

        if options.apply_side_effects:
            models.record_category_suggestion(
                self.connection,
                category=suggestion.category,
                subcategory=suggestion.subcategory,
                amount=txn.amount,
                confidence=suggestion.confidence,
            )
        return None, True, None

    def _record_merchant_pattern(self, txn: ImportedTransaction, category_id: int, confidence: float) -> None:
        pattern = merchant_pattern_key(txn.merchant)
        if not pattern:
            return
        models.record_merchant_pattern(
            self.connection,
            pattern=pattern,
            category_id=category_id,
            confidence=confidence,
        )

    def _fallback_review(self, txn: ImportedTransaction) -> "HybridCategorizer._LLMDetail":
        outcome = CategorizationOutcome(
            category_id=None,
            confidence=0.0,
            method=None,
            needs_review=True,
        )
        review = TransactionReview(
            example=self._build_example(txn),
            suggestions=[],
            similar=self._fetch_similar_transactions(txn.merchant),
        )
        return HybridCategorizer._LLMDetail(outcome=outcome, review=review)

    def _build_example(self, txn: ImportedTransaction) -> ReviewExample:
        fingerprint = models.compute_transaction_fingerprint(
            txn.date,
            txn.amount,
            txn.merchant,
            txn.account_id,
        )
        return ReviewExample(
            fingerprint=fingerprint,
            date=txn.date.isoformat(),
            merchant=txn.merchant,
            amount=txn.amount,
            original_description=txn.original_description,
            account_id=txn.account_id,
        )

    def _fetch_similar_transactions(self, merchant: str) -> list[SimilarTransaction]:
        rows = self.connection.execute(
            """
            SELECT c.category, c.subcategory, COUNT(*) as cnt
            FROM transactions t
            JOIN categories c ON t.category_id = c.id
            WHERE t.merchant = ?
            GROUP BY c.category, c.subcategory
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (merchant,),
        ).fetchall()
        return [
            SimilarTransaction(
                category=str(row["category"]),
                subcategory=str(row["subcategory"]),
                count=int(row["cnt"]),
            )
            for row in rows
        ]
