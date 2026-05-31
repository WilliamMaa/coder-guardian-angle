"""Import map resolution for Python source files."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportMap:
    """Maps locally-used names to their origin modules."""

    # local_name -> full_module_path  (for "module.attr" style calls)
    modules: dict[str, str] = field(default_factory=dict)
    # local_name -> (full_module_path, original_name)  (for direct calls)
    names: dict[str, tuple[str, str]] = field(default_factory=dict)

    def resolve(self, call_name: str) -> tuple[str | None, str]:
        """Resolve a call name to (module_path, symbol_name).

        Examples:
            - "get_balance" -> ("backend.credits.services", "get_balance")
            - "services.get_balance" -> ("backend.credits.services", "get_balance")
            - "self.start_call" -> (None, "start_call")
        """
        if "." in call_name:
            prefix, suffix = call_name.split(".", 1)
            if prefix == "self":
                return None, suffix
            if prefix in self.modules:
                return self.modules[prefix], suffix
            if prefix in self.names:
                mod_path, _orig = self.names[prefix]
                return mod_path, suffix
            return None, call_name

        if call_name in self.names:
            return self.names[call_name]
        if call_name in self.modules:
            return self.modules[call_name], call_name
        return None, call_name


class ImportResolver:
    """Extract import mappings from a Python file's AST."""

    def resolve(self, tree: ast.AST, current_file: Path, project_root: Path) -> ImportMap:
        """Build an ImportMap from the AST."""
        modules: dict[str, str] = {}
        names: dict[str, tuple[str, str]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname if alias.asname else alias.name
                    modules[local] = alias.name

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if node.level and node.level > 0:
                    module = self._resolve_relative_import(
                        node.level, module, current_file, project_root
                    )

                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname if alias.asname else alias.name
                    names[local] = (module, alias.name)
                    modules[local] = f"{module}.{alias.name}" if module else alias.name

        return ImportMap(modules=modules, names=names)

    def _resolve_relative_import(
        self,
        level: int,
        module: str,
        current_file: Path,
        project_root: Path,
    ) -> str:
        """Convert a relative import to an absolute module path."""
        rel_path = current_file.relative_to(project_root).parent
        parts = list(rel_path.parts)
        for _ in range(level - 1):
            if parts:
                parts.pop()
        if module:
            parts.append(module.replace(".", "/"))
        return "/".join(parts).replace("/", ".")
