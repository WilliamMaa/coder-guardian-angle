"""RepoCtx Guard CLI — new command set for Semantic Memory & Engineering Guard."""

from __future__ import annotations

import click


@click.group()
@click.version_option(version="0.2.0", prog_name="repoctx")
def main() -> None:
    """Repo Semantic Memory & Engineering Guard.

    A semantic memory layer between AI coders and your project.
    It digests code from entry points, persists call-chain semantics,
    and guards against structural, test, and legacy violations.
    """
    pass


# ---------------------------------------------------------------------------
# Semantic Memory
# ---------------------------------------------------------------------------

@main.command()
@click.argument("file_path")
@click.option(
    "--only",
    type=str,
    default=None,
    help="Comma-separated list of function names to digest (default: all top-level functions).",
)
@click.option(
    "--depth",
    type=int,
    default=3,
    help="Maximum call-chain depth to trace (default: 3).",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(file_okay=False, writable=True),
    default=None,
    help="Directory to write generated cards (default: .repograph/semantic_memory/).",
)
def digest_entry(file_path: str, only: str | None, depth: int, output_dir: str | None) -> None:
    """Digest an entry file and generate semantic memory cards."""
    from repoctx.semantic_memory.engine import SemanticDigestEngine
    from repoctx.utils.project import find_project_root

    project_root = find_project_root()
    target_symbols = [s.strip() for s in only.split(",")] if only else None

    engine = SemanticDigestEngine(project_root)
    try:
        result = engine.digest(file_path, target_symbols=target_symbols, max_depth=depth)
        click.echo(f"Digest complete: {len(result.cards)} cards generated.")
        for card_path in result.written_paths:
            click.echo(f"  → {card_path}")
    except Exception as e:
        raise click.ClickException(str(e)) from e


@main.command()
def stale() -> None:
    """Check which semantic memory cards are stale."""
    click.echo("[repoctx stale] Not yet implemented.")


@main.command()
@click.option("--affected", is_flag=True, help="Refresh only affected cards.")
def refresh(affected: bool) -> None:
    """Refresh semantic memory cards."""
    click.echo(f"[repoctx refresh] affected={affected}. Not yet implemented.")


@main.command()
@click.option("--since", default="main", help="Git ref to compare against.")
def semantic_diff(since: str) -> None:
    """Summarize semantic changes since a git ref."""
    click.echo(f"[repoctx semantic-diff] since={since}. Not yet implemented.")


@main.command()
@click.argument("flow_or_entry")
def export_context(flow_or_entry: str) -> None:
    """Export a context pack for a flow or entry."""
    click.echo(f"[repoctx export-context] {flow_or_entry}. Not yet implemented.")


# ---------------------------------------------------------------------------
# Task Workspace
# ---------------------------------------------------------------------------

@main.group()
def task() -> None:
    """Task workspace commands."""
    pass


@task.command("start")
@click.argument("task_name")
@click.option("--entry", required=True, help="Entry point for the task (file::symbol).")
def task_start(task_name: str, entry: str) -> None:
    """Start a new task workspace."""
    click.echo(f"[repoctx task start] {task_name} entry={entry}. Not yet implemented.")


@task.command("export")
@click.argument("task_id")
def task_export(task_id: str) -> None:
    """Export a task workspace as unified context."""
    click.echo(f"[repoctx task export] {task_id}. Not yet implemented.")


@task.command("status")
@click.argument("task_id")
def task_status(task_id: str) -> None:
    """Show task workspace status."""
    click.echo(f"[repoctx task status] {task_id}. Not yet implemented.")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

@main.command()
def status() -> None:
    """Show current working tree health status."""
    click.echo("[repoctx status] Not yet implemented.")


@main.command()
def structure_check() -> None:
    """Check new code structure against engineering principles."""
    click.echo("[repoctx structure-check] Not yet implemented.")


@main.command()
@click.option("--task", "task_id", help="Task ID for test-impact analysis.")
def test_impact(task_id: str | None) -> None:
    """Analyze test impact of current changes."""
    click.echo(f"[repoctx test-impact] task={task_id}. Not yet implemented.")


@main.command()
def legacy_check() -> None:
    """Check for legacy core violations."""
    click.echo("[repoctx legacy-check] Not yet implemented.")


@main.command()
def commit_check() -> None:
    """Unified pre-commit gate check."""
    click.echo("[repoctx commit-check] Not yet implemented.")


# ---------------------------------------------------------------------------
# Experiment Agent
# ---------------------------------------------------------------------------

@main.group()
def exp() -> None:
    """Experiment management commands."""
    pass


@exp.command("init")
def exp_init() -> None:
    """Initialize an experiment workspace."""
    click.echo("[repoctx exp init] Not yet implemented.")


@exp.command("check")
@click.option("--config", required=True, help="Path to experiment config file.")
def exp_check(config: str) -> None:
    """Run pre-experiment checks."""
    click.echo(f"[repoctx exp check] config={config}. Not yet implemented.")


@exp.command("run")
@click.option("--name", required=True, help="Experiment name (unique).")
@click.option("--cmd", required=True, help="Command to run the experiment.")
@click.option("--notify", help="Slack channel or email to notify on completion.")
def exp_run(name: str, cmd: str, notify: str | None) -> None:
    """Run an experiment with monitoring and summary."""
    click.echo(f"[repoctx exp run] name={name}, cmd={cmd}. Not yet implemented.")


@exp.command("summarize")
@click.argument("run_id")
def exp_summarize(run_id: str) -> None:
    """Summarize a completed experiment run."""
    click.echo(f"[repoctx exp summarize] run={run_id}. Not yet implemented.")


@exp.command("diagnose")
@click.argument("run_id")
def exp_diagnose(run_id: str) -> None:
    """Diagnose an experiment run with dual-track analysis."""
    click.echo(f"[repoctx exp diagnose] run={run_id}. Not yet implemented.")


if __name__ == "__main__":
    main()
