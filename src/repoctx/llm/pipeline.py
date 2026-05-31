"""Prompt assembly and response parsing pipeline."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, TypeAdapter

from repoctx.llm.client import LLMClient
from repoctx.llm.errors import LLMParseError
from repoctx.llm.tokenizer import TokenCounter

T = TypeVar("T")


class PromptPipeline:
    """Generic pipeline: template -> fill -> token-check -> API call -> JSON parse -> validate."""

    def __init__(
        self,
        client: LLMClient,
        token_counter: TokenCounter | None = None,
        max_prompt_tokens: int = 6000,
    ) -> None:
        self.client = client
        self.token_counter = token_counter or TokenCounter()
        self.max_prompt_tokens = max_prompt_tokens

    def _load_template(self, template_path: Path) -> string.Template:
        """Load a prompt template from file."""
        text = template_path.read_text(encoding="utf-8")
        return string.Template(text)

    def _assemble_prompt(self, template_path: Path, variables: dict[str, str]) -> str:
        """Fill template variables and check token limit."""
        tmpl = self._load_template(template_path)
        prompt = tmpl.safe_substitute(variables)
        self.token_counter.check_limit(prompt, self.max_prompt_tokens)
        return prompt

    def _call_model(self, prompt: str, system_prompt: str | None = None) -> str:
        """Send prompt to LLM and return raw text response."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.client.chat_completion_with_retry(messages)

    @staticmethod
    def _repair_json(text: str) -> str:
        """Fix common JSON formatting errors produced by LLMs.

        Repairs trailing commas before ``}`` or ``]``.
        """
        # Remove trailing commas inside objects and arrays
        text = re.sub(r",(\s*[}\]])", r"\1", text)
        return text

    def _extract_json(self, text: str) -> dict | list:
        """Extract JSON object or array from model response text.

        Handles markdown code blocks and plain JSON.  Automatically repairs
        common LLM JSON mistakes (e.g. trailing commas) before giving up.
        """
        original = text

        # Try markdown code block first
        code_block = re.search(r"```(?:json)?\s*(\[.*?\]|\{.*?\})\s*```", text, re.DOTALL)
        if code_block:
            text = code_block.group(1)
        else:
            # Try to find the first top-level JSON object or array
            match = re.search(r"(\[.*\]|\{.*\})", text, re.DOTALL)
            if match:
                text = match.group(1)

        # Attempt 1: raw text
        try:
            result = json.loads(text)
            if isinstance(result, (dict, list)):
                return result
        except json.JSONDecodeError:
            pass

        # Attempt 2: repair common LLM JSON mistakes
        repaired = self._repair_json(text)
        try:
            result = json.loads(repaired)
            if isinstance(result, (dict, list)):
                return result
        except json.JSONDecodeError:
            pass

        # Give up — include the first 800 chars of the raw response for debugging
        snippet = original[:800].replace("\n", " ")
        raise LLMParseError(
            f"Failed to parse JSON from model response. "
            f"Response snippet (first 800 chars): {snippet!r}"
        )

    def run(
        self,
        template_path: Path,
        variables: dict[str, str],
        output_model: type[T],
        system_prompt: str | None = None,
    ) -> T:
        """Execute the full pipeline.

        Args:
            template_path: Path to the prompt template file.
            variables: Mapping of template variable names to values.
            output_model: Pydantic model class for validating the JSON output.
            system_prompt: Optional system message.

        Returns:
            Validated instance of *output_model*.

        Raises:
            LLMTokenLimitError: If the assembled prompt exceeds the token limit.
            LLMParseError: If the response cannot be parsed as JSON.
            LLMError: If the API call fails.
        """
        prompt = self._assemble_prompt(template_path, variables)
        return self.run_inline(prompt, output_model, system_prompt=system_prompt)

    def run_inline(
        self,
        prompt: str,
        output_model: type[T],
        system_prompt: str | None = None,
    ) -> T:
        """Execute the pipeline with an inline prompt string.

        Args:
            prompt: Fully assembled prompt text.
            output_model: Pydantic model class for validating the JSON output.
            system_prompt: Optional system message.

        Returns:
            Validated instance of *output_model*.

        Raises:
            LLMTokenLimitError: If the prompt exceeds the token limit.
            LLMParseError: If the response cannot be parsed as JSON.
            LLMError: If the API call fails.
        """
        self.token_counter.check_limit(prompt, self.max_prompt_tokens)
        raw_response = self._call_model(prompt, system_prompt=system_prompt)
        parsed = self._extract_json(raw_response)

        try:
            if hasattr(output_model, "model_validate"):
                return output_model.model_validate(parsed)  # type: ignore[return-value]
            return TypeAdapter(output_model).validate_python(parsed)
        except Exception as e:
            raise LLMParseError(f"Model output failed validation: {e}") from e
