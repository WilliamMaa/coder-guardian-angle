"""Entry-driven context analysis: analyze a file and its dependency radius."""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import networkx as nx
from pydantic import BaseModel, Field

from repoctx.loader import (
    load_capability_index,
    load_config,
    load_protected_core_index,
)
from repoctx.models import CapabilityIndex, ProtectedCoreIndex
from repoctx.utils.project import find_project_root


class EntryContextReport(BaseModel):
    """Structured report for entry-driven context analysis."""

    entry_file: str
    entry_module: str | None = None

    upstream: list[dict[str, Any]] = Field(default_factory=list)
    downstream: list[dict[str, Any]] = Field(default_factory=list)

    related_modules: list[str] = Field(default_factory=list)
    protected_cores_in_radius: list[dict[str, Any]] = Field(default_factory=list)
    capabilities_available: list[dict[str, Any]] = Field(default_factory=list)

    risk_summary: list[str] = Field(default_factory=list)
    suggested_tests: list[str] = Field(default_factory=list)


def _load_graph(project_root: Path) -> nx.DiGraph | None:
    """Load the full knowledge graph from graph.json."""
    graph_path = project_root / ".repograph" / "graph.json"
    if not graph_path.exists():
        return None
    try:
        with open(graph_path, encoding="utf-8") as f:
            data = json.load(f)
        return nx.node_link_graph(data, edges="links")
    except (OSError, json.JSONDecodeError):
        return None


def _find_file_node(graph: nx.DiGraph, file_path: str) -> str | None:
    """Find the graph node ID for a given relative file path."""
    # Exact match: file:<rel_path>
    candidate = f"file:{file_path}"
    if candidate in graph:
        return candidate
    # Try without leading ./
    if file_path.startswith("./"):
        candidate = f"file:{file_path[2:]}"
        if candidate in graph:
            return candidate
    # Fallback: search by path attribute
    for node_id, data in graph.nodes(data=True):
        if data.get("type") == "file" and data.get("path") == file_path:  # type: ignore[union-attr]
            return str(node_id)
    return None


class EntryContextAnalyzer:
    """Analyze the dependency radius of an entry file using the knowledge graph."""

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()
        self.config = load_config(self.project_root)
        self.graph = _load_graph(self.project_root)
        self._resolve_internal_edges()
        self.protected_core_index = self._load_protected_core_index()
        self.capability_index = self._load_capability_index()

    def _resolve_internal_edges(self) -> None:
        """Rewrite external:* edges that resolve to internal files into direct file edges."""
        if self.graph is None:
            return
        external_nodes = [n for n in self.graph.nodes() if n.startswith("external:")]
        for ext_node in external_nodes:
            module_path = ext_node.replace("external:", "").replace(".", "/")
            candidate: str | None = None
            for suffix in (".py", "/__init__.py"):
                file_node = f"file:{module_path}{suffix}"
                if file_node in self.graph:
                    candidate = file_node
                    break
            if candidate is None:
                continue
            # Re-wire: source -> ext_node  becomes  source -> candidate
            for source in list(self.graph.predecessors(ext_node)):
                edge_data = dict(self.graph.edges[source, ext_node])
                self.graph.add_edge(source, candidate, **edge_data)

    def _load_protected_core_index(self) -> ProtectedCoreIndex:
        try:
            return load_protected_core_index(self.project_root)
        except Exception:
            return ProtectedCoreIndex(version="1.0", cores=[])

    def _load_capability_index(self) -> CapabilityIndex:
        try:
            return load_capability_index(self.project_root)
        except Exception:
            return CapabilityIndex(version="1.0", capabilities=[])

    def analyze(
        self,
        file_path: str,
        max_depth: int = 2,
    ) -> EntryContextReport:
        """Analyze an entry file and return its dependency context.

        Args:
            file_path: Relative path to the entry file from project root.
            max_depth: Maximum hops to traverse up/downstream (default 2).

        Returns:
            Structured entry context report.
        """
        if self.graph is None:
            raise RuntimeError(
                "Knowledge graph not found. Run 'repoctx scan' first."
            )

        entry_node = _find_file_node(self.graph, file_path)
        if entry_node is None:
            raise ValueError(f"File not found in knowledge graph: {file_path}")

        entry_data = self.graph.nodes[entry_node]
        entry_module = entry_data.get("module_id")

        # Traverse upstream (who depends on this file)
        upstream = self._traverse(
            entry_node,
            direction="upstream",
            max_depth=max_depth,
        )

        # Traverse downstream (what this file depends on)
        downstream = self._traverse(
            entry_node,
            direction="downstream",
            max_depth=max_depth,
        )

        # Collect modules touched in the radius
        all_nodes = {entry_node} | {n["node_id"] for n in upstream} | {n["node_id"] for n in downstream}
        modules: set[str] = set()
        for node_id in all_nodes:
            mod = self.graph.nodes[node_id].get("module_id")
            if mod:
                modules.add(mod)

        # Cross-reference with protected cores
        protected_in_radius: list[dict[str, Any]] = []
        for core in self.protected_core_index.cores:
            core_files = set(core.files)
            for node_id in all_nodes:
                node_path = self.graph.nodes[node_id].get("path", "")
                if node_path and any(node_path == cf or node_path.startswith(cf.rstrip("*")) for cf in core_files):
                    protected_in_radius.append({
                        "name": core.name,
                        "files": core.files,
                        "description": core.description,
                        "module": core.modules[0] if core.modules else None,
                    })
                    break

        # Cross-reference with capabilities
        caps_available: list[dict[str, Any]] = []
        for cap in self.capability_index.capabilities:
            for ep in cap.entry_points:
                if ep.file_path in {self.graph.nodes[n].get("path", "") for n in all_nodes}:
                    caps_available.append({
                        "name": cap.name,
                        "file_path": ep.file_path,
                        "function": ep.function_name,
                        "signature": ep.signature,
                    })
                    break

        # Deduplicate
        seen_caps: set[str] = set()
        unique_caps: list[dict[str, Any]] = []
        for c in caps_available:
            key = f"{c['file_path']}::{c['function']}"
            if key not in seen_caps:
                seen_caps.add(key)
                unique_caps.append(c)

        # Risk summary
        risks: list[str] = []
        if protected_in_radius:
            risks.append(
                f"Entry file touches {len(protected_in_radius)} protected core(s): "
                f"{', '.join(p['name'] for p in protected_in_radius)}"
            )
        if entry_module and entry_module in modules:
            risks.append(f"Entry module: {entry_module}")

        return EntryContextReport(
            entry_file=file_path,
            entry_module=entry_module,
            upstream=upstream,
            downstream=downstream,
            related_modules=sorted(modules),
            protected_cores_in_radius=protected_in_radius,
            capabilities_available=unique_caps,
            risk_summary=risks,
            suggested_tests=[],
        )

    def _traverse(
        self,
        start_node: str,
        direction: str,
        max_depth: int,
    ) -> list[dict[str, Any]]:
        """BFS traverse upstream or downstream from a start node.

        Returns a list of dicts with node_id, path, type, module_id, depth.
        """
        assert self.graph is not None
        neighbor_fn = self.graph.predecessors if direction == "upstream" else self.graph.successors

        visited: set[str] = {start_node}
        queue: deque[tuple[str, int]] = deque([(start_node, 0)])
        results: list[dict[str, Any]] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue
            for neighbor in neighbor_fn(current):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                data = self.graph.nodes[neighbor]
                # Skip external/module nodes in results; they clutter the report
                node_type = data.get("type", "")
                if node_type in ("module",):
                    # Still traverse through modules but don't list them
                    queue.append((neighbor, depth + 1))
                    continue
                if node_type == "external":
                    continue

                results.append({
                    "node_id": neighbor,
                    "path": data.get("path", ""),
                    "name": data.get("name", ""),
                    "type": node_type,
                    "module_id": data.get("module_id"),
                    "depth": depth + 1,
                })
                queue.append((neighbor, depth + 1))

        return results

    def format_text(self, report: EntryContextReport) -> str:
        """Format the report as human-readable text."""
        lines: list[str] = [
            "=" * 60,
            "RepoCtx Guard — Entry Context Report",
            "=" * 60,
            "",
            f"Entry File: {report.entry_file}",
        ]
        if report.entry_module:
            lines.append(f"Entry Module: {report.entry_module}")

        lines.extend(["", "-" * 40, "Upstream — Who depends on this file", "-" * 40])
        if report.upstream:
            for item in report.upstream:
                mod = f" [{item['module_id']}]" if item.get("module_id") else ""
                lines.append(f"  • {item['path']}{mod} (depth {item['depth']})")
        else:
            lines.append("  (none found)")

        lines.extend(["", "-" * 40, "Downstream — What this file depends on", "-" * 40])
        if report.downstream:
            for item in report.downstream:
                mod = f" [{item['module_id']}]" if item.get("module_id") else ""
                lines.append(f"  • {item['path']}{mod} (depth {item['depth']})")
        else:
            lines.append("  (none found)")

        lines.extend(["", "-" * 40, "Modules Involved", "-" * 40])
        if report.related_modules:
            for m in report.related_modules:
                lines.append(f"  • {m}")
        else:
            lines.append("  (none found)")

        lines.extend(["", "-" * 40, "Protected Cores in Impact Radius", "-" * 40])
        if report.protected_cores_in_radius:
            for core in report.protected_cores_in_radius:
                lines.append(f"  ⚠ {core['name']}")
                lines.append(f"    Files: {', '.join(core['files'])}")
                lines.append(f"    {core['description']}")
        else:
            lines.append("  (none found)")

        lines.extend(["", "-" * 40, "Reusable Capabilities Available", "-" * 40])
        if report.capabilities_available:
            for cap in report.capabilities_available:
                sig = f" — {cap['signature']}" if cap.get("signature") else ""
                lines.append(f"  • {cap['name']} ({cap['file_path']}){sig}")
        else:
            lines.append("  (none found)")

        lines.extend(["", "-" * 40, "Risk Summary", "-" * 40])
        if report.risk_summary:
            for r in report.risk_summary:
                lines.append(f"  ! {r}")
        else:
            lines.append("  (none identified)")

        lines.extend(["", "=" * 60])
        return "\n".join(lines)
