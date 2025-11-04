"""Review queue helpers for fin-enhance."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fin_cli.shared import models

from .categorizer.hybrid import (
    CategoryProposal,
    ReviewExample,
    ReviewSuggestion,
    TransactionReview,
)
from .categorizer.llm_client import merchant_pattern_key
from .pipeline import ReviewQueue


def write_review_file(path: Path, review_queue: ReviewQueue) -> None:
    """Serialize review items (transactions + category proposals) to JSON."""

    data = {
        "version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "review_needed": [
            *_serialize_category_proposals(review_queue.category_proposals),
            *_serialize_transaction_reviews(review_queue.transactions),
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class ReviewApplicationError(Exception):
    """Raised when a review decision file cannot be applied."""


def apply_review_file(connection: sqlite3.Connection, file_path: Path) -> tuple[int, int]:
    """Apply review decisions from a JSON file.

    Returns a tuple of (applied_count, skipped_count).
    """

    if not file_path.exists():
        raise ReviewApplicationError(f"Review decisions file not found: {file_path}")
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReviewApplicationError(f"Invalid review decisions JSON: {exc}") from exc

    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        raise ReviewApplicationError("Review decisions file must contain a 'decisions' list.")

    applied = 0
    skipped = 0
    for entry in decisions:
        if not isinstance(entry, dict):
            skipped += 1
            continue
        fingerprint = entry.get("id")
        category = entry.get("category")
        subcategory = entry.get("subcategory")
        learn = bool(entry.get("learn", True))
        confidence = float(entry.get("confidence", 1.0))
        method = str(entry.get("method") or "review:manual")
        if not fingerprint or not category or not subcategory:
            skipped += 1
            continue
        txn_row = models.fetch_transaction_by_fingerprint(connection, fingerprint)
        if txn_row is None:
            skipped += 1
            continue
        category_id = models.get_or_create_category(
            connection,
            category=category,
            subcategory=subcategory,
            auto_generated=False,
            user_approved=True,
        )
        models.apply_review_decision(
            connection,
            fingerprint=fingerprint,
            category_id=category_id,
            confidence=confidence,
            method=method,
        )
        models.increment_category_usage(connection, category_id)
        models.set_category_suggestion_status(
            connection,
            category=category,
            subcategory=subcategory,
            status="approved",
        )
        if learn:
            merchant = str(txn_row["merchant"])
            pattern = merchant_pattern_key(merchant)
            if pattern:  # Only record if we get a valid pattern
                models.record_merchant_pattern(
                    connection,
                    pattern=pattern,
                    category_id=category_id,
                    confidence=confidence,
                )
        applied += 1
    return applied, skipped


def _serialize_transaction_reviews(items: list[TransactionReview]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in items:
        serialized.append(
            {
                "type": "transaction_review",
                "id": item.example.fingerprint,
                "date": item.example.date,
                "merchant": item.example.merchant,
                "amount": item.example.amount,
                "original_description": item.example.original_description,
                "account_id": item.example.account_id,
                "suggestions": [
                    _serialize_suggestion(suggestion) for suggestion in item.suggestions
                ],
                "similar_transactions": [
                    {
                        "category": similar.category,
                        "subcategory": similar.subcategory,
                        "count": similar.count,
                    }
                    for similar in item.similar
                ],
            }
        )
    return serialized


def _serialize_category_proposals(items: list[CategoryProposal]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for proposal in items:
        serialized.append(
            {
                "type": "new_category_approval",
                "proposed_category": proposal.category,
                "proposed_subcategory": proposal.subcategory,
                "confidence": proposal.confidence,
                "transaction_count": proposal.support_count or len(proposal.transaction_examples),
                "total_amount": proposal.total_amount,
                "transaction_examples": [
                    _serialize_example(example) for example in proposal.transaction_examples
                ],
            }
        )
    return serialized


def _serialize_suggestion(suggestion: ReviewSuggestion) -> dict[str, Any]:
    data = {
        "category": suggestion.category,
        "subcategory": suggestion.subcategory,
        "confidence": suggestion.confidence,
        "is_new_category": suggestion.is_new_category,
    }
    if suggestion.notes:
        data["notes"] = suggestion.notes
    return data


def _serialize_example(example: ReviewExample) -> dict[str, Any]:
    return {
        "id": example.fingerprint,
        "date": example.date,
        "merchant": example.merchant,
        "amount": example.amount,
        "original_description": example.original_description,
        "account_id": example.account_id,
    }
