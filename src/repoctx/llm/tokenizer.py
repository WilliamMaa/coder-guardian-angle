"""Token counting utilities using tiktoken."""

from __future__ import annotations

import tiktoken

from repoctx.llm.errors import LLMTokenLimitError


class TokenCounter:
    """Count and truncate tokens for LLM prompts."""

    # Use cl100k_base as a close approximation for DeepSeek / Tencent models
    _ENCODING_NAME = "cl100k_base"

    def __init__(self) -> None:
        self._encoder = tiktoken.get_encoding(self._ENCODING_NAME)

    def count(self, text: str) -> int:
        """Return the number of tokens in *text*."""
        return len(self._encoder.encode(text))

    def truncate(self, text: str, max_tokens: int, suffix: str = "\n...[truncated]") -> str:
        """Truncate *text* to at most *max_tokens* tokens.

        Args:
            text: Input text.
            max_tokens: Maximum number of tokens allowed.
            suffix: String appended when truncation occurs.

        Returns:
            Truncated text (with suffix if truncation happened).
        """
        tokens = self._encoder.encode(text)
        if len(tokens) <= max_tokens:
            return text
        # Reserve space for suffix
        suffix_tokens = self._encoder.encode(suffix)
        truncated = tokens[: max_tokens - len(suffix_tokens)]
        return self._encoder.decode(truncated) + suffix

    def check_limit(self, text: str, max_tokens: int) -> None:
        """Raise LLMTokenLimitError if text exceeds max_tokens.

        Args:
            text: Input text to check.
            max_tokens: Maximum allowed tokens.

        Raises:
            LLMTokenLimitError: If the token count exceeds the limit.
        """
        count = self.count(text)
        if count > max_tokens:
            raise LLMTokenLimitError(
                f"Prompt exceeds token limit: {count} tokens > {max_tokens} max"
            )
