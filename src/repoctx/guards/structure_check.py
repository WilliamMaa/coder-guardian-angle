"""Structure checker: scan Python files against engineering constitution.

Uses AST analysis to detect violations of coding standards defined in
``.repograph/guards/engineering_constitution.yaml``.
"""

from __future__ import annotations

import ast
import fnmatch
import logging
from pathlib import Path
from typing import Any

from repoctx.guards.base import GuardViolation, get_git_diff_files, load_rules
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.guards")


# ---------------------------------------------------------------------------
# Rule implementations
# ---------------------------------------------------------------------------


def _check_no_underscore_functions(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    line_offset: int = 0,
) -> list[GuardViolation]:
    """Disallow public functions whose names start with a single underscore.

    Magic methods (``__xxx__``) and dunder-private (``__xxx``) are allowed.
    """
    name = node.name
    if name.startswith("_") and not name.startswith("__"):
        return [
            GuardViolation(
                rule_id="no_underscore_functions",
                severity="error",
                file=file_path,
                line=node.lineno + line_offset,
                message=f"Function '{name}' starts with underscore — "
                "use descriptive public names or double-underscore for private",
                symbol=name,
            )
        ]
    return []


def _check_mandatory_docstring(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file_path: str,
    line_offset: int = 0,
) -> list[GuardViolation]:
    """Require every function to have a docstring."""
    if ast.get_docstring(node) is None:
        return [
            GuardViolation(
                rule_id="mandatory_docstring",
                severity="error",
                file=file_path,
                line=node.lineno + line_offset,
                message=f"Function '{node.name}' is missing a docstring",
                symbol=node.name,
            )
        ]
    return []


def _check_no_getattr_fallback(
    node: ast.AST,
    file_path: str,
    line_offset: int = 0,
) -> list[GuardViolation]:
    """Disallow ``getattr(obj, attr, default)`` calls that provide a default fallback.

    Using a default value with ``getattr`` silently masks missing attributes.
    """
    violations: list[GuardViolation] = []
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if isinstance(func, ast.Name) and func.id == "getattr":
            if len(child.args) >= 3:
                violations.append(
                    GuardViolation(
                        rule_id="no_getattr_fallback",
                        severity="error",
                        file=file_path,
                        line=child.lineno + line_offset,
                        message="getattr() with default fallback is not allowed",
                        symbol="",
                    )
                )
        elif isinstance(func, ast.Attribute) and func.attr == "getattr":
            if len(child.args) >= 3:
                violations.append(
                    GuardViolation(
                        rule_id="no_getattr_fallback",
                        severity="error",
                        file=file_path,
                        line=child.lineno + line_offset,
                        message="getattr() with default fallback is not allowed",
                        symbol="",
                    )
                )
    return violations


# ---------------------------------------------------------------------------
# Checker
# ---------------------------------------------------------------------------


class StructureChecker:
    """Scan Python files for structural violations."""

    # Map rule_id -> callable that returns list[GuardViolation]
    _FUNCTION_RULES: dict[str, Any] = {
        "no_underscore_functions": _check_no_underscore_functions,
        "mandatory_docstring": _check_mandatory_docstring,
    }

    _AST_RULES: dict[str, Any] = {
        "no_getattr_fallback": _check_no_getattr_fallback,
    }

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.rules = load_rules(project_root)
        self._entry_map: dict[tuple[str, str], str] = {}

    def check(
        self,
        since: str = "HEAD",
        files: list[str] | None = None,
        scan_all: bool = False,
        exclude_paths: list[str] | None = None,
    ) -> list[GuardViolation]:
        """Run enabled rules against Python files.

        Args:
            since: Git ref to diff against (default: uncommitted changes).
            files: If provided, check these exact file paths instead of git diff.
            scan_all: If True, scan all ``.py`` files under the project root
                (respecting *exclude_paths*).
            exclude_paths: Glob patterns to exclude when *scan_all* is True.
                Defaults exclude common non-source directories.

        Returns:
            List of violations found.
        """
        if scan_all:
            py_files = self._collect_all_py_files(exclude_paths)
        elif files is not None:
            py_files = [f for f in files if f.endswith(".py")]
        else:
            files = get_git_diff_files(self.project_root, since=since)
            py_files = [f for f in files if f.endswith(".py")]

        logger.info("Structure-check scanning %d Python file(s)", len(py_files))

        # Pre-load entry map if views_only_entries rule is enabled
        if self._is_enabled("views_only_entries"):
            self._entry_map = self._load_entry_map()

        violations: list[GuardViolation] = []
        for rel_path in py_files:
            abs_path = self.project_root / rel_path
            if not abs_path.exists():
                continue
            try:
                source = abs_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except SyntaxError as e:
                logger.warning("Syntax error in %s: %s", rel_path, e)
                continue
            except Exception as e:
                logger.warning("Failed to read %s: %s", rel_path, e)
                continue

            violations.extend(self._check_file(tree, rel_path))

        return violations

    def _collect_all_py_files(
        self, exclude_paths: list[str] | None = None
    ) -> list[str]:
        """Collect all ``.py`` files under the project root, excluding noise."""
        default_excludes = {
            ".venv",
            "venv",
            "__pycache__",
            ".git",
            ".repograph",
            "node_modules",
            ".tox",
            ".pytest_cache",
            "dist",
            "build",
            "*.egg-info",
        }
        if exclude_paths:
            default_excludes.update(exclude_paths)

        files: list[str] = []
        for path in self.project_root.rglob("*.py"):
            rel = path.relative_to(self.project_root).as_posix()
            if any(part in default_excludes for part in path.parts):
                continue
            if any(rel.endswith(pat) or pat in rel for pat in default_excludes):
                continue
            files.append(rel)
        return sorted(files)

    def _check_file(self, tree: ast.AST, rel_path: str) -> list[GuardViolation]:
        """Run all enabled rules against a single AST."""
        violations: list[GuardViolation] = []

        # Function-level rules
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for rule_id, checker in self._FUNCTION_RULES.items():
                    if self._is_enabled(rule_id):
                        found = checker(node, rel_path)
                        violations.extend(self._filter_by_severity(rule_id, found))

                # views_only_entries: check if this function is a known entry
                if self._is_enabled("views_only_entries"):
                    violations.extend(
                        self._filter_by_severity(
                            "views_only_entries",
                            self._check_views_only_entries(node, rel_path),
                        )
                    )

        # Whole-AST rules (run once per file)
        for rule_id, checker in self._AST_RULES.items():
            if self._is_enabled(rule_id):
                found = checker(tree, rel_path)
                violations.extend(self._filter_by_severity(rule_id, found))

        return violations

    def _is_enabled(self, rule_id: str) -> bool:
        """Return whether a rule is enabled in the constitution.

        A rule is enabled if:
        - It is present in the rules dict with ``enabled: true`` (or no explicit enabled key)
        - OR the rules dict is empty (default: all rules enabled for MVP convenience)
        """
        if not self.rules:
            return True
        rule = self.rules.get(rule_id)
        if rule is None:
            return False
        if isinstance(rule, dict):
            return rule.get("enabled", True)
        return bool(rule)

    def _filter_by_severity(
        self, rule_id: str, violations: list[GuardViolation]
    ) -> list[GuardViolation]:
        """Override violation severity if the constitution specifies one."""
        rule = self.rules.get(rule_id)
        if isinstance(rule, dict) and "severity" in rule:
            for v in violations:
                v.severity = rule["severity"]
        return violations

    # ------------------------------------------------------------------
    # views_only_entries rule
    # ------------------------------------------------------------------

    def _load_entry_map(self) -> dict[tuple[str, str], str]:
        """Load all entry cards and build a (file, symbol) -> id lookup."""
        from repoctx.utils.project import get_repograph_dir

        entries_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "entries"
        if not entries_dir.exists():
            return {}

        mapping: dict[tuple[str, str], str] = {}
        for path in entries_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                if data and data.get("card_type") == "entry":
                    src = data.get("source", {})
                    file_path = src.get("file", "")
                    symbol = src.get("symbol", "")
                    if file_path and symbol:
                        mapping[(file_path, symbol)] = data.get("id", "")
            except Exception:
                continue
        return mapping

    def _check_views_only_entries(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
    ) -> list[GuardViolation]:
        """Enforce that view files contain only registered entry functions.

        If a file matches the configured ``view_file_patterns``, every
        top-level function in it must have a corresponding EntryCard.
        Functions that are not registered as entries are treated as
        "helpers" and must be moved out of the view file.
        """
        rule_cfg = self.rules.get("views_only_entries")
        if not isinstance(rule_cfg, dict):
            return []

        patterns = rule_cfg.get("view_file_patterns", ["**/views.py"])
        if not any(
            Path(file_path).match(pat)
            or fnmatch.fnmatch(file_path, pat)
            or (pat.startswith("**/") and file_path.endswith(pat[3:]))
            for pat in patterns
        ):
            return []

        # Nested functions (inside classes or other functions) are allowed
        # — we only care about module-level helpers cluttering the view file.
        # The caller (_check_file) already filters to module-level funcs via
        # module_level_funcs, so any node reaching here is module-level.
        symbol = node.name
        if (file_path, symbol) not in self._entry_map:
            return [
                GuardViolation(
                    rule_id="views_only_entries",
                    severity="error",
                    file=file_path,
                    line=node.lineno,
                    message=(
                        f"Function '{symbol}' is not a registered entry point — "
                        f"view files must only contain entry functions. "
                        f"Move helper logic to a dedicated module (e.g. utils/ or services/)."
                    ),
                    symbol=symbol,
                )
            ]
        return []

    def _check_file(self, tree: ast.AST, rel_path: str) -> list[GuardViolation]:
        """Run all enabled rules against a single AST."""
        violations: list[GuardViolation] = []

        # Collect module-level function names for views_only_entries
        module_level_funcs: set[str] = set()
        for child in tree.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                module_level_funcs.add(child.name)

        # Function-level rules
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for rule_id, checker in self._FUNCTION_RULES.items():
                    if self._is_enabled(rule_id):
                        found = checker(node, rel_path)
                        violations.extend(self._filter_by_severity(rule_id, found))

                # views_only_entries: only for module-level functions in view files
                if (
                    self._is_enabled("views_only_entries")
                    and node.name in module_level_funcs
                ):
                    violations.extend(
                        self._filter_by_severity(
                            "views_only_entries",
                            self._check_views_only_entries(node, rel_path),
                        )
                    )

        # Whole-AST rules (run once per file)
        for rule_id, checker in self._AST_RULES.items():
            if self._is_enabled(rule_id):
                found = checker(tree, rel_path)
                violations.extend(self._filter_by_severity(rule_id, found))

        return violations

    @staticmethod
    def format_report(violations: list[GuardViolation]) -> str:
        """Return a human-readable report string."""
        if not violations:
            return "Structure check passed. No violations found."

        lines = [f"Structure check: {len(violations)} violation(s) found.\n"]
        for v in violations:
            lines.append(v.format())
        return "\n".join(lines)

    @staticmethod
    def generate_report(
        violations: list[GuardViolation],
        files_scanned: list[str],
        format: str = "markdown",
    ) -> str:
        """Generate a structured report (markdown or json) for downstream consumption.

        Args:
            violations: List of violations found.
            files_scanned: List of file paths that were scanned.
            format: ``"markdown"`` or ``"json"``.

        Returns:
            Report string ready to be written to a file.
        """
        if format == "json":
            return StructureChecker._report_json(violations, files_scanned)
        return StructureChecker._report_markdown(violations, files_scanned)

    @staticmethod
    def _report_markdown(
        violations: list[GuardViolation], files_scanned: list[str]
    ) -> str:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        total = len(violations)
        errors = sum(1 for v in violations if v.severity == "error")
        warnings = sum(1 for v in violations if v.severity == "warning")

        lines = [
            "# Structure Check Report",
            "",
            f"**Generated:** {now}",
            f"**Files scanned:** {len(files_scanned)}",
            f"**Violations:** {total} ({errors} errors, {warnings} warnings)",
            "",
            "---",
            "",
        ]

        if not violations:
            lines.append("✅ No violations found. All scanned files conform to the engineering constitution.")
            return "\n".join(lines)

        # --- By File ---
        lines.append("## Violations by File\n")
        by_file: dict[str, list[GuardViolation]] = {}
        for v in violations:
            by_file.setdefault(v.file, []).append(v)

        for fpath in sorted(by_file):
            lines.append(f"### `{fpath}`\n")
            lines.append("| Line | Severity | Rule | Symbol | Message |")
            lines.append("|------|----------|------|--------|---------|")
            for v in sorted(by_file[fpath], key=lambda x: x.line):
                sym = f"`{v.symbol}`" if v.symbol else "—"
                lines.append(
                    f"| {v.line} | {v.severity} | `{v.rule_id}` | {sym} | {v.message} |"
                )
            lines.append("")

        # --- By Rule ---
        lines.append("---\n")
        lines.append("## Violations by Rule\n")
        by_rule: dict[str, list[GuardViolation]] = {}
        for v in violations:
            by_rule.setdefault(v.rule_id, []).append(v)

        for rule_id in sorted(by_rule):
            rule_violations = by_rule[rule_id]
            lines.append(f"### `{rule_id}` ({len(rule_violations)})\n")
            for v in rule_violations:
                sym = f"`{v.symbol}`" if v.symbol else "—"
                lines.append(f"- `{v.file}:{v.line}` {sym} — {v.message}")
            lines.append("")

        # --- Fix Summary ---
        lines.append("---\n")
        lines.append("## Fix Summary\n")
        lines.append("| Rule | Count | Suggested Action |")
        lines.append("|------|-------|------------------|")
        actions = {
            "no_underscore_functions": "Rename to public names or use `__` prefix for private",
            "mandatory_docstring": "Add a docstring to each function",
            "no_getattr_fallback": "Remove the default argument from getattr() calls",
            "views_only_entries": "Move helper functions to dedicated modules (utils/, services/)",
        }
        for rule_id in sorted(by_rule):
            count = len(by_rule[rule_id])
            action = actions.get(rule_id, "Review and fix manually")
            lines.append(f"| `{rule_id}` | {count} | {action} |")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _report_json(
        violations: list[GuardViolation], files_scanned: list[str]
    ) -> str:
        import json
        from datetime import datetime, timezone

        by_file: dict[str, list[dict]] = {}
        by_rule: dict[str, list[dict]] = {}
        for v in violations:
            rec = {
                "line": v.line,
                "severity": v.severity,
                "rule_id": v.rule_id,
                "symbol": v.symbol,
                "message": v.message,
            }
            by_file.setdefault(v.file, []).append(rec)
            by_rule.setdefault(v.rule_id, []).append(rec)

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "files_scanned": files_scanned,
            "summary": {
                "total": len(violations),
                "errors": sum(1 for v in violations if v.severity == "error"),
                "warnings": sum(1 for v in violations if v.severity == "warning"),
            },
            "by_file": by_file,
            "by_rule": by_rule,
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)
