"""Extract code entities (functions, classes) from source files."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractedEntity:
    """A single extracted code entity."""

    name: str
    type: str  # function, class, method, variable, etc.
    line_start: int
    line_end: int
    signature: str = ""


class EntityExtractor:
    """Extract entities from various source file types."""

    def extract(self, file_path: Path, content: str | None = None) -> list[ExtractedEntity]:
        """Extract entities from a file.

        Args:
            file_path: Path to the source file.
            content: Optional file content string. If not provided, the file
                is read from disk.

        Returns:
            List of extracted entities.
        """
        if content is None:
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return []

        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return self._extract_python(content)
        if suffix in (".vue",):
            return self._extract_vue(content)
        if suffix in (".js", ".ts", ".jsx", ".tsx"):
            return self._extract_javascript(content)

        # For other file types, return a single file-level entity
        return [ExtractedEntity(name=file_path.name, type="file", line_start=1, line_end=1)]

    def _extract_python(self, content: str) -> list[ExtractedEntity]:
        """Extract functions and classes from Python source using AST."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        entities: list[ExtractedEntity] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                sig = self._python_func_signature(node)
                entities.append(
                    ExtractedEntity(
                        name=node.name,
                        type="function",
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        signature=sig,
                    )
                )
            elif isinstance(node, ast.ClassDef):
                entities.append(
                    ExtractedEntity(
                        name=node.name,
                        type="class",
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        signature=f"class {node.name}",
                    )
                )
        return entities

    def _python_func_signature(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Build a rough signature string for a Python function."""
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        return f"{prefix}{node.name}({', '.join(args)})"

    def _extract_vue(self, content: str) -> list[ExtractedEntity]:
        """Extract methods and computed properties from Vue SFC."""
        # Extract <script> or <script setup> section
        script_match = re.search(r"<script[^>]*>(.*?)</script>", content, re.DOTALL)
        if not script_match:
            return []

        script = script_match.group(1)
        entities: list[ExtractedEntity] = []

        # Match methods: methodName() {  or  methodName: function() {
        for m in re.finditer(r"^(\s+)(\w+)\s*\([^)]*\)\s*\{", script, re.MULTILINE):
            name = m.group(2)
            # Rough heuristic: skip very short names and JS keywords
            if len(name) < 2 or name in ("if", "for", "while", "switch", "catch", "return"):
                continue
            # Estimate line number by counting newlines before match
            line = script[: m.start()].count("\n") + 1
            entities.append(
                ExtractedEntity(
                    name=name,
                    type="method",
                    line_start=line,
                    line_end=line,
                )
            )

        return entities

    def _extract_javascript(self, content: str) -> list[ExtractedEntity]:
        """Extract exported functions and classes from JS/TS."""
        entities: list[ExtractedEntity] = []

        # export function name(...) or export const name = (...) =>
        func_pattern = re.compile(
            r"export\s+(?:async\s+)?function\s+(\w+)", re.MULTILINE
        )
        for m in func_pattern.finditer(content):
            line = content[: m.start()].count("\n") + 1
            entities.append(
                ExtractedEntity(
                    name=m.group(1),
                    type="function",
                    line_start=line,
                    line_end=line,
                )
            )

        # export class Name
        class_pattern = re.compile(r"export\s+class\s+(\w+)", re.MULTILINE)
        for m in class_pattern.finditer(content):
            line = content[: m.start()].count("\n") + 1
            entities.append(
                ExtractedEntity(
                    name=m.group(1),
                    type="class",
                    line_start=line,
                    line_end=line,
                )
            )

        return entities
