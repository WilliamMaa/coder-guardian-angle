"""Legacy checker: protect protected semantic entities from accidental modification.

Reads ``.repograph/legacy/protected_entities.yaml`` and flags any git diff
that touches listed files, functions, or modules.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from repoctx.guards.base import GuardViolation, get_git_diff_files, load_protected_entities

logger = logging.getLogger("repoctx.guards")


class LegacyChecker:
    """Check whether current changes violate legacy protections."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.config = load_protected_entities(project_root)

    def check(
        self,
        since: str = "HEAD",
        files: list[str] | None = None,
    ) -> list[GuardViolation]:
        """Run legacy protection checks.

        Args:
            since: Git ref to diff against.
            files: Override file list instead of git diff.

        Returns:
            List of violations (protected entities touched).
        """
        if files is None:
            files = get_git_diff_files(self.project_root, since=since)

        entities = self.config.get("entities", [])
        if not entities:
            logger.info("No protected entities configured.")

        violations: list[GuardViolation] = []
        for changed_file in files:
            for entity in entities:
                match = self._match(changed_file, entity)
                if match:
                    violations.append(
                        GuardViolation(
                            rule_id="legacy_protection",
                            severity="error",
                            file=changed_file,
                            line=0,
                            message=f"Modified protected entity: {entity.get('name', entity)} "
                            f"({entity.get('reason', 'no reason given')})",
                            symbol=entity.get("symbol", ""),
                        )
                    )

        return violations

    def _match(self, changed_file: str, entity: dict[str, Any]) -> bool:
        """Return True if *changed_file* matches the protected *entity*."""
        # Entity can specify: file, module, symbol, or pattern
        entity_file = entity.get("file")
        if entity_file:
            if changed_file == entity_file or changed_file.startswith(
                entity_file.rstrip("/") + "/"
            ):
                return True

        entity_module = entity.get("module")
        if entity_module:
            module_path = entity_module.replace(".", "/")
            if changed_file.startswith(module_path) or changed_file.replace("/", ".").startswith(
                entity_module
            ):
                return True

        entity_pattern = entity.get("pattern")
        if entity_pattern:
            import re

            if re.search(entity_pattern, changed_file):
                return True

        return False

    @staticmethod
    def format_report(violations: list[GuardViolation]) -> str:
        if not violations:
            return "Legacy check passed. No protected entities violated."

        lines = [f"Legacy check: {len(violations)} violation(s) found.\n"]
        for v in violations:
            lines.append(v.format())
        return "\n".join(lines)
