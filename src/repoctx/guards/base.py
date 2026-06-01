"""Shared utilities for all guard modules."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repoctx.utils.yaml_io import load_yaml


@dataclass
class GuardViolation:
    """A single guard violation report."""

    rule_id: str
    severity: str  # error | warning | info
    file: str
    line: int
    message: str
    symbol: str = ""

    def format(self) -> str:
        sym = f" [{self.symbol}]" if self.symbol else ""
        return (
            f"  [{self.severity.upper():7}] {self.file}:{self.line}{sym}\n"
            f"           {self.message} ({self.rule_id})"
        )


def get_git_diff_files(project_root: Path, since: str = "HEAD") -> list[str]:
    """Return a list of file paths changed since *since* (default: uncommitted changes).

    If *since* is ``"HEAD"``, returns files with uncommitted changes.
    Otherwise runs ``git diff --name-only since..HEAD``.
    """
    try:
        if since == "HEAD":
            result = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                ["git", "diff", "--name-only", f"{since}..HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except FileNotFoundError:
        return []


def get_git_diff_new_files(project_root: Path, since: str = "HEAD") -> list[str]:
    """Return only **newly added** files since *since*.

    Uses ``git diff --diff-filter=A --name-only``.
    """
    try:
        if since == "HEAD":
            result = subprocess.run(
                ["git", "diff", "--diff-filter=A", "--name-only", "HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            result = subprocess.run(
                ["git", "diff", "--diff-filter=A", "--name-only", f"{since}..HEAD"],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]
    except FileNotFoundError:
        return []


def load_rules(project_root: Path) -> dict[str, Any]:
    """Load engineering constitution rules from ``.repograph/guards/engineering_constitution.yaml``."""
    from repoctx.utils.project import get_repograph_dir

    path = get_repograph_dir(project_root) / "guards" / "engineering_constitution.yaml"
    if not path.exists():
        return {}
    try:
        data = load_yaml(path)
        return data.get("rules", {})
    except Exception:
        return {}


def load_protected_entities(project_root: Path) -> dict[str, Any]:
    """Load protected entities from ``.repograph/legacy/protected_entities.yaml``."""
    from repoctx.utils.project import get_repograph_dir

    path = get_repograph_dir(project_root) / "legacy" / "protected_entities.yaml"
    if not path.exists():
        return {}
    try:
        data = load_yaml(path)
        return data
    except Exception:
        return {}
