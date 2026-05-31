"""Extract Call nodes from a Python function body AST."""

from __future__ import annotations

import ast
from typing import Any


class CallExtractor:
    """Extract Call nodes from a function body AST."""

    def extract(self, func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, Any]]:
        """Extract all calls within a function body.

        Returns a list of dicts with keys: name, line, col.
        """
        calls: list[dict[str, Any]] = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node.func)
                if call_name:
                    calls.append({
                        "name": call_name,
                        "line": getattr(node, "lineno", 1),
                        "col": getattr(node, "col_offset", 0),
                    })
        return calls

    def _get_call_name(self, node: ast.expr) -> str | None:
        """Convert a call's func AST node to a dotted name string."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return ".".join(parts)
        return None
