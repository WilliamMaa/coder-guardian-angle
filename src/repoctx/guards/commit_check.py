"""Unified pre-commit gate: structure-check + test-impact + legacy-check."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repoctx.guards.base import GuardViolation
from repoctx.guards.legacy_check import LegacyChecker
from repoctx.guards.structure_check import StructureChecker
from repoctx.guards.test_impact import TestImpactAnalyzer


class CommitChecker:
    """Run all guards and produce a unified commit gate report."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.structure = StructureChecker(project_root)
        self.test_impact = TestImpactAnalyzer(project_root)
        self.legacy = LegacyChecker(project_root)

    def check(
        self,
        since: str = "HEAD",
        files: list[str] | None = None,
        scan_all: bool = False,
    ) -> dict[str, Any]:
        """Run all guard checks and return aggregated results.

        Returns:
            Dict with keys: structure, test_impact, legacy, passed, summary.
        """
        structure_violations = self.structure.check(
            since=since, files=files, scan_all=scan_all
        )
        test_impact_result = self.test_impact.analyze(since=since, files=files)
        legacy_violations = self.legacy.check(since=since, files=files)

        passed = len(structure_violations) == 0 and len(legacy_violations) == 0

        return {
            "structure": structure_violations,
            "test_impact": test_impact_result,
            "legacy": legacy_violations,
            "passed": passed,
            "summary": (
                f"Structure: {len(structure_violations)} violation(s), "
                f"Legacy: {len(legacy_violations)} violation(s), "
                f"Tests: {len(test_impact_result.get('related_tests', []))} category(ies)."
            ),
        }

    @staticmethod
    def format_report(result: dict[str, Any]) -> str:
        """Return a human-readable unified report."""
        lines = ["=" * 50, "Commit Check Report", "=" * 50, ""]

        lines.append(result["summary"])
        lines.append("")

        # Structure
        lines.append(StructureChecker.format_report(result["structure"]))
        lines.append("")

        # Legacy
        lines.append(LegacyChecker.format_report(result["legacy"]))
        lines.append("")

        # Test impact
        lines.append(TestImpactAnalyzer.format_report(result["test_impact"]))
        lines.append("")

        if result["passed"]:
            lines.append("✅ All hard checks passed. Ready to commit.")
        else:
            lines.append("❌ Commit blocked. Fix violations above before committing.")

        return "\n".join(lines)
