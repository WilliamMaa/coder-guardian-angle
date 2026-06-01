"""Unified audit engine: one command to digest, check, and report.

``repoctx audit`` is the single entry-point for code quality audits.
It discovers files, optionally digests missing ones, runs all guard
modules, and produces a unified report.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repoctx.guards.base import get_git_diff_files
from repoctx.guards.legacy_check import LegacyChecker
from repoctx.guards.reuse_check import ReuseChecker
from repoctx.guards.structure_check import StructureChecker
from repoctx.semantic_memory.engine import SemanticDigestEngine
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import dump_yaml

logger = logging.getLogger("repoctx.audit")


@dataclass
class AuditResult:
    """Result of a unified audit run."""

    files_scanned: list[str] = field(default_factory=list)
    files_missing_digest: list[str] = field(default_factory=list)
    structure_violations: list[Any] = field(default_factory=list)
    reuse_suggestions: list[Any] = field(default_factory=list)
    legacy_violations: list[Any] = field(default_factory=list)
    auto_digest_attempted: bool = False
    auto_digest_errors: list[str] = field(default_factory=list)
    deep_analysis: list[str] = field(default_factory=list)


class AuditEngine:
    """One-shot auditor for an entire project or a subset of files."""

    _NOISE_DIRS: set[str] = {
        ".venv",
        "venv",
        "__pycache__",
        ".git",
        ".repoctx",
        ".repograph",
        "node_modules",
        ".tox",
        ".pytest_cache",
        "dist",
        "build",
        "*.egg-info",
        "migrations",
    }

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()

    def audit(
        self,
        files: list[str] | None = None,
        scan_all: bool = False,
        auto_digest: bool = False,
        since: str = "HEAD",
    ) -> AuditResult:
        """Run the unified audit.

        Args:
            files: Explicit file paths to audit.
            scan_all: Audit every Python file under the project.
            auto_digest: Automatically digest files that lack semantic memory.
            since: Git ref when using diff mode (default: uncommitted changes).

        Returns:
            :class:`AuditResult` containing all findings.
        """
        # ------------------------------------------------------------------
        # 1. Determine file list
        # ------------------------------------------------------------------
        if scan_all:
            py_files = self._collect_all_py_files()
        elif files:
            py_files = [f for f in files if f.endswith(".py")]
        else:
            py_files = [
                f for f in get_git_diff_files(self.project_root, since=since)
                if f.endswith(".py")
            ]

        logger.info("Audit scope: %d Python file(s)", len(py_files))

        # ------------------------------------------------------------------
        # 2. Find files missing semantic memory
        # ------------------------------------------------------------------
        missing = self._find_missing_digest(py_files)
        logger.info("Missing semantic memory: %d file(s)", len(missing))

        # ------------------------------------------------------------------
        # 3. Auto-digest if requested
        # ------------------------------------------------------------------
        digest_errors: list[str] = []
        if auto_digest and missing:
            digest_errors = self._auto_digest(missing)

        # ------------------------------------------------------------------
        # 4. Run all guards
        # ------------------------------------------------------------------
        structure = StructureChecker(self.project_root).check(files=py_files)
        reuse = ReuseChecker(self.project_root).check(files=py_files)
        legacy = LegacyChecker(self.project_root).check(files=py_files)

        return AuditResult(
            files_scanned=py_files,
            files_missing_digest=missing,
            structure_violations=structure,
            reuse_suggestions=reuse,
            legacy_violations=legacy,
            auto_digest_attempted=auto_digest and bool(missing),
            auto_digest_errors=digest_errors,
        )

    def _collect_all_py_files(self) -> list[str]:
        """Return every ``.py`` file under the project root, excluding noise."""
        files: list[str] = []
        for path in self.project_root.rglob("*.py"):
            if any(part in self._NOISE_DIRS for part in path.parts):
                continue
            files.append(path.relative_to(self.project_root).as_posix())
        return sorted(files)

    def _find_missing_digest(self, py_files: list[str]) -> list[str]:
        """Return files in *py_files* that have no corresponding entry card."""
        from repoctx.utils.project import get_repograph_dir

        entries_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "entries"
        if not entries_dir.exists():
            return py_files

        # Build a set of files that have at least one entry card
        covered: set[str] = set()
        for path in entries_dir.glob("*.yaml"):
            try:
                from repoctx.utils.yaml_io import load_yaml
                data = load_yaml(path)
                src_file = data.get("source", {}).get("file", "")
                if src_file:
                    covered.add(src_file)
            except Exception:
                continue

        return [f for f in py_files if f not in covered]

    def _auto_digest(self, files: list[str]) -> list[str]:
        """Digest files that lack semantic memory. Returns list of error messages."""
        errors: list[str] = []
        try:
            engine = SemanticDigestEngine(self.project_root)
        except Exception as e:
            return [f"Failed to initialize digest engine: {e}"]

        for rel_path in files:
            logger.info("Auto-digesting %s", rel_path)
            try:
                # Guess top-level function names from AST
                symbols = self._extract_top_level_functions(rel_path)
                if symbols:
                    engine.digest(rel_path, target_symbols=symbols, max_depth=2)
                else:
                    engine.digest(rel_path, max_depth=2)
            except Exception as e:
                errors.append(f"{rel_path}: {e}")
        return errors

    def _extract_top_level_functions(self, rel_path: str) -> list[str] | None:
        """Return top-level function names from a Python file."""
        abs_path = self.project_root / rel_path
        try:
            source = abs_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            return None

        names = [
            node.name
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        return names if names else None

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    @staticmethod
    def generate_report(result: AuditResult) -> str:
        """Generate a unified Markdown report."""
        now = datetime.now(timezone.utc).isoformat()
        total_hard = len(
            [v for v in result.structure_violations + result.legacy_violations if v.severity == "error"]
        )
        total_warn = len(
            [v for v in result.structure_violations + result.legacy_violations if v.severity == "warning"]
        )

        lines = [
            "# RepoCtx Audit Report",
            "",
            f"**Generated:** {now}",
            f"**Files scanned:** {len(result.files_scanned)}",
            f"**Errors:** {total_hard}  |  **Warnings:** {total_warn}  |  **Reuse suggestions:** {len(result.reuse_suggestions)}",
            "",
        ]

        if result.files_missing_digest:
            lines.append("## ⚠️ Files Missing Semantic Memory")
            lines.append("")
            lines.append("The following files have not been digested yet.")
            if result.auto_digest_attempted:
                lines.append("Auto-digest was attempted.")
                if result.auto_digest_errors:
                    lines.append("")
                    lines.append("**Digest errors:**")
                    for err in result.auto_digest_errors:
                        lines.append(f"- {err}")
            else:
                lines.append("Run with `--digest` to auto-digest them.")
            lines.append("")
            for f in result.files_missing_digest:
                lines.append(f"- `{f}`")
            lines.append("")
            lines.append("---")
            lines.append("")

        # Structure
        lines.append("## Structure Check")
        lines.append("")
        if result.structure_violations:
            lines.append(f"**{len(result.structure_violations)} violation(s)**")
            lines.append("")
            for v in result.structure_violations:
                lines.append(v.format())
                lines.append("")
        else:
            lines.append("✅ No structural violations.")
        lines.append("")

        # Reuse
        lines.append("## Reuse Check")
        lines.append("")
        if result.reuse_suggestions:
            lines.append(f"**{len(result.reuse_suggestions)} suggestion(s)**")
            lines.append("")
            for s in result.reuse_suggestions:
                lines.append(s.format())
                lines.append("")
        else:
            lines.append("✅ No duplicate implementations detected.")
        lines.append("")

        # Legacy
        lines.append("## Legacy Check")
        lines.append("")
        if result.legacy_violations:
            lines.append(f"**{len(result.legacy_violations)} violation(s)**")
            lines.append("")
            for v in result.legacy_violations:
                lines.append(v.format())
                lines.append("")
        else:
            lines.append("✅ No protected entities violated.")
        lines.append("")

        # Deep analysis
        if result.deep_analysis:
            lines.append("## Deep Analysis (LLM)")
            lines.append("")
            for block in result.deep_analysis:
                lines.append(block)
                lines.append("")
            lines.append("")

        # Summary
        if total_hard == 0 and not result.legacy_violations:
            lines.append("---")
            lines.append("")
            lines.append("🟢 **Audit passed.** No hard blockers.")
        else:
            lines.append("---")
            lines.append("")
            lines.append(f"🔴 **Audit failed.** {total_hard} hard error(s) must be fixed.")

        return "\n".join(lines)
