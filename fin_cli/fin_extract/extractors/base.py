"""Base classes and utilities for statement extractors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
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


@dataclass(frozen=True)
class RegistrationResult:
    """Details about an extractor registration attempt."""

    name: str
    became_primary: bool
    replaced_existing: bool


class ExtractorRegistry:
    """Registry to manage available extractors with precedence handling."""

    def __init__(self, extractors: Iterable[type[StatementExtractor]]) -> None:
        self._entries_by_name: dict[str, list[type[StatementExtractor]]] = {}
        self._order: list[str] = []
        for extractor in extractors:
            self.register(extractor)

    def detect(
        self,
        document: PdfDocument,
        allowed_names: Sequence[str] | None = None,
    ) -> StatementExtractor | None:
        allowed = {name.lower() for name in allowed_names} if allowed_names is not None else None
        for extractor_cls in self.iter_types(include_alternates=True):
            if allowed is not None and extractor_cls.name.lower() not in allowed:
                continue
            extractor = extractor_cls()
            if extractor.supports(document):
                return extractor
        return None

    def register(
        self,
        extractor: type[StatementExtractor],
        *,
        allow_override: bool = False,
    ) -> RegistrationResult:
        if not hasattr(extractor, "__origin__"):
            setattr(extractor, "__origin__", f"python::{extractor.__module__}")
        if not hasattr(extractor, "__plugin_kind__"):
            setattr(extractor, "__plugin_kind__", "builtin_python")
        name = extractor.name
        key = name.lower()
        bucket = self._entries_by_name.setdefault(key, [])

        if not bucket:
            bucket.append(extractor)
            self._order.append(key)
            return RegistrationResult(name=name, became_primary=True, replaced_existing=False)

        if allow_override:
            bucket.insert(0, extractor)
            return RegistrationResult(name=name, became_primary=True, replaced_existing=True)

        bucket.append(extractor)
        return RegistrationResult(name=name, became_primary=False, replaced_existing=False)

    def names(self) -> tuple[str, ...]:
        names: list[str] = []
        for key in self._order:
            bucket = self._entries_by_name.get(key)
            if not bucket:
                continue
            names.append(bucket[0].name)
        return tuple(names)

    def iter_types(
        self,
        *,
        include_alternates: bool = False,
    ) -> Iterable[type[StatementExtractor]]:
        for key in self._order:
            bucket = self._entries_by_name.get(key, [])
            if not bucket:
                continue
            if include_alternates:
                for extractor in bucket:
                    yield extractor
            else:
                yield bucket[0]

    def alternates_for(self, name: str) -> tuple[type[StatementExtractor], ...]:
        """Return alternate extractors registered for the given name (excluding primary)."""

        key = name.lower()
        bucket = self._entries_by_name.get(key, [])
        if len(bucket) <= 1:
            return ()
        return tuple(bucket[1:])
