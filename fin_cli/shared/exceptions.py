"""Project-wide custom exceptions."""

from __future__ import annotations


class FinAgentError(Exception):
    """Base exception for the financial CLI suite."""


class ConfigurationError(FinAgentError):
    """Raised when configuration loading or validation fails."""


class ExtractionError(FinAgentError):
    """Raised when PDF extraction fails."""


class CategorizationError(FinAgentError):
    """Raised when transaction categorization fails."""


class DatabaseError(FinAgentError):
    """Raised for database-related issues."""


class QueryError(DatabaseError):
    """Raised when query orchestration or execution fails."""
