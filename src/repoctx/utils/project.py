"""Project root discovery utilities."""

from __future__ import annotations

from pathlib import Path


class ProjectRootError(Exception):
    """Raised when project root cannot be found."""

    pass


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
