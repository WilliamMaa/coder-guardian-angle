"""Custom exceptions for LLM API calls."""

from __future__ import annotations


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMAuthError(LLMError):
    """Raised when API key is invalid or expired (HTTP 401)."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when rate limit is exceeded (HTTP 429)."""

    pass


class LLMServerError(LLMError):
    """Raised when the LLM server returns 5xx."""

    pass


class LLMTimeoutError(LLMError):
    """Raised when the request times out."""

    pass


class LLMNetworkError(LLMError):
    """Raised when there is no network connectivity."""

    pass


class LLMParseError(LLMError):
    """Raised when the model response cannot be parsed as expected JSON."""

    pass


class LLMTokenLimitError(LLMError):
    """Raised when the prompt exceeds the safe token threshold."""

    pass
