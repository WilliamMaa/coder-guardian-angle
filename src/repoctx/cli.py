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
# Project initialization
# ---------------------------------------------------------------------------

@main.command()
@click.option(
    "--project-name",
    "-n",
    default="my-project",
    help="Project name written to .repoctx.yaml (default: my-project).",
)
@click.option(
    "--language",
    "-l",
    default="python",
    help="Primary programming language (default: python).",
)
@click.option(
    "--framework",
    "-f",
    default="django",
    help="Primary framework (default: django).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing .repoctx.yaml.",
)
def init(project_name: str, language: str, framework: str, force: bool) -> None:
    """Initialize the current project for repoctx."""
    from pathlib import Path

    from repoctx.initialization import init_project

    try:
        created = init_project(
            Path.cwd(),
            project_name=project_name,
            language=language,
            framework=framework,
            force=force,
        )
        click.echo("Initialized repoctx project.")
        for p in created:
            click.echo(f"  → {p}")
    except Exception as e:
        raise click.ClickException(str(e)) from e


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
@click.option(
    "--force",
    is_flag=True,
    help="Force re-generation even if existing cards are up-to-date.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=True,
    help="Show detailed progress output (default: on).",
)
def digest_entry(
    file_path: str,
    only: str | None,
    depth: int,
    output_dir: str | None,
    force: bool,
    verbose: bool,
) -> None:
    """Digest an entry file and generate semantic memory cards."""
    import logging

    if verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(levelname)s: %(message)s",
            force=True,
        )

    from repoctx.semantic_memory.engine import SemanticDigestEngine
    from repoctx.utils.project import find_project_root

    click.echo(f"repoctx digest-entry {file_path}")

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    click.echo(f"Project root: {project_root}")
    target_symbols = [s.strip() for s in only.split(",")] if only else None
    if target_symbols:
        click.echo(f"Target symbols: {target_symbols}")
    click.echo(f"Max depth: {depth}")
    if force:
        click.echo("Force mode: ON — existing cards will be overwritten.")
    click.echo("Initializing engine...")

    try:
        engine = SemanticDigestEngine(project_root)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize engine: {e}") from e

    click.echo("Starting digestion...")
    try:
        result = engine.digest(
            file_path,
            target_symbols=target_symbols,
            max_depth=depth,
            force=force,
        )
        click.echo(f"\nDigest complete: {len(result.cards)} cards generated.")
        for card_path in result.written_paths:
            click.echo(f"  → {card_path}")
    except Exception as e:
        raise click.ClickException(f"Digest failed: {e}") from e


@main.command("list")
def list_cards() -> None:
    """List all semantic memory cards in the project."""
    from pathlib import Path

    from repoctx.utils.project import find_project_root
    from repoctx.utils.yaml_io import load_yaml

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    base = project_root / ".repograph" / "semantic_memory"
    sections = [
        ("Entry Cards", base / "entries"),
        ("Symbol Cards", base / "symbols"),
        ("Context Packs", base / "context_packs"),
    ]

    found_any = False
    for title, path in sections:
        if not path.exists():
            continue
        files = sorted(path.glob("*.yaml"))
        if not files:
            continue
        found_any = True
        click.echo(f"\n{title}")
        click.echo("-" * 60)
        for f in files:
            try:
                raw = load_yaml(f)
                cid = raw.get("id", f.stem)
                status = raw.get("version", {}).get("status", "unknown")
                generated = raw.get("version", {}).get("generated_at", "")[:19]
                click.echo(f"  [{status:8}] {cid:50}  {generated}")
            except Exception:
                click.echo(f"  [broken ] {f.name}")

    if not found_any:
        click.echo("No semantic memory cards found.")
        click.echo("Run 'repoctx digest-entry <file>' to generate some.")


@main.command()
def stale() -> None:
    """Check which semantic memory cards are stale (source changed)."""
    from repoctx.semantic_memory.refresh_engine import RefreshEngine
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = RefreshEngine(project_root)
    report = engine.find_stale()
    total = len(report.stale_entries) + len(report.stale_symbols)

    for cid in report.stale_entries:
        click.echo(f"  STALE  {cid}  (entry)")
    for cid in report.stale_symbols:
        click.echo(f"  STALE  {cid}  (symbol)")

    if total == 0:
        click.echo("All cards are fresh — source files have not changed.")
    else:
        click.echo(f"\n{total} stale card(s) found.")
        click.echo("Run 'repoctx refresh --affected' to re-generate.")


@main.command("delete-card")
@click.argument("card_id")
def delete_card(card_id: str) -> None:
    """Delete a semantic memory card by its ID."""
    from pathlib import Path

    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    base = project_root / ".repograph" / "semantic_memory"
    candidates = [
        base / "entries" / f"{card_id}.yaml",
        base / "symbols" / f"{card_id}.yaml",
        base / "context_packs" / f"{card_id}.yaml",
    ]

    for path in candidates:
        if path.exists():
            path.unlink()
            click.echo(f"Deleted {card_id}")
            return

    raise click.ClickException(
        f"Card not found: {card_id}\n"
        f"Use 'repoctx list' to see available cards."
    )


@main.command()
@click.option(
    "--affected",
    is_flag=True,
    help="Refresh only stale cards and entries that depend on stale symbols.",
)
def refresh(affected: bool) -> None:
    """Refresh semantic memory cards."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
        force=True,
    )

    from repoctx.semantic_memory.engine import SemanticDigestEngine
    from repoctx.semantic_memory.refresh_engine import RefreshEngine
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    refresh_engine = RefreshEngine(project_root)

    if not affected:
        click.echo("Use --affected to refresh stale cards. Without --affected, nothing happens.")
        return

    click.echo("Scanning for stale cards...")
    report = refresh_engine.find_stale()
    total_stale = len(report.stale_entries) + len(report.stale_symbols)
    click.echo(f"Found {total_stale} stale card(s).")

    if total_stale == 0:
        click.echo("Nothing to refresh.")
        return

    click.echo("Initializing digest engine...")
    try:
        digest_engine = SemanticDigestEngine(project_root)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize engine: {e}") from e

    click.echo("Refreshing...")
    refreshed, messages = refresh_engine.refresh_affected(digest_engine)

    for msg in messages:
        click.echo(f"  {msg}")

    click.echo(f"\nRefresh complete: {refreshed} entry(s) refreshed.")


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


@task.command("list")
def task_list() -> None:
    """List all task workspaces."""
    from pathlib import Path

    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    tasks_dir = project_root / ".repograph" / "tasks"
    if not tasks_dir.exists():
        click.echo("No tasks found.")
        return

    tasks = sorted(d for d in tasks_dir.iterdir() if d.is_dir())
    if not tasks:
        click.echo("No tasks found.")
        return

    click.echo(f"{'Task ID':<50} {'Created'}")
    click.echo("-" * 70)
    for task_path in tasks:
        # Try to read created timestamp from task_intent.md
        created = ""
        intent_path = task_path / "task_intent.md"
        if intent_path.exists():
            text = intent_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                if line.startswith("**Created:**"):
                    created = line.replace("**Created:**", "").strip()
                    break
        click.echo(f"{task_path.name:<50} {created}")


@task.command("start")
@click.argument("task_name")
@click.option(
    "--entry",
    required=True,
    help="Entry point for the task (file.py::symbol).",
)
def task_start(task_name: str, entry: str) -> None:
    """Start a new task workspace for the given entry point."""
    from repoctx.semantic_memory.engine import SemanticDigestEngine
    from repoctx.task_workspace.engine import TaskWorkspace, TaskWorkspaceError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    click.echo(f"Starting task workspace: {task_name}")
    click.echo(f"Entry point: {entry}")

    try:
        digest_engine = SemanticDigestEngine(project_root)
    except Exception as e:
        raise click.ClickException(f"Failed to initialize LLM engine: {e}") from e

    try:
        workspace = TaskWorkspace.create(
            project_root,
            task_name=task_name,
            entry_ref=entry,
            pipeline=digest_engine.pipeline,
        )
    except TaskWorkspaceError as e:
        raise click.ClickException(str(e)) from e
    except Exception as e:
        raise click.ClickException(f"Failed to create task workspace: {e}") from e

    click.echo(f"\nTask workspace created: {workspace.task_id}")
    click.echo(f"  → {workspace.task_root}")
    click.echo("\nNext steps:")
    click.echo("  1. Review accepted_understanding.md")
    click.echo("  2. Fill in out_of_scope.yaml and frozen_assumptions.yaml")
    click.echo("  3. Run 'repoctx task validate <task_id>' before committing")


@task.command("export")
@click.argument("task_id")
def task_export(task_id: str) -> None:
    """Export a task workspace as unified markdown context."""
    from repoctx.task_workspace.engine import TaskWorkspace
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    workspace = TaskWorkspace(project_root, task_id)
    if not workspace.task_root.exists():
        raise click.ClickException(
            f"Task not found: {task_id}\n"
            f"Use 'repoctx task status <task_id>' to see available tasks."
        )

    output = workspace.export()
    click.echo(output)


@task.command("status")
@click.argument("task_id")
def task_status(task_id: str) -> None:
    """Show task workspace status and file listing."""
    from pathlib import Path

    from repoctx.task_workspace.engine import TaskWorkspace
    from repoctx.utils.project import find_project_root
    from repoctx.utils.yaml_io import load_yaml

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    workspace = TaskWorkspace(project_root, task_id)
    if not workspace.task_root.exists():
        click.echo(f"Task not found: {task_id}")
        tasks_dir = project_root / ".repograph" / "tasks"
        if tasks_dir.exists():
            click.echo("Available tasks:")
            for d in sorted(tasks_dir.iterdir()):
                if d.is_dir():
                    click.echo(f"  {d.name}")
        raise click.ClickException(f"Task workspace not found: {task_id}")

    click.echo(f"Task: {task_id}")
    click.echo(f"Root: {workspace.task_root}")
    click.echo("")

    # Show files
    for f in sorted(workspace.task_root.rglob("*")):
        if f.is_file():
            rel = f.relative_to(workspace.task_root)
            click.echo(f"  {rel}")

    # Show out_of_scope count
    oos_path = workspace.task_root / "out_of_scope.yaml"
    if oos_path.exists():
        try:
            oos = load_yaml(oos_path)
            count = len(oos.get("items", []))
            click.echo(f"\nOut of scope items: {count}")
        except Exception:
            pass

    # Show frozen assumptions count
    fa_path = workspace.task_root / "frozen_assumptions.yaml"
    if fa_path.exists():
        try:
            fa = load_yaml(fa_path)
            count = len(fa.get("assumptions", []))
            click.echo(f"Frozen assumptions: {count}")
        except Exception:
            pass

    # Show active files
    af_path = workspace.task_root / "active_files.yaml"
    if af_path.exists():
        try:
            af = load_yaml(af_path)
            files = af.get("files", [])
            if files:
                click.echo(f"\nActive files ({len(files)}):")
                for file_path in files:
                    click.echo(f"  - {file_path}")
        except Exception:
            pass


@task.command("validate")
@click.argument("task_id")
def task_validate(task_id: str) -> None:
    """Validate current changes against task constraints."""
    from repoctx.task_workspace.engine import TaskWorkspace
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    workspace = TaskWorkspace(project_root, task_id)
    if not workspace.task_root.exists():
        raise click.ClickException(
            f"Task not found: {task_id}\n"
            f"Use 'repoctx task status <task_id>' to see available tasks."
        )

    result = workspace.validate()
    click.echo(result.format())
    if not result.passed:
        raise click.ClickException("Validation failed.")


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
