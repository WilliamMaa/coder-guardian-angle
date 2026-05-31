"""HTTP client for Tencent MaaS LLM API."""

from __future__ import annotations

import json
import time

import httpx

from repoctx.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
)
from repoctx.models import ModelProviderConfig


class LLMClient:
    """Synchronous client for the Tencent MaaS chat completions API."""

    def __init__(
        self,
        config: ModelProviderConfig,
        api_key: str | None = None,
    ) -> None:
        self.config = config
        self.api_key = api_key or config.api_key
        self.base_url = config.base_url.rstrip("/")
        self.timeout = config.timeout

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        stream: bool = False,
    ) -> str:
        """Send a chat completion request and return the text content.

        Args:
            messages: OpenAI-compatible message list.
            model: Model identifier. Defaults to config.model.
            stream: Whether to stream. MVP only supports sync (False).

        Returns:
            The assistant's message content.

        Raises:
            LLMAuthError: On HTTP 401.
            LLMRateLimitError: On HTTP 429.
            LLMServerError: On HTTP 5xx.
            LLMTimeoutError: On request timeout.
            LLMNetworkError: On network failure.
            LLMError: On other failures.
        """
        if not self.api_key:
            raise LLMAuthError("API key is not configured. Set it in .repoctx.yaml or repoctx config.ini.")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or self.config.model,
            "messages": messages,
            "stream": stream,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as e:
            raise LLMTimeoutError(
                f"Request timed out after {self.timeout} seconds"
            ) from e
        except httpx.NetworkError as e:
            raise LLMNetworkError(
                "Network error: unable to reach the API endpoint. "
                "Please check your internet connection."
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(f"HTTP request failed: {e}") from e

        if response.status_code == 401:
            raise LLMAuthError("Invalid or expired API key (HTTP 401)")
        if response.status_code == 429:
            raise LLMRateLimitError("Rate limit exceeded (HTTP 429). Please retry later.")
        if response.status_code >= 500:
            raise LLMServerError(f"Server error (HTTP {response.status_code}). Please retry later.")
        if not response.is_success:
            raise LLMError(f"Unexpected HTTP {response.status_code}: {response.text}")

        try:
            data = response.json()
            content: str = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            raise LLMError(f"Failed to parse API response: {e}") from e

        return content

    def chat_completion_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> str:
        """Call chat_completion with exponential backoff retry.

        Retries on LLMRateLimitError and LLMServerError.
        """
        for attempt in range(max_retries):
            try:
                return self.chat_completion(messages, model=model)
            except (LLMRateLimitError, LLMServerError) as e:
                if attempt == max_retries - 1:
                    raise e
                delay = base_delay * (2 ** attempt)
                time.sleep(delay)
        # Should never reach here because the loop either returns or raises.
        return ""
