"""Reuse checker: detect when new code duplicates existing reusable symbols.

Reads SymbolCards from semantic memory and compares them against new
functions in the current diff, suggesting reuse opportunities.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repoctx.guards.base import get_git_diff_files
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.guards")


@dataclass
class ReuseSuggestion:
    """A single reuse suggestion."""

    new_file: str
    new_symbol: str
    new_line: int
    existing_symbol_id: str
    existing_summary: str
    existing_use_when: list[str]
    match_reason: str
    confidence: str  # high | medium | low

    def format(self) -> str:
        use_when = ", ".join(self.existing_use_when) if self.existing_use_when else "N/A"
        return (
            f"  [{self.confidence.upper()}] {self.new_file}:{self.new_line} `{self.new_symbol}`\n"
            f"       → Reuse `{self.existing_symbol_id}` instead of re-implementing\n"
            f"         Summary: {self.existing_summary}\n"
            f"         Use when: {use_when}\n"
            f"         Reason: {self.match_reason}"
        )


class ReuseChecker:
    """Check whether new functions duplicate existing reusable symbols."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.symbols = self._load_all_symbols()

    def check(
        self,
        since: str = "HEAD",
        files: list[str] | None = None,
        scan_all: bool = False,
    ) -> list[ReuseSuggestion]:
        """Find reuse opportunities in new/modified Python files.

        Args:
            since: Git ref to diff against.
            files: Override file list.
            scan_all: Scan all Python files instead of diff.

        Returns:
            List of reuse suggestions.
        """
        if scan_all:
            py_files = self._collect_all_py_files()
        elif files is not None:
            py_files = [f for f in files if f.endswith(".py")]
        else:
            files = get_git_diff_files(self.project_root, since=since)
            py_files = [f for f in files if f.endswith(".py")]

        if not self.symbols:
            logger.info("No SymbolCards found — run 'repoctx digest-entry' first.")
            return []

        logger.info(
            "Reuse-check: %d file(s), %d symbol(s) in memory", len(py_files), len(self.symbols)
        )

        suggestions: list[ReuseSuggestion] = []
        for rel_path in py_files:
            abs_path = self.project_root / rel_path
            if not abs_path.exists():
                continue
            try:
                source = abs_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
            except SyntaxError:
                continue
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    sug = self._check_function(node, rel_path, source)
                    if sug:
                        suggestions.append(sug)

        # Sort by confidence (high first)
        order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: order.get(s.confidence, 3))
        return suggestions

    def _load_all_symbols(self) -> list[dict[str, Any]]:
        """Load all SymbolCards from disk."""
        from repoctx.utils.project import get_repograph_dir

        symbols_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "symbols"
        if not symbols_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in symbols_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                if data and data.get("card_type") == "symbol":
                    results.append(data)
            except Exception:
                continue
        return results

    def _collect_all_py_files(self) -> list[str]:
        """Collect all Python files under project root."""
        excludes = {".venv", "venv", "__pycache__", ".git", ".repograph", "node_modules"}
        files: list[str] = []
        for path in self.project_root.rglob("*.py"):
            if any(part in excludes for part in path.parts):
                continue
            files.append(path.relative_to(self.project_root).as_posix())
        return sorted(files)

    def _check_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: str,
        source: str,
    ) -> ReuseSuggestion | None:
        """Compare a single new function against all known symbols."""
        func_name = node.name.lower()
        # Get function body text for keyword matching
        body_start = max(0, node.lineno - 1)
        body_end = node.end_lineno or body_start + 1
        body_lines = source.splitlines()[body_start:body_end]
        body_text = " ".join(body_lines).lower()

        best_match: ReuseSuggestion | None = None
        best_score = 0

        for sym in self.symbols:
            score, reason = self._score_match(func_name, body_text, sym)
            if score > best_score:
                best_score = score
                confidence = "high" if score >= 50 else "medium" if score >= 25 else "low"
                best_match = ReuseSuggestion(
                    new_file=file_path,
                    new_symbol=node.name,
                    new_line=node.lineno,
                    existing_symbol_id=sym.get("id", "unknown"),
                    existing_summary=sym.get("summary", ""),
                    existing_use_when=sym.get("reuse_guidance", {}).get("use_when", []),
                    match_reason=reason,
                    confidence=confidence,
                )

        # Threshold: only report medium+ matches
        if best_match and best_score >= 25:
            return best_match
        return None

    def _score_match(
        self, func_name: str, body_text: str, sym: dict[str, Any]
    ) -> tuple[int, str]:
        """Score how likely *func_name* duplicates *sym*. Returns (score, reason)."""
        score = 0
        reasons: list[str] = []

        sym_id = sym.get("id", "").lower()
        sym_name = sym_id.split(".")[-1] if "." in sym_id else sym_id

        # 1. Function name overlap (strong signal)
        if func_name == sym_name:
            score += 60
            reasons.append("exact name match")
        elif func_name in sym_name or sym_name in func_name:
            score += 40
            reasons.append("similar name")
        # Check common substrings (e.g. "balance" in both)
        elif len(func_name) > 4 and len(sym_name) > 4:
            common = set(func_name.split("_")) & set(sym_name.split("_"))
            if common - {"get", "set", "is", "has", "the", "a"}:
                score += 20
                reasons.append(f"shared keywords: {', '.join(common - {'get', 'set', 'is', 'has', 'the', 'a'})}")

        # 2. Semantic role keyword overlap
        for role in sym.get("semantic_role", []):
            role_words = {w for w in role.lower().split() if len(w) > 3}
            body_words = set(body_text.split())
            overlap = role_words & body_words
            if overlap:
                score += len(overlap) * 8
                reasons.append(f"semantic role overlap: {', '.join(list(overlap)[:3])}")

        # 3. Summary keyword overlap
        summary = sym.get("summary", "").lower()
        summary_words = {w for w in summary.split() if len(w) > 3}
        body_words = set(body_text.split())
        overlap = summary_words & body_words
        if overlap:
            score += len(overlap) * 5
            reasons.append(f"summary keyword overlap: {', '.join(list(overlap)[:3])}")

        # 4. reuse_guidance.use_when overlap
        for use_when in sym.get("reuse_guidance", {}).get("use_when", []):
            use_words = {w for w in use_when.lower().split() if len(w) > 3}
            overlap = use_words & body_words
            if overlap:
                score += len(overlap) * 10
                reasons.append(f"reuse scenario match: {', '.join(list(overlap)[:3])}")

        return score, "; ".join(reasons) if reasons else "heuristic match"

    @staticmethod
    def format_report(suggestions: list[ReuseSuggestion]) -> str:
        """Return a human-readable report."""
        if not suggestions:
            return "Reuse check passed. No duplicate implementations detected."

        lines = [
            f"Reuse check: {len(suggestions)} suggestion(s) found.",
            "Consider reusing existing symbols instead of re-implementing:\n",
        ]
        for s in suggestions:
            lines.append(s.format())
            lines.append("")
        return "\n".join(lines)
