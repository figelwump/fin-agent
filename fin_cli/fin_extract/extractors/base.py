"""Base classes and utilities for statement extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

from ..parsers.pdf_loader import PdfDocument
from ..types import ExtractionResult


class StatementExtractor(ABC):
    """Abstract base for bank-specific extractors."""

    name: str = "generic"

    @abstractmethod
    def supports(self, document: PdfDocument) -> bool:
        """Return True if this extractor can parse the given document."""

    @abstractmethod
    def extract(self, document: PdfDocument) -> ExtractionResult:
        """Perform extraction and return transactions + metadata."""


class ExtractorRegistry:
    """Registry to manage available extractors."""

    def __init__(self, extractors: Iterable[type[StatementExtractor]]) -> None:
        self._extractor_types = list(extractors)

    def detect(self, document: PdfDocument) -> StatementExtractor | None:
        for extractor_cls in self._extractor_types:
            extractor = extractor_cls()
            if extractor.supports(document):
                return extractor
        return None

    def register(self, extractor: type[StatementExtractor]) -> None:
        if extractor not in self._extractor_types:
            self._extractor_types.append(extractor)
