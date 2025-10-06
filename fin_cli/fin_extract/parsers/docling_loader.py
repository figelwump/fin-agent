"""Adapter for Docling PDF parser."""

from __future__ import annotations
from pathlib import Path
from fin_cli.shared.exceptions import ExtractionError
from .pdf_loader import PdfDocument, PdfTable

try:
    from docling.document_converter import DocumentConverter
except ModuleNotFoundError:
    DocumentConverter = None  # type: ignore[assignment]

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
            # Convert table to DataFrame
            df = table.export_to_dataframe()

            if df.empty:
                continue

            # Extract headers and rows from DataFrame
            headers = tuple(str(col) for col in df.columns)
            rows = [
                tuple(str(cell) if cell is not None else "" for cell in row)
                for row in df.values.tolist()
            ]

            tables.append(PdfTable(headers=headers, rows=rows))

        return PdfDocument(text=text, tables=tables)
    except Exception as exc:
        raise ExtractionError(f"Failed to read PDF with Docling: {exc}") from exc