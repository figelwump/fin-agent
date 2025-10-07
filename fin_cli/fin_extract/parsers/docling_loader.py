"""Adapter for Docling PDF parser."""

from __future__ import annotations
import re
from pathlib import Path
from fin_cli.shared.exceptions import ExtractionError
from .pdf_loader import PdfDocument, PdfTable

try:
    from docling.document_converter import DocumentConverter
except ModuleNotFoundError:
    DocumentConverter = None  # type: ignore[assignment]


DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}(/\d{2,4})?$")
AMOUNT_RE = re.compile(r"^[-\(\$]?\d[\d,]*\.?\d{0,2}\)?$")
UNICODE_ESC_RE = re.compile(r"/uni([0-9A-Fa-f]{4})")


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

def load_pdf_with_docling(path: str | Path) -> PdfDocument:
    if DocumentConverter is None:
        raise ExtractionError(
            "Docling is not installed. Install fin-cli with the 'pdf_docling' extra to enable extraction."
        )

    pdf_path = Path(path)
    if not pdf_path.exists():
        raise ExtractionError(f"PDF file does not exist: {pdf_path}")
    
    try:
        # Step 1: Convert PDF using Docling
        converter = DocumentConverter()
        result = converter.convert(pdf_path)

        # Step 2: Extract text from the document
        # Using markdown export for now - preserves some structure
        text = result.document.export_to_markdown()

        # Step 3: Convert Docling tables to our PdfTable format
        tables: list[PdfTable] = []
        for table in result.document.tables:
            # Convert table to DataFrame (pass doc argument to get better structure)
            df = table.export_to_dataframe(doc=result.document)

            if df.empty:
                continue

            # Extract headers and rows from DataFrame
            headers = tuple(_clean_docling_text(str(col)) for col in df.columns)
            rows = [
                tuple(_clean_docling_text(cell) for cell in row)
                for row in df.values.tolist()
            ]

            # Fix misidentified headers: if headers look like data (dates, amounts),
            # treat them as the first row and generate generic column names
            if _headers_look_like_data(headers):
                # Add the misidentified headers as the first data row so we do not
                # lose any information and then synthesize semantic column names.
                rows = [headers] + rows
                inferred_headers = _synthesize_ledger_headers(headers)
                if inferred_headers is not None:
                    headers = inferred_headers
                else:
                    # Fall back to positional headers if we cannot infer names.
                    headers = tuple(str(i) for i in range(len(headers)))

            tables.append(PdfTable(headers=headers, rows=rows))

        return PdfDocument(text=text, tables=tables)
    except Exception as exc:
        raise ExtractionError(f"Failed to read PDF with Docling: {exc}") from exc
