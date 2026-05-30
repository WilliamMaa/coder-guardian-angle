"""Build an in-memory knowledge graph from scanned project data."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from repoctx.models import RepoCtxConfig
from repoctx.scanner.entity_extractor import ExtractedEntity
from repoctx.scanner.relation_extractor import ExtractedRelation


class GraphBuilder:
    """Construct a directed knowledge graph from scan results."""

    def __init__(self, config: RepoCtxConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self.graph = nx.DiGraph()

    def add_module(self, module_id: str, module_type: str, module_path: str) -> None:
        """Add a module node to the graph."""
        self.graph.add_node(
            f"module:{module_id}",
            type="module",
            id=module_id,
            module_type=module_type,
            path=module_path,
        )

    def add_file(self, file_path: Path, module_id: str | None = None) -> str:
        """Add a file node and its belongs_to edge. Returns the node ID."""
        rel_path = file_path.relative_to(self.project_root).as_posix()
        node_id = f"file:{rel_path}"
        self.graph.add_node(
            node_id,
            type="file",
            path=rel_path,
            name=file_path.name,
            module_id=module_id,
        )
        if module_id:
            self.graph.add_edge(
                node_id,
                f"module:{module_id}",
                type="belongs_to",
            )
        return node_id

    def add_entity(
        self,
        file_path: Path,
        entity: ExtractedEntity,
        module_id: str | None = None,
    ) -> str:
        """Add an entity node (function, class) and link it to its file."""
        rel_path = file_path.relative_to(self.project_root).as_posix()
        safe_id = rel_path.replace("/", "_")
        node_id = f"entity:{safe_id}:{entity.name}"
        self.graph.add_node(
            node_id,
            type=entity.type,
            name=entity.name,
            file_path=rel_path,
            line_start=entity.line_start,
            line_end=entity.line_end,
            signature=entity.signature,
            module_id=module_id,
        )
        file_node = f"file:{rel_path}"
        self.graph.add_edge(node_id, file_node, type="belongs_to")
        return node_id

    def add_relation(
        self,
        file_path: Path,
        relation: ExtractedRelation,
    ) -> None:
        """Add a dependency edge from a file to an imported module."""
        rel_path = file_path.relative_to(self.project_root).as_posix()
        source_node = f"file:{rel_path}"
        # Target may not be a file in the project; store as external reference
        target_node = f"external:{relation.target_module}"
        self.graph.add_edge(
            source_node,
            target_node,
            type=relation.relation_type,
            names=relation.names,
        )

    def build(
        self,
        files: list[Path],
        file_to_module: dict[Path, str | None],
        file_entities: dict[Path, list[ExtractedEntity]],
        file_relations: dict[Path, list[ExtractedRelation]],
    ) -> nx.DiGraph:
        """Build the complete graph from scan data.

        Args:
            files: All scanned files.
            file_to_module: Mapping from file path to module ID (or None).
            file_entities: Mapping from file path to extracted entities.
            file_relations: Mapping from file path to extracted relations.

        Returns:
            The constructed directed graph.
        """
        # Add module nodes first
        for mod in self.config.modules:
            self.add_module(mod.name, mod.type, mod.path)

        # Add file nodes
        for file_path in files:
            module_id = file_to_module.get(file_path)
            self.add_file(file_path, module_id)

        # Add entity nodes
        for file_path, entities in file_entities.items():
            module_id = file_to_module.get(file_path)
            for entity in entities:
                self.add_entity(file_path, entity, module_id)

        # Add relation edges
        for file_path, relations in file_relations.items():
            for relation in relations:
                self.add_relation(file_path, relation)

        return self.graph
