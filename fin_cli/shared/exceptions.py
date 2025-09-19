"""Project-wide custom exceptions (initial scaffolding)."""

from __future__ import annotations


class FinAgentError(Exception):
    """Base exception for the financial CLI suite."""


class ExtractionError(FinAgentError):
    """Raised when PDF extraction fails."""


class CategorizationError(FinAgentError):
    """Raised when transaction categorization fails."""


class DatabaseError(FinAgentError):
    """Raised for database-related issues."""
