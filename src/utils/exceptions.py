"""Custom exceptions for Text-to-SQL Agent."""


class Text2SQLError(Exception):
    """Base exception for all Text-to-SQL errors."""
    pass


class ConfigurationError(Text2SQLError):
    """Raised when configuration is invalid or missing."""
    pass


class SchemaError(Text2SQLError):
    """Raised when there's an error with schema parsing or loading."""
    pass


class SessionError(Text2SQLError):
    """Raised when there's an error with session management."""
    pass


class LLMError(Text2SQLError):
    """Base exception for LLM-related errors."""
    pass


class RecoverableError(LLMError):
    """Raised when an error is recoverable through retry."""
    pass


class FatalError(LLMError):
    """Raised when an error is not recoverable (e.g., authentication failure)."""
    pass


class RetryExhaustedError(LLMError):
    """Raised when all retry attempts have been exhausted."""
    pass


class BigQueryError(Text2SQLError):
    """Raised when there's an error with BigQuery operations."""
    pass


class JoinInferenceError(Text2SQLError):
    """Raised when join inference fails or is ambiguous."""
    pass


class AmbiguityError(Text2SQLError):
    """Raised when the agent detects ambiguity that requires human clarification."""

    def __init__(self, message: str, options: list = None, context: dict = None):
        """Initialize ambiguity error with options for user choice.

        Args:
            message: Description of the ambiguity
            options: List of possible options to resolve ambiguity
            context: Additional context about the ambiguity
        """
        super().__init__(message)
        self.options = options or []
        self.context = context or {}


class MaxIterationsError(Text2SQLError):
    """Raised when agent reaches maximum iteration limit."""
    pass


class CorrectionError(Text2SQLError):
    """Raised when there's an error processing user corrections."""
    pass


class ValidationError(Text2SQLError):
    """Raised when validation fails (SQL syntax, schema, etc.)."""
    pass
