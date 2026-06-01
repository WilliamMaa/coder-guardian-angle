"""Test impact analyzer: find which tests should be run/added for current changes.

Uses semantic memory cards to map changed files to affected entry points
and their related tests.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from repoctx.guards.base import get_git_diff_files
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.guards")


class TestImpactAnalyzer:
    """Analyze test impact of current code changes."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def analyze(
        self,
        since: str = "HEAD",
        files: list[str] | None = None,
    ) -> dict[str, Any]:
        """Analyze which tests are impacted by current changes.

        Args:
            since: Git ref to diff against.
            files: Override file list instead of git diff.

        Returns:
            Dictionary with affected entries, related tests, and gaps.
        """
        if files is None:
            files = get_git_diff_files(self.project_root, since=since)

        logger.info("Test-impact analyzing %d changed file(s)", len(files))

        # Load all entry cards and context packs
        entries = self._load_all_entries()
        context_packs = self._load_all_context_packs()

        # Find affected entries (direct or indirect)
        affected_entries: list[dict[str, Any]] = []
        for entry in entries:
            entry_file = entry.get("source", {}).get("file", "")
            if entry_file in files:
                affected_entries.append(entry)
                continue
            downstream = entry.get("main_downstream", [])
            for ds in downstream:
                ds_file = self._symbol_id_to_file(ds)
                if ds_file and ds_file in files:
                    affected_entries.append(entry)
                    break

        # Collect related tests from affected entries and their context packs
        related_tests: set[str] = set()
        for entry in affected_entries:
            entry_symbol = entry.get("source", {}).get("symbol", "")
            # Context pack id is typically "context.<symbol>"
            cp = context_packs.get(f"context.{entry_symbol}")
            if cp:
                for t in cp.get("related_tests", []):
                    related_tests.add(t)

        # Identify gaps: changed files with no semantic memory coverage
        covered_files = set()
        for entry in entries:
            covered_files.add(entry.get("source", {}).get("file", ""))
        uncovered = [f for f in files if f not in covered_files and f.endswith(".py")]

        return {
            "changed_files": files,
            "affected_entries": [e.get("id") for e in affected_entries],
            "related_tests": sorted(related_tests),
            "uncovered_files": uncovered,
            "summary": (
                f"{len(files)} file(s) changed, "
                f"{len(affected_entries)} entry(s) affected, "
                f"{len(related_tests)} test category(ies) identified, "
                f"{len(uncovered)} file(s) without semantic memory coverage."
            ),
        }

    def _load_all_entries(self) -> list[dict[str, Any]]:
        """Load all entry cards from disk."""
        from repoctx.utils.project import get_repograph_dir

        entries_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "entries"
        if not entries_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in entries_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                if data and data.get("card_type") == "entry":
                    results.append(data)
            except Exception:
                continue
        return results

    def _load_all_context_packs(self) -> dict[str, dict[str, Any]]:
        """Load all context packs keyed by their id."""
        from repoctx.utils.project import get_repograph_dir

        cp_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "context_packs"
        if not cp_dir.exists():
            return {}
        results: dict[str, dict[str, Any]] = {}
        for path in cp_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                if data and data.get("id"):
                    results[data["id"]] = data
            except Exception:
                continue
        return results

    @staticmethod
    def _symbol_id_to_file(symbol_id: str) -> str | None:
        """Best-effort reverse mapping from symbol id like 'module.function' to file path."""
        # This is inherently heuristic — we don't have an index yet.
        # For MVP, assume module path mirrors file path.
        if "." not in symbol_id:
            return None
        parts = symbol_id.split(".")
        # Try path/to/module.py::function
        candidate = "/".join(parts[:-1]) + ".py"
        return candidate

    @staticmethod
    def format_report(result: dict[str, Any]) -> str:
        """Return a human-readable report string."""
        lines = ["Test Impact Analysis", "=" * 40, ""]
        lines.append(result["summary"])
        lines.append("")

        if result["affected_entries"]:
            lines.append("Affected Entries:")
            for e in result["affected_entries"]:
                lines.append(f"  - {e}")
            lines.append("")

        if result["related_tests"]:
            lines.append("Related Tests (run these):")
            for t in result["related_tests"]:
                lines.append(f"  - {t}")
            lines.append("")

        if result["uncovered_files"]:
            lines.append("Uncovered Files (no semantic memory — consider digesting):")
            for f in result["uncovered_files"]:
                lines.append(f"  - {f}")
            lines.append("")

        return "\n".join(lines)
