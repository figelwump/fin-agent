"""Data structures shared across fin-query modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Structured result set returned by the executor layer."""

    columns: tuple[str, ...]
    rows: Sequence[tuple[Any, ...]]
    limit_applied: bool = False
    limit_value: int | None = None
    description: str | None = None
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class SavedQuerySummary:
    """Metadata about a saved query sourced from the manifest."""

    name: str
    description: str
    path: str
    parameters: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SchemaTable:
    """Schema representation for a single SQLite table."""

    name: str
    columns: Sequence[tuple[str, str, bool]]
    indexes: Sequence[str]
    foreign_keys: Sequence[tuple[str, str, str]]
    estimated_row_count: int | None = None


@dataclass(frozen=True, slots=True)
class SchemaOverview:
    """Aggregated schema details returned by the schema inspector."""

    tables: Sequence[SchemaTable]
    database_path: Path
