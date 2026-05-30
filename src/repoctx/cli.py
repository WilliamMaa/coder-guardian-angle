"""RepoCtx Guard CLI entry point and commands."""

import click

from repoctx.context_router import ContextRouter


@click.group()
@click.version_option(version="0.1.0", prog_name="repoctx")
def main() -> None:
    """RepoCtx Guard — AI-assisted Development Control Plane.

    Standing beside the AI coder, constraining it, reminding it,
    reviewing it, and recording it.
    """
    pass


@main.command()
def scan() -> None:
    """Scan project and build the knowledge graph index."""
    from repoctx.scanner.engine import scan_project

    try:
        repograph_dir = scan_project()
        click.echo(f"Scan complete. Knowledge graph written to: {repograph_dir}")
    except Exception as e:
        click.echo(f"Scan failed: {e}", err=True)
        raise click.ClickException(str(e)) from e


@main.command()
@click.argument("task")
@click.option(
    "--max-tokens",
    type=int,
    default=3000,
    help="Maximum context length in tokens (default: 3000).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text).",
)
def context(task: str, max_tokens: int, output_format: str) -> None:
    """Generate minimal but accurate context for a given TASK."""
    try:
        router = ContextRouter()
        report = router.generate(task)
    except ValueError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:
        raise click.ClickException(f"Context generation failed: {e}") from e

    if output_format == "json":
        click.echo(report.model_dump_json(indent=2))
    else:
        click.echo(router.format_text(report))


@main.command()
def status() -> None:
    """Show current working tree health status."""
    click.echo("[repoctx status] Not yet implemented.")


@main.command("commit-check")
def commit_check() -> None:
    """Unified pre-commit gate check."""
    click.echo("[repoctx commit-check] Not yet implemented.")


@main.command("test-impact")
def test_impact() -> None:
    """Analyze test impact of current changes."""
    click.echo("[repoctx test-impact] Not yet implemented.")


@main.group()
def exp() -> None:
    """Experiment management commands."""
    pass


@exp.command("run")
@click.option("--name", required=True, help="Experiment name (unique).")
@click.option("--cmd", required=True, help="Command to run the experiment.")
@click.option("--config", help="Path to experiment config file.")
@click.option("--notify", help="Slack channel or email to notify on completion.")
def exp_run(name: str, cmd: str, config: str | None, notify: str | None) -> None:
    """Run an experiment with monitoring and summary."""
    click.echo(f"[repoctx exp run] name={name}, cmd={cmd}")
    if config:
        click.echo(f"  config={config}")
    if notify:
        click.echo(f"  notify={notify}")
    click.echo("Not yet implemented.")


@exp.command("summarize")
@click.option("--run", "run_name", required=True, help="Experiment name to summarize.")
def exp_summarize(run_name: str) -> None:
    """Summarize a completed experiment run."""
    click.echo(f"[repoctx exp summarize] run={run_name}")
    click.echo("Not yet implemented.")


if __name__ == "__main__":
    main()
