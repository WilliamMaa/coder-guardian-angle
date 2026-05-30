"""Persist the knowledge graph to JSON index files."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from repoctx.models import RepoCtxConfig


class Indexer:
    """Serialize the knowledge graph to the .repograph/ directory structure."""

    def __init__(self, config: RepoCtxConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.repograph_dir = project_root / ".repograph"

    def _write_json(self, path: Path, data: object) -> None:
        """Write data to a JSON file, creating parent directories."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def persist(self, graph: nx.DiGraph, scanned_at: str) -> None:
        """Persist the graph to the standard .repograph/ structure.

        Args:
            graph: The constructed knowledge graph.
            scanned_at: ISO 8601 timestamp of the scan.
        """
        # Gather statistics
        module_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "module"]
        file_nodes = [n for n, d in graph.nodes(data=True) if d.get("type") == "file"]
        entity_nodes = [
            n for n, d in graph.nodes(data=True)
            if d.get("type") is not None and d.get("type") not in ("module", "file")
        ]

        # 1. index.json
        index = {
            "scanned_at": scanned_at,
            "total_files": len(file_nodes),
            "total_modules": len(module_nodes),
            "modules": [graph.nodes[m]["id"] for m in module_nodes if "id" in graph.nodes[m]],
            "protected_core_ids": [],
            "reusable_capability_ids": [],
        }
        self._write_json(self.repograph_dir / "index.json", index)

        # 2. modules/*.json
        for node_id in module_nodes:
            data = dict(graph.nodes[node_id])
            mod_id = data.pop("id", node_id.replace("module:", ""))
            # Collect files belonging to this module
            mod_files = []
            for f_node in file_nodes:
                f_data = graph.nodes[f_node]
                if f_data.get("module_id") == mod_id:
                    mod_files.append(f_data.get("path", f_node))

            module_doc = {
                "id": mod_id,
                "name": data.get("id", mod_id),
                "path": data.get("path", ""),
                "type": data.get("module_type", "unknown"),
                "description": "",
                "files": sorted(mod_files),
                "dependencies": [],
                "dependents": [],
                "api_endpoints": [],
                "data_flows": [],
            }
            self._write_json(self.repograph_dir / "modules" / f"{mod_id}.json", module_doc)

        # 3. entities/*.json
        for node_id in entity_nodes:
            data = dict(graph.nodes[node_id])
            ent_id = node_id.replace(":", "_")
            entity_doc = {
                "id": ent_id,
                "type": data.get("type", "unknown"),
                "name": data.get("name", ""),
                "module_id": data.get("module_id"),
                "file_path": data.get("file_path", ""),
                "line_start": data.get("line_start", 1),
                "line_end": data.get("line_end", 1),
                "signature": data.get("signature", ""),
                "description": "",
            }
            self._write_json(self.repograph_dir / "entities" / f"{ent_id}.json", entity_doc)

        # 4. edges/*.json
        for edge_idx, (source, target, edge_data) in enumerate(graph.edges(data=True)):
            edge_doc = {
                "id": f"edge_{edge_idx}",
                "type": edge_data.get("type", "unknown"),
                "source_id": source,
                "target_id": target,
                "metadata": {k: v for k, v in edge_data.items() if k != "type"},
            }
            self._write_json(self.repograph_dir / "edges" / f"edge_{edge_idx}.json", edge_doc)

        # 5. Full graph snapshot for downstream analysis
        graph_data = nx.node_link_data(graph, edges="links")
        self._write_json(self.repograph_dir / "graph.json", graph_data)

        # 6. rules/ directory placeholder
        (self.repograph_dir / "rules").mkdir(parents=True, exist_ok=True)
