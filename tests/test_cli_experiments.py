"""CLI tests for experiment commands."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from repoctx.cli import main


class TestExpCLI:
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def project(self, tmp_path, monkeypatch):
        """Create a minimal project structure in a temp directory."""
        monkeypatch.setenv("REPOCTX_REPOGRAPH_DIR", str(tmp_path / ".repograph"))
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: testproj\nlanguage: python\nframework: pytest\n"
        )
        entry = tmp_path / "experiments" / "train.py"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--epochs', default=10)\n"
        )
        return tmp_path

    def test_exp_init(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        result = runner.invoke(main, [
            "exp", "init",
            "--entry", "experiments/train.py",
            "--name", "my_exp",
            "--purpose", "Training test",
        ])
        assert result.exit_code == 0
        assert "Experiment contract created" in result.output
        assert "my_exp" in result.output
        assert "--epochs" in result.output

    def test_exp_init_duplicate_fails(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        runner.invoke(main, [
            "exp", "init",
            "--entry", "experiments/train.py",
            "--name", "dup",
        ])
        result = runner.invoke(main, [
            "exp", "init",
            "--entry", "experiments/train.py",
            "--name", "dup",
        ])
        assert result.exit_code != 0
        assert "already exists" in result.output

    def test_exp_history_empty(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        result = runner.invoke(main, ["exp", "history", "no_such"])
        assert result.exit_code == 0
        assert "No runs found" in result.output

    def test_exp_diagnose_no_runs(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        result = runner.invoke(main, ["exp", "diagnose", "no_such"])
        assert result.exit_code != 0
        assert "No runs found" in result.output

    def test_exp_ps_empty(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        result = runner.invoke(main, ["exp", "ps"])
        assert result.exit_code == 0
        assert "No running experiments" in result.output

    def test_exp_logs_no_runs(self, runner, project, monkeypatch):
        monkeypatch.chdir(project)
        result = runner.invoke(main, ["exp", "logs", "no_such"])
        assert result.exit_code != 0
        assert "No runs found" in result.output
