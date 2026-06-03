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
    """Digest an entry file into semantic cards."""
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

    from repoctx.utils.project import get_repograph_dir

    repograph_dir = get_repograph_dir(project_root)
    base = repograph_dir / "semantic_memory"
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
    """Show stale cards (source changed)."""
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

    from repoctx.utils.project import get_repograph_dir

    repograph_dir = get_repograph_dir(project_root)
    base = repograph_dir / "semantic_memory"
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
@click.argument("paths", nargs=-1)
@click.option(
    "--all",
    "scan_all",
    is_flag=True,
    help="Audit every Python file in the project.",
)
@click.option(
    "--dir",
    "dirs",
    multiple=True,
    help="Audit all .py files under specific directorie(s).",
)
@click.option(
    "--digest",
    "auto_digest",
    is_flag=True,
    help="Auto-digest files that lack semantic memory (calls LLM).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    help="Write report to a file instead of stdout.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show reuse suggestions and extra detail (default: errors only).",
)
@click.option(
    "--deep",
    is_flag=True,
    help="Use LLM to analyze view files and suggest where helpers should be moved.",
)
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against when not using --all (default: uncommitted changes).",
)
def audit(
    paths: tuple[str, ...],
    scan_all: bool,
    dirs: tuple[str, ...],
    auto_digest: bool,
    output: str | None,
    verbose: bool,
    deep: bool,
    since: str,
) -> None:
    """One-shot code quality audit.

    This is the primary command for code quality audits. It scans files,
    optionally digests missing ones, runs all guard checks, and produces
    a unified report.

    By default only hard errors are shown. Use --verbose to see reuse
    suggestions and warnings.

    \b
    Examples:
      repoctx audit                    # audit git diff only
      repoctx audit --all              # audit entire project
      repoctx audit --all --digest     # audit + auto-digest missing files
      repoctx audit --dir app/views/   # audit a directory
      repoctx audit --all -o report.md # write report to file
      repoctx audit --all -v           # show everything including reuse suggestions
    """
    from pathlib import Path

    from repoctx.audit import AuditEngine
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    # Build file list
    file_list: list[str] = []
    if paths:
        file_list.extend(paths)
    if dirs:
        for d in dirs:
            target = project_root / d
            if target.is_dir():
                file_list.extend(
                    p.relative_to(project_root).as_posix()
                    for p in target.rglob("*.py")
                )
            else:
                click.echo(f"Warning: --dir '{d}' is not a directory, skipping.")

    engine = AuditEngine(project_root)
    result = engine.audit(
        files=file_list if file_list else None,
        scan_all=scan_all,
        auto_digest=auto_digest,
        since=since,
    )

    # Filter to errors only unless verbose
    if not verbose:
        result.reuse_suggestions = []
        result.structure_violations = [v for v in result.structure_violations if v.severity == "error"]
        result.legacy_violations = [v for v in result.legacy_violations if v.severity == "error"]

    # --deep: LLM-driven refactoring suggestions for every scanned file
    if deep:
        from repoctx.refactor.refactor_suggest import RefactorSuggestEngine

        target_files = result.files_scanned
        if target_files:
            deep_blocks: list[str] = []
            try:
                refactor_engine = RefactorSuggestEngine(project_root)
                for tf in target_files:
                    try:
                        r = refactor_engine.suggest(tf)
                        deep_blocks.append(r.format_markdown())
                    except Exception as e:
                        deep_blocks.append(f"**{tf}:** Skipped — {e}")
                result.deep_analysis = deep_blocks
            except Exception as e:
                result.deep_analysis = [f"Deep analysis unavailable: {e}"]
        else:
            result.deep_analysis = ["--deep: no Python files in scanned scope."]

    report = AuditEngine.generate_report(result)

    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}")
    else:
        click.echo(report)

    hard_errors = len(
        [v for v in result.structure_violations + result.legacy_violations if v.severity == "error"]
    )
    if hard_errors:
        raise click.ClickException(f"Audit failed: {hard_errors} hard error(s).")


@main.command()
@click.option(
    "--affected",
    is_flag=True,
    help="Refresh stale cards and entries that depend on stale symbols.",
)
@click.option(
    "--prune",
    is_flag=True,
    help="Remove orphaned cards whose source functions no longer exist.",
)
def refresh(affected: bool, prune: bool) -> None:
    """Refresh stale cards.

    Use --affected to re-generate stale cards.
    Use --prune to clean up orphaned cards after refactoring.
    Both flags can be combined.
    """
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

    # --- Prune phase ---
    if prune:
        click.echo("Pruning orphaned cards...")
        prune_report = refresh_engine.prune()

        if prune_report.pruned_entries:
            click.echo(f"  Pruned {len(prune_report.pruned_entries)} entry card(s):")
            for cid in prune_report.pruned_entries:
                click.echo(f"    - {cid}")

        if prune_report.pruned_symbols:
            click.echo(f"  Pruned {len(prune_report.pruned_symbols)} symbol card(s):")
            for cid in prune_report.pruned_symbols:
                click.echo(f"    - {cid}")

        if prune_report.pruned_contexts:
            click.echo(f"  Pruned {len(prune_report.pruned_contexts)} context pack(s):")
            for cid in prune_report.pruned_contexts:
                click.echo(f"    - {cid}")

        if prune_report.new_functions:
            click.echo(f"\n  {len(prune_report.new_functions)} new function(s) without cards:")
            for f in prune_report.new_functions:
                click.echo(f"    - {f}")
            click.echo("  Run 'repoctx audit --all --digest' to generate cards for them.")

        total_pruned = (
            len(prune_report.pruned_entries)
            + len(prune_report.pruned_symbols)
            + len(prune_report.pruned_contexts)
        )
        if total_pruned == 0 and not prune_report.new_functions:
            click.echo("  No orphaned cards found. Semantic memory is clean.")

        if not affected:
            return

    # --- Refresh phase ---
    if not affected:
        if not prune:
            click.echo("Use --affected to refresh stale cards, or --prune to clean up orphans.")
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
    """Export a context pack."""
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

    from repoctx.utils.project import get_repograph_dir

    tasks_dir = get_repograph_dir(project_root) / "tasks"
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
        from repoctx.utils.project import get_repograph_dir

        tasks_dir = get_repograph_dir(project_root) / "tasks"
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
# Rules
# ---------------------------------------------------------------------------

@main.command("rules")
def show_rules() -> None:
    """Display current engineering constitution rules."""
    from pathlib import Path

    from repoctx.utils.project import find_project_root
    from repoctx.utils.yaml_io import load_yaml

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    from repoctx.utils.project import get_repograph_dir

    path = get_repograph_dir(project_root) / "guards" / "engineering_constitution.yaml"
    if not path.exists():
        click.echo("No engineering constitution found.")
        return

    try:
        data = load_yaml(path)
    except Exception as e:
        raise click.ClickException(f"Failed to read rules: {e}") from e

    click.echo("Engineering Constitution")
    click.echo("=" * 40)

    # Principles
    principles = data.get("principles", [])
    if principles:
        click.echo("\nPrinciples:")
        for p in principles:
            click.echo(f"  - {p}")

    # Rules
    rules = data.get("rules", {})
    if rules:
        click.echo("\nRules:")
        for rule_id, cfg in rules.items():
            if isinstance(cfg, dict):
                enabled = "ON" if cfg.get("enabled", True) else "OFF"
                severity = cfg.get("severity", "error")
                desc = cfg.get("description", "")
                click.echo(f"  [{enabled:3}] [{severity:7}] {rule_id}")
                if desc:
                    click.echo(f"        {desc}")
            else:
                enabled = "ON" if cfg else "OFF"
                click.echo(f"  [{enabled:3}] {rule_id}")
    else:
        click.echo("\nNo rules configured.")


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@main.command("migrate-repograph")
@click.option(
    "--to",
    type=str,
    help=(
        "New repograph directory path. Can be absolute or relative to project root. "
        "If provided, updates .repoctx.yaml and migrates data."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be migrated without making changes.",
)
def migrate_repograph(to: str | None, dry_run: bool) -> None:
    """Migrate .repograph data to a new location.

    Usage:
      # Set new location in .repoctx.yaml and migrate
      repoctx migrate-repograph --to /path/to/new/repograph

      # Preview migration without moving data
      repoctx migrate-repograph --to /path/to/new/repograph --dry-run

      # Migrate to the location already configured in .repoctx.yaml
      repoctx migrate-repograph
    """
    import shutil
    from pathlib import Path

    from repoctx.utils.project import find_project_root, get_repograph_dir
    from repoctx.utils.yaml_io import dump_yaml, load_yaml

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    config_path = project_root / ".repoctx.yaml"
    config = load_yaml(config_path)

    # Determine old (current) location
    old_dir = get_repograph_dir(project_root)

    # Determine new location
    if to:
        new_dir = Path(to)
        if not new_dir.is_absolute():
            new_dir = project_root / new_dir
        new_dir = new_dir.resolve()
    else:
        new_dir_str = config.get("repograph_dir")
        if not new_dir_str:
            raise click.ClickException(
                "No repograph_dir configured in .repoctx.yaml.\n"
                "Use --to to specify a new location, or add repograph_dir to .repoctx.yaml first."
            )
        new_dir = Path(new_dir_str)
        if not new_dir.is_absolute():
            new_dir = (project_root / new_dir).resolve()

    if old_dir == new_dir:
        click.echo(f"Source and destination are the same:\n  {old_dir}")
        click.echo("Nothing to migrate.")
        return

    click.echo(f"Project root:  {project_root}")
    click.echo(f"Current:       {old_dir}")
    click.echo(f"Destination:   {new_dir}")

    if not old_dir.exists():
        click.echo("\nNo existing repograph data found at current location.")
        if not dry_run and to:
            # Just update config
            config["repograph_dir"] = str(new_dir)
            dump_yaml(config, config_path)
            click.echo(f"Updated .repoctx.yaml repograph_dir → {new_dir}")
        return

    # Count what would be migrated
    files_to_migrate = list(old_dir.rglob("*"))
    files_count = len([f for f in files_to_migrate if f.is_file()])
    dirs_count = len([d for d in files_to_migrate if d.is_dir()])

    click.echo(f"\nItems to migrate: {files_count} files, {dirs_count} directories")

    if dry_run:
        click.echo("\n--dry-run: no changes made.")
        return

    if new_dir.exists():
        existing = list(new_dir.iterdir())
        if existing:
            raise click.ClickException(
                f"Destination already exists and is not empty:\n  {new_dir}\n"
                f"Move or delete it first, or choose a different --to path."
            )

    # Perform migration
    click.echo("\nMigrating...")
    try:
        shutil.copytree(old_dir, new_dir)
    except Exception as e:
        raise click.ClickException(f"Migration failed during copy: {e}") from e

    # Update config if --to was specified
    if to:
        config["repograph_dir"] = str(new_dir)
        dump_yaml(config, config_path)
        click.echo(f"Updated .repoctx.yaml repograph_dir → {new_dir}")

    # Verify
    new_files = list(new_dir.rglob("*"))
    new_files_count = len([f for f in new_files if f.is_file()])
    if new_files_count == files_count:
        click.echo(f"\n✅ Migration complete. {files_count} files copied.")
        click.echo(f"You can now delete the old location if desired:\n  rm -rf {old_dir}")
    else:
        click.echo(f"\n⚠️ Migration finished but file count mismatch: {new_files_count} vs {files_count}")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

@main.command(deprecated=True)
def status() -> None:
    """Show project health."""
    from pathlib import Path

    from repoctx.semantic_memory.refresh_engine import RefreshEngine
    from repoctx.utils.project import find_project_root
    from repoctx.utils.yaml_io import load_yaml

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    from repoctx.utils.project import get_repograph_dir

    repograph = get_repograph_dir(project_root)

    # Semantic memory stats
    entries_dir = repograph / "semantic_memory" / "entries"
    symbols_dir = repograph / "semantic_memory" / "symbols"
    context_dir = repograph / "semantic_memory" / "context_packs"
    entry_count = len(list(entries_dir.glob("*.yaml"))) if entries_dir.exists() else 0
    symbol_count = len(list(symbols_dir.glob("*.yaml"))) if symbols_dir.exists() else 0
    context_count = len(list(context_dir.glob("*.yaml"))) if context_dir.exists() else 0

    # Stale count
    try:
        refresh_engine = RefreshEngine(project_root)
        report = refresh_engine.find_stale()
        stale_count = len(report.stale_entries) + len(report.stale_symbols)
    except Exception:
        stale_count = 0

    # Task count
    tasks_dir = repograph / "tasks"
    task_count = len([d for d in tasks_dir.iterdir() if d.is_dir()]) if tasks_dir.exists() else 0

    # Guard rules count
    constitution_path = repograph / "guards" / "engineering_constitution.yaml"
    rule_count = 0
    if constitution_path.exists():
        try:
            data = load_yaml(constitution_path)
            rule_count = len(data.get("rules", {}))
        except Exception:
            pass

    click.echo(f"Project: {project_root.name}")
    click.echo(f"")
    click.echo(f"Semantic Memory:")
    click.echo(f"  Entries:     {entry_count}")
    click.echo(f"  Symbols:     {symbol_count}")
    click.echo(f"  Contexts:    {context_count}")
    click.echo(f"  Stale:       {stale_count}")
    click.echo(f"")
    click.echo(f"Tasks:         {task_count}")
    click.echo(f"Guard Rules:   {rule_count}")


@main.command()
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against (default: uncommitted changes).",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="Check specific file(s) instead of git diff.",
)
@click.option(
    "--dir",
    "dirs",
    multiple=True,
    help="Check all .py files under specific directorie(s).",
)
@click.option(
    "--all",
    "scan_all",
    is_flag=True,
    help="Scan all Python files in the project (useful for legacy code audits).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    help="Write report to a file instead of stdout.",
)
@click.option(
    "--format",
    "report_format",
    type=click.Choice(["markdown", "json"], case_sensitive=False),
    default="markdown",
    help="Report format (default: markdown).",
)
def structure_check(
    since: str,
    files: tuple[str, ...],
    dirs: tuple[str, ...],
    scan_all: bool,
    output: str | None,
    report_format: str,
) -> None:
    """Check code structure.

    By default only scans files with uncommitted changes.
    Use --all to scan the entire codebase, --dir for specific directories,
    or --file to check specific files.
    """
    from pathlib import Path

    from repoctx.guards.structure_check import StructureChecker
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    # Build file list from --file and --dir
    file_list: list[str] = []
    if files:
        file_list.extend(files)
    if dirs:
        for d in dirs:
            target = project_root / d
            if target.is_dir():
                file_list.extend(
                    p.relative_to(project_root).as_posix()
                    for p in target.rglob("*.py")
                )
            else:
                click.echo(f"Warning: --dir '{d}' is not a directory, skipping.")

    checker = StructureChecker(project_root)
    violations = checker.check(
        since=since,
        files=file_list if file_list else None,
        scan_all=scan_all,
    )

    # Determine which files were actually scanned for the report
    scanned_files = file_list if file_list else []
    if scan_all:
        scanned_files = checker._collect_all_py_files()

    if output:
        report = StructureChecker.generate_report(
            violations, scanned_files, format=report_format
        )
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}")
    else:
        click.echo(StructureChecker.format_report(violations))

    if violations:
        error_count = sum(1 for v in violations if v.severity == "error")
        if error_count:
            raise click.ClickException(
                f"Structure check failed: {error_count} error(s)."
            )


@main.command(deprecated=True)
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against (default: uncommitted changes).",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="Analyze specific file(s) instead of git diff.",
)
def test_impact(since: str, files: tuple[str, ...]) -> None:
    """Show test impact of changes."""
    from repoctx.guards.test_impact import TestImpactAnalyzer
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    analyzer = TestImpactAnalyzer(project_root)
    file_list = list(files) if files else None
    result = analyzer.analyze(since=since, files=file_list)
    click.echo(TestImpactAnalyzer.format_report(result))


@main.command(deprecated=True)
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against (default: uncommitted changes).",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="Check specific file(s) instead of git diff.",
)
def legacy_check(since: str, files: tuple[str, ...]) -> None:
    """Check legacy protections."""
    from repoctx.guards.legacy_check import LegacyChecker
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    checker = LegacyChecker(project_root)
    file_list = list(files) if files else None
    violations = checker.check(since=since, files=file_list)

    click.echo(LegacyChecker.format_report(violations))
    if violations:
        raise click.ClickException("Legacy check failed.")


@main.command(deprecated=True)
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against (default: uncommitted changes).",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="Check specific file(s) instead of git diff.",
)
@click.option(
    "--dir",
    "dirs",
    multiple=True,
    help="Check all .py files under specific directorie(s).",
)
@click.option(
    "--all",
    "scan_all",
    is_flag=True,
    help="Scan all Python files in the project.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(dir_okay=False, writable=True),
    help="Write report to a file instead of stdout.",
)
def reuse_check(
    since: str,
    files: tuple[str, ...],
    dirs: tuple[str, ...],
    scan_all: bool,
    output: str | None,
) -> None:
    """Detect duplicate implementations.

    Compares new/modified functions against SymbolCards in semantic memory
    and suggests reuse opportunities.
    """
    from pathlib import Path

    from repoctx.guards.reuse_check import ReuseChecker
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    file_list: list[str] = []
    if files:
        file_list.extend(files)
    if dirs:
        for d in dirs:
            target = project_root / d
            if target.is_dir():
                file_list.extend(
                    p.relative_to(project_root).as_posix()
                    for p in target.rglob("*.py")
                )
            else:
                click.echo(f"Warning: --dir '{d}' is not a directory, skipping.")

    checker = ReuseChecker(project_root)
    suggestions = checker.check(
        since=since,
        files=file_list if file_list else None,
        scan_all=scan_all,
    )

    report = ReuseChecker.format_report(suggestions)
    if output:
        Path(output).write_text(report, encoding="utf-8")
        click.echo(f"Report written to {output}")
    else:
        click.echo(report)

    if suggestions:
        high = sum(1 for s in suggestions if s.confidence == "high")
        if high:
            raise click.ClickException(
                f"Reuse check: {high} high-confidence duplication(s) detected."
            )


@main.command(deprecated=True)
@click.option(
    "--since",
    default="HEAD",
    help="Git ref to compare against (default: uncommitted changes).",
)
@click.option(
    "--file",
    "files",
    multiple=True,
    help="Check specific file(s) instead of git diff.",
)
@click.option(
    "--dir",
    "dirs",
    multiple=True,
    help="Check all .py files under specific directorie(s).",
)
@click.option(
    "--all",
    "scan_all",
    is_flag=True,
    help="Scan all Python files in the project (structure-check only).",
)
def commit_check(
    since: str, files: tuple[str, ...], dirs: tuple[str, ...], scan_all: bool
) -> None:
    """Pre-commit gate: all checks in one."""
    from pathlib import Path

    from repoctx.guards.commit_check import CommitChecker
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    file_list: list[str] = []
    if files:
        file_list.extend(files)
    if dirs:
        for d in dirs:
            target = project_root / d
            if target.is_dir():
                file_list.extend(
                    p.relative_to(project_root).as_posix()
                    for p in target.rglob("*.py")
                )
            else:
                click.echo(f"Warning: --dir '{d}' is not a directory, skipping.")

    checker = CommitChecker(project_root)
    result = checker.check(
        since=since,
        files=file_list if file_list else None,
        scan_all=scan_all,
    )

    click.echo(CommitChecker.format_report(result))
    if not result["passed"]:
        raise click.ClickException("Commit check failed. Fix violations before committing.")


# ---------------------------------------------------------------------------
# Experiment Agent
# ---------------------------------------------------------------------------

@main.group()
def exp() -> None:
    """Experiment management commands."""
    pass


@exp.command("init")
@click.option("--entry", required=True, help="Path to the experiment entry script.")
@click.option("--name", required=True, help="Unique contract identifier.")
@click.option("--symbol", default="main", help="Entry function name (default: main).")
@click.option("--purpose", default="", help="Short description of the experiment.")
def exp_init(entry: str, name: str, symbol: str, purpose: str) -> None:
    """Initialize an experiment contract."""
    from repoctx.experiments.contract import ContractEngine, ContractError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = ContractEngine(project_root)
    try:
        contract = engine.create(
            entry_file=entry,
            contract_id=name,
            entry_symbol=symbol,
            purpose=purpose,
        )
    except ContractError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"✅ Experiment contract created: {contract.id}")
    click.echo(f"   Entry file: {contract.entry_file}")
    click.echo(f"   Entry symbol: {contract.entry_symbol}")
    click.echo(f"   Purpose: {contract.contract.purpose}")
    if contract.contract.cli_args:
        click.echo(f"   Detected CLI args: {', '.join(a.name for a in contract.contract.cli_args)}")
    click.echo(f"\nEdit with: repoctx exp edit {contract.id}")


@exp.command("edit")
@click.argument("contract_id")
def exp_edit(contract_id: str) -> None:
    """Open an experiment contract in your default editor."""
    import os
    import subprocess

    from repoctx.experiments.contract import ContractEngine, ContractError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = ContractEngine(project_root)
    try:
        path = engine._contract_path(contract_id)
    except ContractError as e:
        raise click.ClickException(str(e)) from e

    if not path.exists():
        raise click.ClickException(f"Contract '{contract_id}' not found.")

    editor = os.environ.get("EDITOR", "vi")
    click.echo(f"Opening {path} in {editor}...")
    subprocess.call([editor, str(path)])


@exp.command("check")
@click.argument("contract_id")
def exp_check(contract_id: str) -> None:
    """Run pre-experiment checks."""
    click.echo(f"[repoctx exp check] contract={contract_id}. Not yet implemented.")


@exp.command("run")
@click.argument("cmd")
@click.option("--contract", required=True, help="Contract ID to use.")
@click.option("--output-dir", default=None, help="Override output directory.")
@click.option("--notify", is_flag=True, default=False, help="Send Slack notification on completion.")
def exp_run(cmd: str, contract: str, output_dir: str | None, notify: bool) -> None:
    """Run an experiment in the background with monitoring.

    Example:
        repoctx exp run "python train.py --epochs 50" --contract my_exp --notify
    """
    from pathlib import Path

    from repoctx.experiments.contract import ContractEngine, ContractError
    from repoctx.experiments.monitor import ExperimentMonitor
    from repoctx.experiments.runner import ExperimentRunner, RunnerError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    # Load contract
    contract_engine = ContractEngine(project_root)
    try:
        exp_contract = contract_engine.load(contract)
    except ContractError as e:
        raise click.ClickException(str(e)) from e

    # Infer output_dir
    if output_dir:
        out = Path(output_dir)
    else:
        # Try to infer from cmd or contract defaults
        out = _infer_output_dir(cmd, exp_contract)
        out = project_root / out
    out.mkdir(parents=True, exist_ok=True)

    # Launch via nohup
    runner = ExperimentRunner(project_root)
    try:
        pid, nohup_path = runner.nohup_start(cmd, contract_id=contract, output_dir=out)
    except RunnerError as e:
        raise click.ClickException(str(e)) from e

    # Start monitor thread
    monitor = ExperimentMonitor(
        contract=exp_contract,
        nohup_path=nohup_path,
        pid=pid,
        output_dir=out,
        project_root=project_root,
        cmd=cmd,
        notify=notify,
    )
    monitor.start()

    click.echo(f"🚀 Experiment launched: {contract}")
    click.echo(f"   PID: {pid}")
    click.echo(f"   Nohup log: {nohup_path}")
    click.echo(f"   Output dir: {out}")
    click.echo(f"   Monitor: started (background)")
    if notify:
        click.echo("   You will receive a notification when it completes.")


def _infer_output_dir(cmd: str, contract: "ExperimentContract") -> Path:
    """Infer output directory from --output_dir in cmd or contract default."""
    import re
    from pathlib import Path

    m = re.search(r"--output[-_]?dir\s+(\S+)", cmd)
    if m:
        return Path(m.group(1))
    for arg in contract.contract.cli_args:
        if "output" in arg.name.lower() and arg.default:
            return Path(arg.default)
    return Path(".")


@exp.command("history")
@click.argument("contract_id")
@click.option("--status", default=None, help="Filter by status (e.g. completed, failed).")
@click.option("--limit", default=20, help="Max number of runs to show.")
def exp_history(contract_id: str, status: str | None, limit: int) -> None:
    """Show run history for a contract."""
    from repoctx.experiments.history import HistoryEngine, HistoryError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = HistoryEngine(project_root)
    try:
        entries = engine.list_runs(contract_id=contract_id, status_filter=status, limit=limit)
    except HistoryError as e:
        raise click.ClickException(str(e)) from e

    if not entries:
        click.echo(f"No runs found for contract '{contract_id}'.")
        return

    click.echo(f"{'Run ID':<40} {'Status':<12} {'Started':<16} {'Duration':<10} {'Files'}")
    click.echo("-" * 90)
    for e in entries:
        click.echo(f"{e.run_id:<40} {e.status:<12} {e.started_at:<16} {e.duration:<10} {e.result_count}")


@exp.command("summarize")
@click.argument("run_id")
def exp_summarize(run_id: str) -> None:
    """Summarize a completed experiment run."""
    from repoctx.experiments.history import HistoryEngine, HistoryError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = HistoryEngine(project_root)
    try:
        run = engine.get_run(run_id)
    except HistoryError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"# Run Summary: {run.id}")
    click.echo(f"Contract: {run.contract_id}")
    click.echo(f"Command: {run.cmd}")
    click.echo(f"PID: {run.pid}")
    click.echo(f"Status: {run.light_analysis.status}")
    click.echo(f"Duration: {_fmt_dur(run.duration_seconds)}")
    click.echo(f"Started: {run.started_at or 'N/A'}")
    click.echo(f"Ended: {run.ended_at or 'N/A'}")
    click.echo(f"Result files: {len(run.result_files)}")
    for rf in run.result_files:
        click.echo(f"  - {rf.path} ({rf.source})")
    click.echo("")
    click.echo("## LLM Summary")
    click.echo(run.llm_analysis.summary or "(none)")


def _fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"


@exp.command("ps")
def exp_ps() -> None:
    """List currently running experiments."""
    import os

    from repoctx.experiments.history import HistoryEngine
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = HistoryEngine(project_root)
    runs = engine.list_runs(status_filter="running", limit=100)

    active: list[tuple[str, str, int]] = []
    for entry in runs:
        # Try to validate PID is still alive
        try:
            run = engine.get_run(entry.run_id)
        except Exception:
            continue
        pid = run.pid
        if pid is None:
            continue
        try:
            os.kill(pid, 0)
            active.append((entry.run_id, entry.contract_id, pid))
        except (OSError, ProcessLookupError):
            pass

    if not active:
        click.echo("No running experiments.")
        return

    click.echo(f"{'Run ID':<40} {'Contract':<20} {'PID'}")
    click.echo("-" * 70)
    for run_id, cid, pid in active:
        click.echo(f"{run_id:<40} {cid:<20} {pid}")


@exp.command("logs")
@click.argument("contract_id")
@click.option("--lines", default=50, help="Number of tail lines to show.")
def exp_logs(contract_id: str, lines: int) -> None:
    """Tail the nohup log of the latest run for a contract."""
    from repoctx.experiments.history import HistoryEngine, HistoryError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = HistoryEngine(project_root)
    runs = engine.list_runs(contract_id=contract_id, limit=1)
    if not runs:
        raise click.ClickException(f"No runs found for contract '{contract_id}'.")

    try:
        run = engine.get_run(runs[0].run_id)
    except HistoryError as e:
        raise click.ClickException(str(e)) from e

    nohup_path = run.nohup_path
    if not nohup_path:
        raise click.ClickException("No nohup log recorded for this run.")

    from pathlib import Path
    path = Path(nohup_path)
    if not path.exists():
        raise click.ClickException(f"Nohup log not found: {path}")

    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            all_lines = f.readlines()
            tail = all_lines[-lines:]
    except OSError as e:
        raise click.ClickException(f"Failed to read log: {e}") from e

    click.echo(f"--- Last {len(tail)} lines of {path} ---")
    click.echo("".join(tail))


@exp.command("diagnose")
@click.argument("contract_id")
@click.option("--compare-recent-success-num", default=1, help="Compare against N recent successful runs.")
def exp_diagnose(contract_id: str, compare_recent_success_num: int) -> None:
    """Diagnose an experiment contract by comparing recent runs."""
    from repoctx.experiments.diagnose import DiagnoseEngine, DiagnoseError
    from repoctx.utils.project import find_project_root

    try:
        project_root = find_project_root()
    except Exception as e:
        raise click.ClickException(
            f"{e}\n\nRun 'repoctx init' in your project root first."
        ) from e

    engine = DiagnoseEngine(project_root)
    try:
        report = engine.diagnose(
            contract_id=contract_id,
            compare_recent_success_num=compare_recent_success_num,
        )
    except DiagnoseError as e:
        raise click.ClickException(str(e)) from e

    click.echo(report.format())


if __name__ == "__main__":
    main()
