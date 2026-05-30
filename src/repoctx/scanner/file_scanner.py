"""File system scanning utilities."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from repoctx.models import RepoCtxConfig


def should_exclude(
    file_path: Path,
    exclude_patterns: list[str],
    project_root: Path,
) -> bool:
    """Check if a file should be excluded based on patterns.

    Patterns support glob syntax and are matched against both the
    relative path and the file name.
    """
    rel_path = file_path.relative_to(project_root).as_posix()
    name = file_path.name

    for pattern in exclude_patterns:
        if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(name, pattern):
            return True
    return False


def scan_files(config: RepoCtxConfig, project_root: Path) -> list[Path]:
    """Scan project directories and return a list of files to index.

    Args:
        config: Project configuration containing scan_paths and exclude_paths.
        project_root: Absolute path to the project root.

    Returns:
        Sorted list of file paths to be indexed.
    """
    files: list[Path] = []
    exclude_patterns = config.exclude_paths

    for scan_path_str in config.scan_paths:
        scan_path = project_root / scan_path_str
        if not scan_path.exists():
            continue

        if scan_path.is_file():
            if not should_exclude(scan_path, exclude_patterns, project_root):
                files.append(scan_path.resolve())
            continue

        for file_path in scan_path.rglob("*"):
            if not file_path.is_file():
                continue
            if should_exclude(file_path, exclude_patterns, project_root):
                continue
            files.append(file_path.resolve())

    # Deduplicate and sort
    unique = sorted(set(files), key=lambda p: p.as_posix())
    return unique
