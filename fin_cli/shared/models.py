"""Data model helper stubs.

Actual CRUD utilities will be implemented in Phase 2 once the schema is live.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Transaction:
    """Minimal transaction representation for later use."""

    date: date
    merchant: str
    amount: float
    account_id: int | None = None
    category_id: int | None = None
    original_description: str | None = None
