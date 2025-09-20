"""Review queue helpers for fin-enhance."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import sqlite3

from fin_cli.shared import models

from .pipeline import ReviewCandidate


@dataclass(slots=True)
class ReviewPayload:
    items: list[ReviewCandidate]

    def to_dict(self) -> dict:
        return {
            "version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "review_needed": [
                {
                    "type": "transaction_review",
                    "id": item.fingerprint,
                    "date": item.date,
                    "merchant": item.merchant,
                    "amount": item.amount,
                    "original_description": item.original_description,
                    "account_id": item.account_id,
                }
                for item in self.items
            ],
        }


def write_review_file(path: Path, items: Iterable[ReviewCandidate]) -> None:
    payload = ReviewPayload(list(items))
    data = payload.to_dict()
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
        if learn:
            merchant = str(txn_row["merchant"])
            models.record_merchant_pattern(
                connection,
                pattern=merchant,
                category_id=category_id,
                confidence=confidence,
            )
        applied += 1
    return applied, skipped
