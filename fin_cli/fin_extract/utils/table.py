"""Helpers for normalizing PDF table structures."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
from typing import Callable, Iterable, Sequence

try:  # Optional typing support without runtime dependency
    from ..parsers.pdf_loader import PdfTable
except ImportError:  # pragma: no cover - during type checking only
    PdfTable = None  # type: ignore


NormalizedPredicate = Callable[[tuple[str, ...]], bool]


@dataclass(slots=True)
class NormalizedTable:
    """Normalized representation of a PDF table."""

    headers: tuple[str, ...]
    rows: list[tuple[str, ...]]


def normalize_pdf_table(
    table: "PdfTable",
    *,
    header_scan: int = 6,
    header_predicate: NormalizedPredicate | None = None,
    merge_depth: int = 3,
) -> NormalizedTable:
    """Normalize a ``PdfTable`` produced by pdfplumber/camelot.

    Parameters
    ----------
    table:
        The source table with header tuple and body rows.
    header_scan:
        Number of leading rows to consider while searching for a header.
    header_predicate:
        Optional predicate determining whether a candidate row should be
        treated as the table header.
    merge_depth:
        Maximum number of successive rows to merge when forming header
        candidates (useful for multi-line headers).
    """

    raw_rows: list[Sequence[str | None]] = [table.headers, *table.rows]
    return normalize_table_rows(
        raw_rows,
        header_scan=header_scan,
        header_predicate=header_predicate,
        merge_depth=merge_depth,
    )


def normalize_table_rows(
    raw_rows: Iterable[Sequence[str | None]],
    *,
    header_scan: int = 6,
    header_predicate: NormalizedPredicate | None = None,
    merge_depth: int = 3,
) -> NormalizedTable:
    """Normalize a sequence of raw table rows.

    Returns a :class:`NormalizedTable` containing cleaned header cells and the
    remaining body rows with whitespace trimmed. Empty rows are discarded.
    """

    rows = [normalize_cells(row) for row in raw_rows]
    rows = [row for row in rows if any(row)]
    if not rows:
        return NormalizedTable(headers=(), rows=[])

    predicate = header_predicate or _default_header_predicate
    max_scan = min(header_scan, len(rows))

    for idx in range(max_scan):
        candidate = rows[idx]
        variants = [(candidate, 1)]
        for depth in range(2, merge_depth + 1):
            if idx + depth - 1 >= len(rows):
                break
            merged = merge_rows(rows[idx : idx + depth])
            variants.append((merged, depth))
        for header, span in variants:
            if predicate(header):
                data_rows = rows[idx + span :]
                return NormalizedTable(headers=header, rows=list(data_rows))

    # Fallback: treat first row as header.
    return NormalizedTable(headers=rows[0], rows=rows[1:])


def merge_rows(rows: Sequence[Sequence[str]]) -> tuple[str, ...]:
    """Merge multiple rows column-wise, joining non-empty cells by space."""

    merged: list[str] = []
    for column_cells in zip_longest(*rows, fillvalue=""):
        merged_value = " ".join(part for part in column_cells if part).strip()
        merged.append(merged_value)
    return tuple(merged)


def normalize_cells(row: Sequence[str | None]) -> tuple[str, ...]:
    """Trim whitespace and convert ``None`` values to empty strings."""

    return tuple((cell or "").strip() for cell in row)


def _default_header_predicate(header: tuple[str, ...]) -> bool:
    non_empty = sum(1 for cell in header if cell)
    return non_empty >= 2

