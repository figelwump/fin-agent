"""Rules-based categorization utilities."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from fin_cli.shared import models

from .llm_client import merchant_pattern_key


@dataclass(slots=True)
class CategorizationOutcome:
    category_id: int | None
    confidence: float
    method: str | None
    needs_review: bool


class RuleCategorizer:
    """Simple categorizer that relies on learned merchant patterns and history."""

    def __init__(self, connection: sqlite3.Connection, *, track_usage: bool = True) -> None:
        self.connection = connection
        self.track_usage = track_usage

    def categorize(self, merchant: str) -> CategorizationOutcome:
        outcome = self._from_patterns(merchant)
        if outcome:
            return outcome
        outcome = self._from_history(merchant)
        if outcome:
            return outcome
        return CategorizationOutcome(
            category_id=None,
            confidence=0.0,
            method=None,
            needs_review=True,
        )

    def _from_patterns(self, merchant: str) -> CategorizationOutcome | None:
        pattern_key = merchant_pattern_key(merchant)
        if not pattern_key:
            return None
        rows = models.fetch_merchant_patterns(self.connection, pattern_key)
        if not rows:
            return None
        best = rows[0]
        category_id = int(best["category_id"]) if best["category_id"] is not None else None
        if category_id is None:
            return None
        confidence = float(best["confidence"] or 0.8)
        # update usage count for analytics
        if self.track_usage:
            self.connection.execute(
                "UPDATE merchant_patterns SET usage_count = usage_count + 1 WHERE pattern = ?",
                (best["pattern"],),
            )
        return CategorizationOutcome(
            category_id=category_id,
            confidence=confidence,
            method="rule:pattern",
            needs_review=False,
        )

    def _from_history(self, merchant: str) -> CategorizationOutcome | None:
        row = self.connection.execute(
            """
            SELECT category_id, COUNT(*) as count
            FROM transactions
            WHERE merchant = ? AND category_id IS NOT NULL
            GROUP BY category_id
            ORDER BY count DESC
            LIMIT 1
            """,
            (merchant,),
        ).fetchone()
        if not row or row["category_id"] is None:
            return None
        return CategorizationOutcome(
            category_id=int(row["category_id"]),
            confidence=0.7,
            method="rule:history",
            needs_review=False,
        )
