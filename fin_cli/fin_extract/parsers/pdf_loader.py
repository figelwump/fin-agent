"""Helpers for reading PDFs with pdfplumber."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

try:  # pragma: no cover - import guarded for optional dependency
    import pdfplumber
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    pdfplumber = None  # type: ignore[assignment]


@dataclass(slots=True)
class PdfTable:
    headers: tuple[str, ...]
    rows: list[tuple[str, ...]]


@dataclass(slots=True)
class PdfDocument:
    text: str
    tables: list[PdfTable]


def load_pdf_document(path: str | Path) -> PdfDocument:
    if pdfplumber is None:
        raise RuntimeError(
            "pdfplumber is not installed. Install fin-cli with the 'pdf' extra to enable extraction."
        )
    pdf_path = Path(path)
    text_chunks: list[str] = []
    tables: list[PdfTable] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_chunks.append(page_text)
            extracted_tables = page.extract_tables() or []
            for raw_table in extracted_tables:
                if not raw_table:
                    continue
                headers, rows = _normalize_table(raw_table)
                if headers:
                    tables.append(PdfTable(headers=headers, rows=rows))
    return PdfDocument(text="\n".join(text_chunks), tables=tables)


def _normalize_table(raw_table: Sequence[Sequence[str | None]]) -> tuple[tuple[str, ...], list[tuple[str, ...]]]:
    rows: list[tuple[str, ...]] = []
    headers: tuple[str, ...] = ()
    iterator = iter(raw_table)
    for row in iterator:
        cleaned = _clean_row(row)
        if not headers:
            headers = cleaned
            continue
        if _is_header_row(cleaned, headers):
            headers = cleaned
            continue
        rows.append(cleaned)
    return headers, rows


def _clean_row(row: Sequence[str | None]) -> tuple[str, ...]:
    return tuple((cell or "").strip() for cell in row)


def _is_header_row(candidate: Sequence[str], current_headers: Sequence[str]) -> bool:
    return candidate == current_headers
