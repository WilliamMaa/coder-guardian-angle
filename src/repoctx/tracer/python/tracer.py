"""Python-specific call-chain tracer."""

from __future__ import annotations

import ast
from pathlib import Path

from repoctx.cards import SymbolSource
from repoctx.tracer.base import BaseTracer, CallNode, CallTree, TracerContext
from repoctx.tracer.python.call_extractor import CallExtractor
from repoctx.tracer.python.import_resolver import ImportMap, ImportResolver
from repoctx.tracer.python.module_resolver import ModulePathResolver


class PythonTracer(BaseTracer):
    """Trace Python function calls through import relationships.

    Handles:
    - ``import X``
    - ``import X as Y``
    - ``from X import Y``
    - ``from X import Y as Z``
    - Relative imports (``from . import X``, ``from .. import X``)

    Known limitations (acceptable for MVP):
    - ``from X import *`` is ignored (cannot determine imported names statically).
    - Dynamic imports (``__import__``, ``importlib``) are ignored.
    - Method calls on arbitrary objects (``obj.foo()`` where ``obj`` is not
      an imported module) are marked as *unresolved*.
    """

    extensions = (".py",)

    def __init__(self, context: TracerContext) -> None:
        super().__init__(context)
        self.import_resolver = ImportResolver()
        self.call_extractor = CallExtractor()
        self.module_resolver = ModulePathResolver(context.project_root)

    def trace(
        self,
        file_path: str,
        symbol_names: list[str] | None = None,
    ) -> CallTree:
        abs_path = self.context.project_root / file_path
        if not abs_path.exists():
            raise ValueError(f"File not found: {abs_path}")

        tree = self._parse_file(abs_path)
        import_map = self.import_resolver.resolve(tree, abs_path, self.context.project_root)

        if symbol_names is None:
            symbol_names = [
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]

        entry_nodes: list[CallNode] = []
        visited: set[str] = set()

        for symbol_name in symbol_names:
            func_node = self._find_function(tree, symbol_name)
            if func_node is None:
                continue
            source = SymbolSource(
                file=file_path,
                symbol=symbol_name,
                line_start=func_node.lineno,
                line_end=func_node.end_lineno or func_node.lineno,
            )
            node = self._trace_function(
                func_node, source, import_map, visited, current_depth=0
            )
            entry_nodes.append(node)

        if not entry_nodes:
            raise ValueError(f"No matching functions found in {file_path}")

        if len(entry_nodes) == 1:
            return CallTree(
                entry=entry_nodes[0],
                all_nodes=self._flatten(entry_nodes[0]),
            )

        root = CallNode(
            symbol=f"<entry:{file_path}>",
            module_path=None,
            source=SymbolSource(file=file_path, symbol="<entry>"),
            children=entry_nodes,
        )
        return CallTree(entry=root, all_nodes=self._flatten(root))

    def _trace_function(
        self,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        source: SymbolSource,
        import_map: ImportMap,
        visited: set[str],
        current_depth: int,
    ) -> CallNode:
        node = CallNode(
            symbol=source.symbol,
            module_path=None,
            source=source,
        )

        visit_key = f"{source.file}::{source.symbol}"
        if visit_key in visited or current_depth >= self.context.max_depth:
            return node
        visited.add(visit_key)

        calls = self.call_extractor.extract(func_node)
        for call in calls:
            call_name = call["name"]
            module_path, symbol_name = import_map.resolve(call_name)

            if module_path is None:
                node.children.append(
                    CallNode(
                        symbol=call_name,
                        module_path=None,
                        source=SymbolSource(
                            file=source.file,
                            symbol=call_name,
                            line_start=call["line"],
                        ),
                        is_external=True,
                        call_type="unknown",
                    )
                )
                continue

            target_file = self.module_resolver.resolve(module_path)
            if target_file is None:
                node.children.append(
                    CallNode(
                        symbol=symbol_name,
                        module_path=module_path,
                        source=SymbolSource(
                            file=source.file,
                            symbol=call_name,
                            line_start=call["line"],
                        ),
                        is_external=True,
                        call_type="function",
                    )
                )
                continue

            try:
                target_tree = self._parse_file(target_file)
                target_func = self._find_function(target_tree, symbol_name)
            except SyntaxError:
                target_func = None

            if target_func is None:
                node.children.append(
                    CallNode(
                        symbol=symbol_name,
                        module_path=module_path,
                        source=SymbolSource(
                            file=str(target_file.relative_to(self.context.project_root)),
                            symbol=symbol_name,
                        ),
                        is_external=True,
                        call_type="function",
                    )
                )
                continue

            target_import_map = self.import_resolver.resolve(
                target_tree, target_file, self.context.project_root
            )
            target_source = SymbolSource(
                file=str(target_file.relative_to(self.context.project_root)),
                symbol=symbol_name,
                line_start=target_func.lineno,
                line_end=target_func.end_lineno or target_func.lineno,
            )
            child = self._trace_function(
                target_func,
                target_source,
                target_import_map,
                visited,
                current_depth + 1,
            )
            node.children.append(child)

        return node

    def _parse_file(self, path: Path) -> ast.AST:
        content = path.read_text(encoding="utf-8")
        return ast.parse(content)

    def _find_function(
        self, tree: ast.AST, name: str
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        return None

    def _flatten(self, node: CallNode) -> list[CallNode]:
        result = [node]
        for child in node.children:
            result.extend(self._flatten(child))
        return result
