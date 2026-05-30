"""Integration tests verifying CLI commands are registered."""

from click.testing import CliRunner

from repoctx.cli import main


def test_main_command_exists() -> None:
    """Main command should be registered and show help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "RepoCtx Guard" in result.output


def test_scan_command_exists() -> None:
    """scan sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["scan", "--help"])
    assert result.exit_code == 0
    assert "Scan project" in result.output


def test_context_command_exists() -> None:
    """context sub-command should be registered with options."""
    runner = CliRunner()
    result = runner.invoke(main, ["context", "--help"])
    assert result.exit_code == 0
    assert "TASK" in result.output
    assert "--max-tokens" in result.output
    assert "--format" in result.output


def test_status_command_exists() -> None:
    """status sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--help"])
    assert result.exit_code == 0
    assert "health status" in result.output


def test_commit_check_command_exists() -> None:
    """commit-check sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["commit-check", "--help"])
    assert result.exit_code == 0
    assert "pre-commit gate" in result.output


def test_test_impact_command_exists() -> None:
    """test-impact sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["test-impact", "--help"])
    assert result.exit_code == 0
    assert "test impact" in result.output


def test_exp_group_exists() -> None:
    """exp group should be registered with sub-commands."""
    runner = CliRunner()
    result = runner.invoke(main, ["exp", "--help"])
    assert result.exit_code == 0
    assert "Experiment management" in result.output
    assert "run" in result.output
    assert "summarize" in result.output


def test_exp_run_command_exists() -> None:
    """exp run sub-command should have required options."""
    runner = CliRunner()
    result = runner.invoke(main, ["exp", "run", "--help"])
    assert result.exit_code == 0
    assert "--name" in result.output
    assert "--cmd" in result.output


def test_exp_summarize_command_exists() -> None:
    """exp summarize sub-command should have required options."""
    runner = CliRunner()
    result = runner.invoke(main, ["exp", "summarize", "--help"])
    assert result.exit_code == 0
    assert "--run" in result.output
