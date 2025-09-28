"""Helpers for reading PDFs with pdfplumber and Camelot fallback."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from fin_cli.shared.exceptions import ExtractionError

try:  # pragma: no cover - import guarded for optional dependency
    import pdfplumber
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    pdfplumber = None  # type: ignore[assignment]

try:  # pragma: no cover - import guarded for optional dependency
    import camelot  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - handled at runtime
    camelot = None  # type: ignore[assignment]


@dataclass(slots=True)
class PdfTable:
    headers: tuple[str, ...]
    rows: list[tuple[str, ...]]


@dataclass(slots=True)
class PdfDocument:
    text: str
    tables: list[PdfTable]


def load_pdf_document(path: str | Path, *, enable_camelot_fallback: bool = False) -> PdfDocument:
    if pdfplumber is None:
        raise ExtractionError(
            "pdfplumber is not installed. Install fin-cli with the 'pdf' extra to enable extraction."
        )

    pdf_path = Path(path)
    if not pdf_path.exists():
        raise ExtractionError(f"PDF file does not exist: {pdf_path}")

    text_chunks: list[str] = []
    tables: list[PdfTable] = []
    try:
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
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ExtractionError(f"Failed to read PDF with pdfplumber: {exc}") from exc

    if enable_camelot_fallback:
        try:
            fallback_tables = _load_tables_with_camelot(pdf_path)
        except ExtractionError:
            fallback_tables = [] if tables else None
            if fallback_tables is None:
                raise
        else:
            tables = _merge_tables(tables, fallback_tables)

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


def _merge_tables(primary: list[PdfTable], secondary: list[PdfTable]) -> list[PdfTable]:
    """Return a new list containing tables from both sequences without duplicates."""

    seen: set[tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]] = set()
    merged: list[PdfTable] = []

    def _add(table: PdfTable) -> None:
        key = (table.headers, tuple(table.rows))
        if key in seen:
            return
        seen.add(key)
        merged.append(table)

    for table in primary:
        _add(table)
    for table in secondary:
        _add(table)
    return merged


def _load_tables_with_camelot(pdf_path: Path) -> list[PdfTable]:
    """Load tables using Camelot when pdfplumber fails to identify them.

    Camelot can parse lattice/stream-based tables more robustly at the cost of
    performance and heavier system dependencies (Ghostscript). We keep the
    logic centralized here so extractors do not need to know about the
    underlying library choices.
    """

    if camelot is None:
        raise ExtractionError(
            "Camelot fallback requested but camelot-py is not installed. Install the 'pdf' extra."
        )

    tables: list[PdfTable] = []
    last_error: Exception | None = None
    import warnings

    for flavor in ("lattice", "stream"):
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="No tables found in table area",
                    category=UserWarning,
                    module="camelot",
                )
                camelot_tables = camelot.read_pdf(
                    str(pdf_path),
                    pages="all",
                    flavor=flavor,
                    strip_text="\n",
                )
        except Exception as exc:  # pragma: no cover - library-specific failure paths
            last_error = exc
            continue

        for table in camelot_tables:
            df = table.df
            raw_rows = df.values.tolist()
            cleaned_rows: list[tuple[str, ...]] = [
                tuple((str(cell) if cell is not None else "").strip() for cell in row)
                for row in raw_rows
            ]
            if not cleaned_rows:
                continue
            headers = cleaned_rows[0]
            body = [row for row in cleaned_rows[1:] if any(cell for cell in row)]
            if not any(headers) and body:
                headers = body.pop(0)
            tables.append(PdfTable(headers=headers, rows=body))

    if not tables:
        if last_error:
            raise ExtractionError(f"Camelot could not parse tables: {last_error}") from last_error
        raise ExtractionError("Camelot fallback did not detect any tables in the PDF.")

    return tables
