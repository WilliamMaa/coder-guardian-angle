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

    Patterns support glob syntax. They are matched against:
    - the relative file path
    - the file name
    - any directory component in the relative path
    """
    rel_path = file_path.relative_to(project_root).as_posix()
    name = file_path.name
    path_parts = rel_path.split("/")

    for pattern in exclude_patterns:
        # 1. Match full relative path
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # 2. Match file name
        if fnmatch.fnmatch(name, pattern):
            return True
        # 3. Match any directory component (e.g. "migrations" excludes anything inside migrations/)
        if "/" not in pattern and "*" not in pattern and pattern in path_parts:
            return True
        # 4. Match directory prefix for glob patterns like */migrations/*
        if pattern.startswith("*/") and pattern.endswith("/*"):
            dir_name = pattern[2:-2]  # extract "migrations" from "*/migrations/*"
            if dir_name in path_parts:
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
