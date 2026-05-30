"""Extract dependency relations (imports) from source files."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExtractedRelation:
    """A single dependency relation."""

    source_file: Path
    target_module: str  # imported module/path
    relation_type: str  # import, from_import, require, etc.
    names: list[str] | None = None  # specific imported names


class RelationExtractor:
    """Extract import/dependency relations from source files."""

    def extract(self, file_path: Path, content: str | None = None) -> list[ExtractedRelation]:
        """Extract relations from a file.

        Args:
            file_path: Path to the source file.
            content: Optional file content. Read from disk if not provided.

        Returns:
            List of extracted relations.
        """
        if content is None:
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                return []

        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return self._extract_python(file_path, content)
        if suffix in (".vue", ".js", ".ts", ".jsx", ".tsx"):
            return self._extract_javascript(file_path, content)

        return []

    def _extract_python(
        self, file_path: Path, content: str
    ) -> list[ExtractedRelation]:
        """Extract import relations from Python source."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        relations: list[ExtractedRelation] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    relations.append(
                        ExtractedRelation(
                            source_file=file_path,
                            target_module=alias.name,
                            relation_type="import",
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                relations.append(
                    ExtractedRelation(
                        source_file=file_path,
                        target_module=module,
                        relation_type="from_import",
                        names=names,
                    )
                )
        return relations

    def _extract_javascript(
        self, file_path: Path, content: str
    ) -> list[ExtractedRelation]:
        """Extract import relations from JS/TS/Vue source."""
        relations: list[ExtractedRelation] = []

        # ES6 imports: import ... from 'module'
        es6_pattern = re.compile(r"import\s+.*?\s+from\s+['\"]([^'\"]+)['\"];?")
        for m in es6_pattern.finditer(content):
            relations.append(
                ExtractedRelation(
                    source_file=file_path,
                    target_module=m.group(1),
                    relation_type="import",
                )
            )

        # require('module')
        require_pattern = re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)")
        for m in require_pattern.finditer(content):
            relations.append(
                ExtractedRelation(
                    source_file=file_path,
                    target_module=m.group(1),
                    relation_type="require",
                )
            )

        return relations
