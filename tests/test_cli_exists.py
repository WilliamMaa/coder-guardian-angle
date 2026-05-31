"""Integration tests verifying CLI commands are registered."""

from click.testing import CliRunner

from repoctx.cli import main


def test_main_command_exists() -> None:
    """Main command should be registered and show help."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "Repo Semantic Memory & Engineering Guard" in result.output


# ---------------------------------------------------------------------------
# Semantic Memory commands
# ---------------------------------------------------------------------------


def test_digest_entry_command_exists() -> None:
    """digest-entry sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["digest-entry", "--help"])
    assert result.exit_code == 0
    assert "Digest an entry file" in result.output
    assert "--only" in result.output
    assert "--depth" in result.output


def test_stale_command_exists() -> None:
    """stale sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["stale", "--help"])
    assert result.exit_code == 0


def test_refresh_command_exists() -> None:
    """refresh sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["refresh", "--help"])
    assert result.exit_code == 0
    assert "--affected" in result.output


def test_semantic_diff_command_exists() -> None:
    """semantic-diff sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["semantic-diff", "--help"])
    assert result.exit_code == 0
    assert "--since" in result.output


def test_export_context_command_exists() -> None:
    """export-context sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["export-context", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Task workspace commands
# ---------------------------------------------------------------------------


def test_task_group_exists() -> None:
    """task group should be registered with sub-commands."""
    runner = CliRunner()
    result = runner.invoke(main, ["task", "--help"])
    assert result.exit_code == 0
    assert "Task workspace" in result.output
    assert "start" in result.output
    assert "export" in result.output
    assert "status" in result.output


def test_task_start_command_exists() -> None:
    """task start sub-command should have required options."""
    runner = CliRunner()
    result = runner.invoke(main, ["task", "start", "--help"])
    assert result.exit_code == 0
    assert "--entry" in result.output


# ---------------------------------------------------------------------------
# Guard commands
# ---------------------------------------------------------------------------


def test_status_command_exists() -> None:
    """status sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["status", "--help"])
    assert result.exit_code == 0
    assert "health status" in result.output


def test_structure_check_command_exists() -> None:
    """structure-check sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["structure-check", "--help"])
    assert result.exit_code == 0


def test_test_impact_command_exists() -> None:
    """test-impact sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["test-impact", "--help"])
    assert result.exit_code == 0
    assert "--task" in result.output


def test_legacy_check_command_exists() -> None:
    """legacy-check sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["legacy-check", "--help"])
    assert result.exit_code == 0


def test_commit_check_command_exists() -> None:
    """commit-check sub-command should be registered."""
    runner = CliRunner()
    result = runner.invoke(main, ["commit-check", "--help"])
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Experiment commands
# ---------------------------------------------------------------------------


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
    """exp summarize sub-command should accept a RUN_ID argument."""
    runner = CliRunner()
    result = runner.invoke(main, ["exp", "summarize", "--help"])
    assert result.exit_code == 0
    assert "RUN_ID" in result.output
