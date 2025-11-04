"""Dataclasses describing extracted statement data."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class ExtractedTransaction:
    """Normalized representation of a transaction pulled from a statement."""

    date: date
    merchant: str
    amount: float
    original_description: str
    account_id_hint: str | None = None


@dataclass(slots=True)
class StatementMetadata:
    """Summary metadata derived from the statement itself."""

    institution: str
    account_name: str
    account_type: str
    start_date: date | None
    end_date: date | None


@dataclass(slots=True)
class ExtractionResult:
    """Container for metadata plus extracted transactions."""

    metadata: StatementMetadata
    transactions: list[ExtractedTransaction]

    def __iter__(self) -> Iterator[ExtractedTransaction]:
        return iter(self.transactions)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.transactions)


def merge_results(*results: ExtractionResult) -> ExtractionResult:
    """Merge multiple partial results (e.g., multi-account statements)."""
    if not results:
        raise ValueError("No results to merge")
    base = results[0]
    merged_transactions: list[ExtractedTransaction] = []
    for result in results:
        merged_transactions.extend(result.transactions)
    return ExtractionResult(metadata=base.metadata, transactions=merged_transactions)
