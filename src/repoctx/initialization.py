"""Project initialization logic for repoctx.

Creates the ``.repoctx.yaml`` marker file and the full ``.repograph/``
directory tree under ``~/.repoctx/<project_name>/`` expected by the
Semantic Memory & Engineering Guard system.
"""

from __future__ import annotations

from pathlib import Path

from repoctx.models import ModuleDefinition, RepoCtxConfig
from repoctx.utils.yaml_io import dump_yaml


class InitializationError(Exception):
    """Raised when project initialization fails."""

    pass


# Full directory tree under .repograph/ (relative to .repograph/)
_REPGRAPH_DIRECTORIES: list[str] = [
    "semantic_memory/entries",
    "semantic_memory/paths",
    "semantic_memory/symbols",
    "semantic_memory/flows",
    "semantic_memory/context_packs",
    "semantic_memory/versions",
    "tasks",
    "guards",
    "legacy",
    "tests",
    "experiments/runs",
    "experiments/summaries",
    "experiments/environment_notes",
    "experiments/failure_modes",
    "experiments/design_specs",
    "reports/commit_checks",
    "reports/semantic_diffs",
    "reports/experiment_summaries",
]

# Default stub YAML files created under .repograph/ (only if missing)
_DEFAULT_STUB_FILES: dict[str, object] = {
    "guards/engineering_constitution.yaml": {
        "principles": [
            "Project understanding must be persistent.",
            "Entry points are the natural starting point.",
            "Semantic memory is the source of truth.",
            "Semantic memory must be versioned and refreshable.",
            "Guards are built on semantic memory, not path rules.",
            "Legacy core is production asset.",
            "Unexpected experiment results require dual-track diagnosis.",
        ],
        "rules": {
            "no_underscore_functions": {
                "enabled": True,
                "severity": "error",
                "description": "Public functions must not start with a single underscore.",
            },
            "mandatory_docstring": {
                "enabled": True,
                "severity": "error",
                "description": "Every function must have a docstring.",
            },
            "no_getattr_fallback": {
                "enabled": True,
                "severity": "error",
                "description": "getattr() must not be called with a default fallback value.",
            },
            "exception_logging": {
                "enabled": False,
                "severity": "warning",
                "description": "Except blocks should log the exception.",
            },
            "no_silent_fallback": {
                "enabled": False,
                "severity": "error",
                "description": "Functions must not silently return None on error without logging.",
            },
            "views_only_entries": {
                "enabled": False,
                "severity": "error",
                "description": "View files must only contain registered entry functions. Helpers must live in dedicated modules.",
                "view_file_patterns": [
                    "**/views.py",
                    "**/view_*.py",
                    "**/*_view.py",
                    "**/*_views.py",
                ],
            },
        },
    },
    "guards/structure_rules.yaml": {"rules": []},
    "guards/test_rules.yaml": {"rules": []},
    "guards/legacy_rules.yaml": {"rules": []},
    "legacy/protected_entities.yaml": {
        "entities": [
            # Example format (remove or adapt for your project):
            # {
            #   "name": "Billing Core",
            #   "file": "legacy/billing/core.py",
            #   "symbol": "calculate_invoice",
            #   "reason": "Production-critical billing logic",
            # },
        ]
    },
    "legacy/reusable_capabilities.yaml": {"capabilities": []},
    "legacy/public_surfaces.yaml": {"surfaces": []},
    "legacy/core_contracts.yaml": {"contracts": []},
    "tests/behavior_test_map.yaml": {"behaviors": []},
    "tests/test_impact_map.yaml": {"impacts": []},
}


def init_project(
    project_root: Path | str,
    *,
    project_name: str = "my-project",
    language: str = "python",
    framework: str = "django",
    force: bool = False,
) -> list[Path]:
    """Initialize a project for repoctx.

    Creates:
        - ``.repoctx.yaml`` configuration / marker file
        - ``.repograph/`` directory tree under ``~/.repoctx/<project_name>/``
        - Default stub YAML files for guards, legacy, and tests

    Args:
        project_root: Target project directory.
        project_name: Value for the ``project_name`` field in ``.repoctx.yaml``.
        language: Primary programming language.
        framework: Primary web / application framework.
        force: If *True*, overwrite an existing ``.repoctx.yaml``.

    Returns:
        List of paths that were created (or already existed for directories).

    Raises:
        InitializationError: If ``.repoctx.yaml`` already exists and *force* is
            *False*.
    """
    root = Path(project_root).resolve()
    created: list[Path] = []

    # ------------------------------------------------------------------
    # 1. .repoctx.yaml
    # ------------------------------------------------------------------
    config_path = root / ".repoctx.yaml"
    if config_path.exists() and not force:
        raise InitializationError(
            f"Project already initialized: {config_path} exists. "
            "Use --force to overwrite."
        )

    config = RepoCtxConfig(
        project_name=project_name,
        language=language,
        framework=framework,
        modules=[
            ModuleDefinition(name="backend", path="backend", type="backend"),
            ModuleDefinition(name="frontend", path="frontend", type="frontend"),
        ],
    )
    dump_yaml(config.model_dump(mode="json", exclude_none=True), config_path)
    created.append(config_path)

    # ------------------------------------------------------------------
    # 2. .repograph/ directories (under ~/.repoctx/<project_name>/)
    # ------------------------------------------------------------------
    from repoctx.utils.project import get_repograph_dir

    repograph_dir = get_repograph_dir(root)
    for rel in _REPGRAPH_DIRECTORIES:
        dir_path = repograph_dir / rel
        dir_path.mkdir(parents=True, exist_ok=True)
        created.append(dir_path)

    # ------------------------------------------------------------------
    # 3. Default stub YAML files (skip if already present)
    # ------------------------------------------------------------------
    for rel_path, data in _DEFAULT_STUB_FILES.items():
        file_path = repograph_dir / rel_path
        if not file_path.exists():
            dump_yaml(data, file_path)
            created.append(file_path)

    return created
