"""Base classes and utilities for statement extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Sequence

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

    def detect(
        self,
        document: PdfDocument,
        allowed_names: Sequence[str] | None = None,
    ) -> StatementExtractor | None:
        allowed = {name.lower() for name in allowed_names} if allowed_names is not None else None
        for extractor_cls in self._extractor_types:
            if allowed is not None and extractor_cls.name.lower() not in allowed:
                continue
            extractor = extractor_cls()
            if extractor.supports(document):
                return extractor
        return None

    def register(self, extractor: type[StatementExtractor]) -> None:
        if extractor not in self._extractor_types:
            self._extractor_types.append(extractor)

    def names(self) -> tuple[str, ...]:
        return tuple(extractor.name for extractor in self._extractor_types)
