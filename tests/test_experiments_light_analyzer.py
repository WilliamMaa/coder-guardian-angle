"""Tests for light-weight nohup analysis."""

from __future__ import annotations

import pytest

from repoctx.experiments.light_analyzer import light_analyze
from repoctx.models.experiment import ExperimentContract


@pytest.fixture
def contract():
    return ExperimentContract(
        id="test",
        entry_file="test.py",
        contract={"purpose": "test"},
    )


class TestLightAnalyze:
    def test_completed_status(self, contract):
        text = "Training complete\nDone\n"
        result = light_analyze(text, contract)
        assert result.status == "completed"

    def test_oom_status(self, contract):
        text = "Epoch 3/50\nCUDA out of memory\n"
        result = light_analyze(text, contract)
        assert result.status == "oom"
        assert any("OOM" in h for h in result.hints)

    def test_crashed_status(self, contract):
        text = "Segmentation fault (core dumped)\n"
        result = light_analyze(text, contract)
        assert result.status == "crashed"

    def test_failed_status(self, contract):
        text = "Traceback (most recent call last):\n  File ...\n"
        result = light_analyze(text, contract)
        assert result.status == "failed"

    def test_killed_status(self, contract):
        text = "Killed\n"
        result = light_analyze(text, contract)
        assert result.status == "killed"

    def test_unknown_when_no_signals(self, contract):
        text = "Just some random log output\n"
        result = light_analyze(text, contract)
        assert result.status == "unknown"

    def test_error_overrides_completion(self, contract):
        """If both error and completion signals exist, error wins."""
        text = "Training complete\nCUDA out of memory\n"
        result = light_analyze(text, contract)
        assert result.status == "oom"

    def test_extracts_file_references(self, contract):
        text = "Results saved to ./outputs/metrics.json\nOutput written to ./runs/final.txt\n"
        result = light_analyze(text, contract)
        assert any("metrics.json" in h for h in result.hints)
        assert any("final.txt" in h for h in result.hints)
