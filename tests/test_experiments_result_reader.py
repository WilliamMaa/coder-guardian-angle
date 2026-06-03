"""Tests for experiment result file reader."""

from __future__ import annotations

import pytest

from repoctx.experiments.result_reader import read_results
from repoctx.models.experiment import ContractBody, ExperimentContract, OutputFile


@pytest.fixture
def contract():
    return ExperimentContract(
        id="test",
        entry_file="test.py",
        contract=ContractBody(
            output_files=[
                OutputFile(pattern="{output_dir}/results.csv"),
                OutputFile(pattern="{output_dir}/model.pt"),
            ],
        ),
    )


class TestReadResults:
    def test_tier1_nohup_reference(self, tmp_path, contract):
        target = tmp_path / "metrics.json"
        target.write_text('{"acc": 0.95}')
        hints = [f"Result file referenced: {target}"]
        results = read_results(hints, contract, tmp_path)
        assert len(results) == 1
        assert results[0].path == str(target)
        assert results[0].source == "nohup_reference"

    def test_tier2_contract_pattern(self, tmp_path, contract):
        csv = tmp_path / "results.csv"
        csv.write_text("epoch,loss\n1,0.5\n")
        results = read_results([], contract, tmp_path)
        paths = {r.path for r in results}
        assert str(csv) in paths
        assert any(r.source == "contract" for r in results)

    def test_tier3_shallow_scan(self, tmp_path, contract):
        # No hints, no contract matches → scan output_dir
        txt = tmp_path / "log.txt"
        txt.write_text("some log")
        results = read_results([], contract, tmp_path)
        assert len(results) >= 1
        assert any(str(txt) == r.path for r in results)

    def test_respects_max_scan_limit(self, tmp_path, contract):
        # Create many files to trigger the limit
        for i in range(15):
            (tmp_path / f"file{i}.txt").write_text("x")
        results = read_results([], contract, tmp_path)
        assert len(results) <= 10

    def test_deduplication(self, tmp_path, contract):
        # Same file referenced in nohup and contract
        csv = tmp_path / "results.csv"
        csv.write_text("x")
        hints = [f"Result file referenced: {csv}"]
        results = read_results(hints, contract, tmp_path)
        # Should only appear once
        assert len([r for r in results if "results.csv" in r.path]) == 1
