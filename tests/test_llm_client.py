"""Unit tests for LLM client, tokenizer, pipeline, and logger (all mocked)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from pydantic import BaseModel

from repoctx.llm.client import LLMClient
from repoctx.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMRateLimitError,
    LLMServerError,
    LLMTimeoutError,
)
from repoctx.llm.logger import LLMCallLogger
from repoctx.llm.pipeline import PromptPipeline
from repoctx.llm.tokenizer import TokenCounter
from repoctx.models import ModelProviderConfig

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def model_config() -> ModelProviderConfig:
    return ModelProviderConfig(
        api_key="test-key",
        base_url="https://tokenhub.tencentmaas.com/v1",
        model="deepseek-v4-flash-202605",
        timeout=60,
    )


@pytest.fixture
def llm_client(model_config: ModelProviderConfig) -> LLMClient:
    return LLMClient(model_config)


@pytest.fixture
def mock_success_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.is_success = True
    resp.json.return_value = {
        "choices": [{"message": {"content": '{"result": "ok"}'}}]
    }
    return resp


def _mock_httpx_post(response: MagicMock) -> MagicMock:
    """Return a context manager mock that yields *response* from post()."""
    mock_client = MagicMock()
    mock_client.post.return_value = response
    return mock_client


# ---------------------------------------------------------------------------
# LLMClient
# ---------------------------------------------------------------------------


class TestLLMClient:
    """Tests for the Tencent MaaS LLM client."""

    def test_successful_completion(
        self, llm_client: LLMClient, mock_success_response: MagicMock
    ) -> None:
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(mock_success_response)
            mock_client.return_value.__enter__.return_value = mock_cm

            result = llm_client.chat_completion(
                [{"role": "user", "content": "Hello"}]
            )
            assert result == '{"result": "ok"}'
            mock_cm.post.assert_called_once()
            _, kwargs = mock_cm.post.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_unconfigured_api_key(self, model_config: ModelProviderConfig) -> None:
        model_config.api_key = None
        client = LLMClient(model_config)
        with pytest.raises(LLMAuthError, match="API key is not configured"):
            client.chat_completion([{"role": "user", "content": "x"}])

    def test_auth_error_401(self, llm_client: LLMClient) -> None:
        resp = MagicMock()
        resp.status_code = 401
        resp.is_success = False
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(resp)
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMAuthError, match="Invalid or expired API key"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_rate_limit_429(self, llm_client: LLMClient) -> None:
        resp = MagicMock()
        resp.status_code = 429
        resp.is_success = False
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(resp)
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMRateLimitError, match="Rate limit exceeded"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_server_error_503(self, llm_client: LLMClient) -> None:
        resp = MagicMock()
        resp.status_code = 503
        resp.is_success = False
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(resp)
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMServerError, match="Server error"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_timeout(self, llm_client: LLMClient) -> None:
        with patch("httpx.Client") as mock_client:
            mock_cm = MagicMock()
            mock_cm.post.side_effect = httpx.TimeoutException("timed out")
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMTimeoutError, match="timed out"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_network_error(self, llm_client: LLMClient) -> None:
        with patch("httpx.Client") as mock_client:
            mock_cm = MagicMock()
            mock_cm.post.side_effect = httpx.NetworkError("no route")
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMNetworkError, match="Network error"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_unexpected_http_error(self, llm_client: LLMClient) -> None:
        resp = MagicMock()
        resp.status_code = 418
        resp.is_success = False
        resp.text = "I'm a teapot"
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(resp)
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMError, match="Unexpected HTTP 418"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_malformed_json_response(self, llm_client: LLMClient) -> None:
        resp = MagicMock()
        resp.status_code = 200
        resp.is_success = True
        resp.json.return_value = {"invalid": "structure"}
        with patch("httpx.Client") as mock_client:
            mock_cm = _mock_httpx_post(resp)
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMError, match="Failed to parse API response"):
                llm_client.chat_completion([{"role": "user", "content": "x"}])

    def test_retry_success_on_second_attempt(
        self, llm_client: LLMClient, mock_success_response: MagicMock
    ) -> None:
        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 429
        rate_limit_resp.is_success = False

        with patch("httpx.Client") as mock_client, patch("time.sleep"):
            mock_cm = MagicMock()
            mock_cm.post.side_effect = [rate_limit_resp, mock_success_response]
            mock_client.return_value.__enter__.return_value = mock_cm

            result = llm_client.chat_completion_with_retry(
                [{"role": "user", "content": "Hello"}], max_retries=3
            )
            assert result == '{"result": "ok"}'
            assert mock_cm.post.call_count == 2

    def test_retry_exhausted(self, llm_client: LLMClient) -> None:
        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 429
        rate_limit_resp.is_success = False

        with patch("httpx.Client") as mock_client, patch("time.sleep"):
            mock_cm = MagicMock()
            mock_cm.post.return_value = rate_limit_resp
            mock_client.return_value.__enter__.return_value = mock_cm

            with pytest.raises(LLMRateLimitError):
                llm_client.chat_completion_with_retry(
                    [{"role": "user", "content": "Hello"}], max_retries=2
                )
            assert mock_cm.post.call_count == 2


# ---------------------------------------------------------------------------
# TokenCounter
# ---------------------------------------------------------------------------


class TestTokenCounter:
    """Tests for token counting and truncation."""

    def test_count_tokens(self) -> None:
        counter = TokenCounter()
        assert counter.count("hello world") > 0

    def test_count_empty_string(self) -> None:
        counter = TokenCounter()
        assert counter.count("") == 0

    def test_truncate_noop_when_under_limit(self) -> None:
        counter = TokenCounter()
        text = "hello"
        result = counter.truncate(text, max_tokens=1000)
        assert result == text

    def test_truncate_when_over_limit(self) -> None:
        counter = TokenCounter()
        text = "hello world " * 1000
        result = counter.truncate(text, max_tokens=10)
        assert counter.count(result) <= 10
        assert "[truncated]" in result

    def test_check_limit_raises(self) -> None:
        counter = TokenCounter()
        text = "hello world " * 1000
        with pytest.raises(Exception, match="exceeds token limit"):
            counter.check_limit(text, max_tokens=5)

    def test_check_limit_passes(self) -> None:
        counter = TokenCounter()
        counter.check_limit("hello", max_tokens=1000)


# ---------------------------------------------------------------------------
# PromptPipeline
# ---------------------------------------------------------------------------


class TestPromptPipeline:
    """Tests for the prompt assembly and parsing pipeline."""

    def test_pipeline_success(self, tmp_path: Path, model_config: ModelProviderConfig) -> None:
        template = tmp_path / "test.txt"
        template.write_text("Task: $task\nOutput JSON with field 'answer'.")

        class OutputModel(BaseModel):
            answer: str

        client = LLMClient(model_config)
        pipeline = PromptPipeline(client)

        with patch.object(client, "chat_completion_with_retry", return_value='{"answer": "42"}'):
            result = pipeline.run(
                template_path=template,
                variables={"task": "what is 6x7"},
                output_model=OutputModel,
            )
            assert result.answer == "42"

    def test_pipeline_extracts_json_from_markdown(self, tmp_path: Path, model_config: ModelProviderConfig) -> None:
        template = tmp_path / "test.txt"
        template.write_text("Task: $task")

        class OutputModel(BaseModel):
            result: str

        client = LLMClient(model_config)
        pipeline = PromptPipeline(client)

        response = '```json\n{"result": "ok"}\n```'
        with patch.object(client, "chat_completion_with_retry", return_value=response):
            result = pipeline.run(
                template_path=template,
                variables={"task": "x"},
                output_model=OutputModel,
            )
            assert result.result == "ok"

    def test_pipeline_invalid_json(self, tmp_path: Path, model_config: ModelProviderConfig) -> None:
        template = tmp_path / "test.txt"
        template.write_text("Task: $task")

        class OutputModel(BaseModel):
            result: str

        client = LLMClient(model_config)
        pipeline = PromptPipeline(client)

        with patch.object(client, "chat_completion_with_retry", return_value="not json"), \
             pytest.raises(Exception, match="Failed to parse JSON"):
            pipeline.run(
                template_path=template,
                variables={"task": "x"},
                output_model=OutputModel,
            )

    def test_pipeline_validation_failure(self, tmp_path: Path, model_config: ModelProviderConfig) -> None:
        template = tmp_path / "test.txt"
        template.write_text("Task: $task")

        class OutputModel(BaseModel):
            result: int

        client = LLMClient(model_config)
        pipeline = PromptPipeline(client)

        with patch.object(client, "chat_completion_with_retry", return_value='{"result": "not-an-int"}'), \
             pytest.raises(Exception, match="failed validation"):
            pipeline.run(
                template_path=template,
                variables={"task": "x"},
                output_model=OutputModel,
            )


# ---------------------------------------------------------------------------
# LLMCallLogger
# ---------------------------------------------------------------------------


class TestLLMCallLogger:
    """Tests for LLM call logging."""

    def test_log_success(self, tmp_path: Path) -> None:
        logger = LLMCallLogger(tmp_path)
        logger.log(
            prompt_summary="Summarize task",
            response_summary="Result ok",
            duration_ms=123.45,
            model="deepseek-v4",
            success=True,
        )

        log_file = tmp_path / "llm_calls.log"
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["model"] == "deepseek-v4"
        assert entry["success"] is True
        assert entry["duration_ms"] == 123.45
        assert "error" not in entry

    def test_log_error(self, tmp_path: Path) -> None:
        logger = LLMCallLogger(tmp_path)
        logger.log(
            prompt_summary="x",
            response_summary="",
            duration_ms=0,
            model="x",
            success=False,
            error="timeout",
        )

        log_file = tmp_path / "llm_calls.log"
        entry = json.loads(log_file.read_text().strip().splitlines()[0])
        assert entry["success"] is False
        assert entry["error"] == "timeout"

    def test_log_creates_directory(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b"
        logger = LLMCallLogger(nested)
        logger.log("p", "r", 1.0, "m")
        assert (nested / "llm_calls.log").exists()


# ---------------------------------------------------------------------------
# Integration test against real API (skipped by default)
# ---------------------------------------------------------------------------


def _read_tool_config_ini() -> str | None:
    """Read API key from repoctx tool root config.ini."""
    from repoctx import llm as _llm_mod

    tool_root = Path(_llm_mod.__file__).resolve().parent.parent.parent
    ini_path = tool_root / "config.ini"
    if not ini_path.exists():
        return None
    parser = configparser.ConfigParser()
    parser.read(ini_path, encoding="utf-8")
    return parser.get("DEFAULT", "tencent_cloud_llm_api_key", fallback=None)


@pytest.mark.integration
@pytest.mark.skipif(
    not _read_tool_config_ini(),
    reason="No API key in repoctx config.ini",
)
def test_real_api_call() -> None:
    """One real call to verify connectivity with Tencent MaaS."""
    config = ModelProviderConfig(api_key=_read_tool_config_ini())
    client = LLMClient(config)
    result = client.chat_completion(
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'pong' and nothing else."},
        ]
    )
    assert "pong" in result.lower()
