"""RepoCtx Guard CLI entry point and commands."""

from pathlib import Path

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
@click.option(
    "--auto-approve",
    is_flag=True,
    default=False,
    help="Auto-accept all discovered protected cores and capabilities without interactive review.",
)
def scan(auto_approve: bool) -> None:
    """Scan project and build the knowledge graph index."""
    from repoctx.scanner.engine import scan_project

    try:
        repograph_dir = scan_project(auto_approve=auto_approve)
        click.echo(f"Scan complete. Knowledge graph written to: {repograph_dir}")
    except Exception as e:
        click.echo(f"Scan failed: {e}", err=True)
        raise click.ClickException(str(e)) from e


@main.command()
@click.argument("task", required=False)
@click.option(
    "--from-file",
    "entry_file",
    type=str,
    default=None,
    help="Analyze a specific entry file instead of using a natural-language task. "
         "Example: --from-file backend/freecall/views.py",
)
@click.option(
    "--max-depth",
    type=int,
    default=2,
    help="Maximum dependency hops to traverse when using --from-file (default: 2).",
)
@click.option(
    "--max-tokens",
    type=int,
    default=3000,
    help="Maximum context length in tokens for LLM-based analysis (default: 3000).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    default=None,
    help="Write report to a file instead of stdout.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (default: text).",
)
def context(
    task: str | None,
    entry_file: str | None,
    max_depth: int,
    max_tokens: int,
    output: str | None,
    output_format: str,
) -> None:
    """Generate minimal but accurate context for a given TASK or ENTRY FILE."""
    content: str

    if entry_file:
        # Entry-driven analysis (no LLM, graph-based)
        from repoctx.entry_context import EntryContextAnalyzer

        try:
            analyzer = EntryContextAnalyzer()
            entry_report = analyzer.analyze(entry_file, max_depth=max_depth)
        except RuntimeError as e:
            raise click.ClickException(str(e)) from e
        except ValueError as e:
            raise click.ClickException(str(e)) from e
        except Exception as e:
            raise click.ClickException(f"Entry context analysis failed: {e}") from e

        if output_format == "json":
            content = entry_report.model_dump_json(indent=2)
        else:
            content = analyzer.format_text(entry_report)
    else:
        # Semantic-driven analysis (LLM-based)
        if not task:
            raise click.ClickException(
                "Please provide a TASK description or use --from-file <path>."
            )
        try:
            router = ContextRouter()
            semantic_report = router.generate(task)
        except ValueError as e:
            raise click.ClickException(str(e)) from e
        except Exception as e:
            raise click.ClickException(f"Context generation failed: {e}") from e

        if output_format == "json":
            content = semantic_report.model_dump_json(indent=2)
        else:
            content = router.format_text(semantic_report)

    if output:
        Path(output).write_text(content, encoding="utf-8")
        click.echo(f"Report written to: {output}")
    else:
        click.echo(content)


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
