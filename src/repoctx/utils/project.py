"""Project root discovery utilities."""

from __future__ import annotations

from pathlib import Path


class ProjectRootError(Exception):
    """Raised when project root cannot be found."""

    pass


def get_repograph_dir(project_root: Path | str | None = None) -> Path:
    """Return the repograph directory for the current project.

    The path can be overridden via the ``REPOCTX_REPOGRAPH_DIR`` environment
    variable (used primarily in tests to avoid polluting ``~/.repoctx/``).

    By default, semantic memory and guard data live under the user's home
    directory to avoid gitignore visibility issues::

        ~/.repoctx/<project_name>/.repograph/

    The project name is read from ``.repoctx.yaml``.

    Args:
        project_root: Project root directory. If *None*, discovered automatically.

    Returns:
        Absolute path to the project's ``.repograph/`` directory.

    Raises:
        ProjectRootError: If the project config cannot be found or read.
    """
    env_dir = __import__("os").environ.get("REPOCTX_REPOGRAPH_DIR")
    if env_dir:
        return Path(env_dir)

    if project_root is None:
        project_root = find_project_root()
    root = Path(project_root).resolve()
    config_path = root / ".repoctx.yaml"
    if not config_path.exists():
        # Fallback for backward compatibility (e.g. tests without init)
        return root / ".repograph"

    from repoctx.utils.yaml_io import load_yaml

    try:
        config = load_yaml(config_path)
    except Exception as e:
        raise ProjectRootError(f"Failed to read project config: {e}") from e

    # Check for explicit repograph_dir in config
    custom_dir = config.get("repograph_dir")
    if custom_dir:
        custom_path = Path(custom_dir)
        if not custom_path.is_absolute():
            custom_path = root / custom_path
        return custom_path.resolve()

    project_name = config.get("project_name", root.name)
    repograph_dir = Path.home() / ".repoctx" / str(project_name) / ".repograph"
    return repograph_dir


def find_project_root(start: Path | str | None = None, marker: str = ".repoctx.yaml") -> Path:
    """Discover project root by searching upward for a marker file.

    Starting from *start* (default: current working directory), walk up the
    directory tree until *marker* is found. The directory containing the
    marker is returned as the project root.

    Args:
        start: Directory to start searching from. Defaults to cwd.
        marker: Filename that identifies the project root.

    Returns:
        Absolute path to the project root directory.

    Raises:
        ProjectRootError: If the marker file cannot be found before reaching
            the filesystem root.
    """
    start = Path.cwd() if start is None else Path(start).resolve()

    current = start
    if current.is_file():
        current = current.parent

    for parent in [current, *current.parents]:
        candidate = parent / marker
        if candidate.exists():
            return parent.resolve()

    raise ProjectRootError(
        f"Could not find project root: '{marker}' not found in "
        f"any parent directory of {start}"
    )
