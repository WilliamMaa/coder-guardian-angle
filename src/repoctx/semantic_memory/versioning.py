"""Versioning utilities for semantic memory cards.

Computes content hashes and git metadata so cards can be tracked for staleness.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from repoctx.tracer.base import CallNode


def compute_file_hash(path: Path) -> str:
    """Return SHA256 hex digest of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get_git_commit(project_root: Path) -> str:
    """Return current git commit short SHA or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def compute_dependency_hash(node: CallNode) -> str:
    """Return a short hash of immediate downstream symbol references."""
    deps = sorted(
        f"{child.source.file}::{child.symbol}"
        for child in node.children
        if not child.is_external
    )
    if not deps:
        return ""
    content = "\n".join(deps)
    return hashlib.sha256(content.encode()).hexdigest()[:16]
