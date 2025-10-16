"""Skeleton StatementExtractor implementation for custom plugins."""

from __future__ import annotations

from fin_cli.fin_extract.extractors.base import StatementExtractor
from fin_cli.fin_extract.parsers.pdf_loader import PdfDocument
from fin_cli.fin_extract.types import ExtractionResult, StatementMetadata


class ExampleExtractor(StatementExtractor):
    name = "example_python"

    def supports(self, document: PdfDocument) -> bool:
        return "example" in document.text.lower()

    def extract(self, document: PdfDocument) -> ExtractionResult:
        metadata = StatementMetadata(
            institution="Example Bank",
            account_name="Example Account",
            account_type="checking",
            start_date=None,
            end_date=None,
        )
        return ExtractionResult(metadata=metadata, transactions=[])
