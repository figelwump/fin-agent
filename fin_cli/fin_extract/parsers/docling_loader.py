"""Adapter for Docling PDF parser."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from fin_cli.shared.exceptions import ExtractionError
from .pdf_loader import PdfDocument, PdfTable

try:
    from docling.document_converter import DocumentConverter, FormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.backend.docling_parse_v4_backend import DoclingParseV4DocumentBackend
    from docling.pipeline.standard_pdf_pipeline import StandardPdfPipeline
except ModuleNotFoundError:
    DocumentConverter = None  # type: ignore[assignment]
    FormatOption = None  # type: ignore[assignment]
    InputFormat = None  # type: ignore[assignment]
    PdfPipelineOptions = None  # type: ignore[assignment]
    DoclingParseV4DocumentBackend = None  # type: ignore[assignment]
    StandardPdfPipeline = None  # type: ignore[assignment]


DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}(/\d{2,4})?$")
AMOUNT_RE = re.compile(r"^[-\(\$]?\d[\d,]*\.?\d{0,2}\)?$")
UNICODE_ESC_RE = re.compile(r"/uni([0-9A-Fa-f]{4})")

_log = logging.getLogger(__name__)
_FAST_CONVERTER: DocumentConverter | None = None
_FULL_CONVERTER: DocumentConverter | None = None


def _headers_look_like_data(headers: tuple[str, ...]) -> bool:
    """Detect if headers look like data values rather than column names.

    Common patterns in transaction data:
    - Dates: MM/DD, MM/DD/YY, etc
    - Dollar amounts: $X.XX, -X.XX, numbers with decimals
    - Transaction descriptions (all caps, longer strings)
    """
    if not headers or len(headers) == 0:
        return False

    # Check first column - if it looks like a date, headers are probably data
    first = headers[0].strip()
    if DATE_RE.match(first):  # Matches 01/03, 12/05/24, etc
        return True

    # Check last column - if it looks like a dollar amount, headers are probably data
    last = headers[-1].strip()
    if AMOUNT_RE.match(last):  # Matches $1.23, -19.95, 1,234.56
        return True

    return False


def _looks_like_date(value: str) -> bool:
    return bool(DATE_RE.match(value.strip()))


def _looks_like_amount(value: str) -> bool:
    normalized = value.strip()
    if normalized.endswith("CR") or normalized.endswith("DR"):
        normalized = normalized[:-2].strip()
    return bool(AMOUNT_RE.match(normalized))


def _synthesize_ledger_headers(sample_row: tuple[str, ...]) -> tuple[str, ...] | None:
    """Infer transaction-style headers from a row that looks like data.

    Docling sometimes returns the first data row as the header tuple. We try to
    recover semantic column names so extractors that rely on words like
    "date", "description", or "amount" continue to work across issuers.
    """

    if not sample_row:
        return None

    synthesized: list[str] = []
    found_date = False
    found_description = False
    found_amount = False

    for idx, cell in enumerate(sample_row):
        value = (cell or "").strip()
        if not value:
            synthesized.append(f"Column {idx}")
            continue
        if not found_date and _looks_like_date(value):
            synthesized.append("Transaction Date")
            found_date = True
            continue
        if not found_amount and _looks_like_amount(value):
            synthesized.append("Amount")
            found_amount = True
            continue
        if not found_description and value:
            synthesized.append("Description")
            found_description = True
            continue
        synthesized.append(f"Detail {idx}")

    # Ensure minimum semantic coverage so downstream extractors see the words
    # they expect even if the heuristics above did not trigger.
    if not found_description and synthesized:
        description_index = 1 if len(synthesized) > 1 else 0
        synthesized[description_index] = "Description"
        found_description = True
    if not found_date and synthesized:
        synthesized[0] = "Transaction Date"
        found_date = True
    if not found_amount and synthesized:
        synthesized[-1] = "Amount"
        found_amount = True

    return tuple(synthesized)


def _clean_docling_text(value: str | None) -> str:
    """Decode docling's `/uniXXXX` sequences back into plain characters."""

    if value is None:
        return ""
    text = str(value)

    def _replace(match: re.Match[str]) -> str:
        codepoint = int(match.group(1), 16)
        return chr(codepoint)

    return UNICODE_ESC_RE.sub(_replace, text)


def _build_fast_docling_converter() -> DocumentConverter:
    """Return a tuned DocumentConverter that skips OCR/GPU warm-up for digital PDFs."""

    global _FAST_CONVERTER
    if _FAST_CONVERTER is not None:
        return _FAST_CONVERTER

    # Skip GPU probing and OCR to avoid the costly accelerate stack for digitally-native statements.
    pdf_options = PdfPipelineOptions(do_ocr=False)
    format_options = {
        InputFormat.PDF: FormatOption(
            pipeline_cls=StandardPdfPipeline,
            backend=DoclingParseV4DocumentBackend,
            pipeline_options=pdf_options,
        )
    }
    _FAST_CONVERTER = DocumentConverter(
        allowed_formats=[InputFormat.PDF],
        format_options=format_options,
    )
    return _FAST_CONVERTER


def _get_full_docling_converter() -> DocumentConverter:
    """Return the stock Docling converter for image-based fallbacks."""

    global _FULL_CONVERTER
    if _FULL_CONVERTER is None:
        _FULL_CONVERTER = DocumentConverter()
    return _FULL_CONVERTER


def load_pdf_with_docling(path: str | Path) -> PdfDocument:
    if DocumentConverter is None:
        raise ExtractionError(
            "Docling is not installed. Install fin-cli with the 'pdf_docling' extra to enable extraction."
        )

    pdf_path = Path(path)
    if not pdf_path.exists():
        raise ExtractionError(f"PDF file does not exist: {pdf_path}")
    
    try:
        fast_converter = _build_fast_docling_converter()
        result = fast_converter.convert(pdf_path)
        document = _build_pdf_document(result)

        if not document.text.strip() and not document.tables:
            # If we stripped all content (likely a scanned PDF), retry with full OCR stack.
            _log.info(
                "Docling fast-path produced empty output; retrying with full pipeline including OCR."
            )
            fallback_result = _get_full_docling_converter().convert(pdf_path)
            document = _build_pdf_document(fallback_result)

        return document
    except Exception as exc:
        raise ExtractionError(f"Failed to read PDF with Docling: {exc}") from exc


def _build_pdf_document(result) -> PdfDocument:
    """Convert a Docling ConversionResult into our PdfDocument structure."""

    text = result.document.export_to_markdown()
    tables: list[PdfTable] = []
    for table in result.document.tables:
        # Convert table to DataFrame (pass doc to preserve structure hints)
        df = table.export_to_dataframe(doc=result.document)

        if df.empty:
            continue

        headers = tuple(_clean_docling_text(str(col)) for col in df.columns)
        rows = [
            tuple(_clean_docling_text(cell) for cell in row)
            for row in df.values.tolist()
        ]

        if _headers_look_like_data(headers):
            rows = [headers] + rows
            inferred_headers = _synthesize_ledger_headers(headers)
            if inferred_headers is not None:
                headers = inferred_headers
            else:
                headers = tuple(str(i) for i in range(len(headers)))

        tables.append(PdfTable(headers=headers, rows=rows))

    return PdfDocument(text=text, tables=tables)
