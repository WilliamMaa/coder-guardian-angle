"""Scanning orchestrator: tie together all scanner components."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from repoctx.loader import (
    generate_capability_template,
    generate_config_template,
    generate_protected_core_template,
    load_config,
)
from repoctx.models import RepoCtxConfig
from repoctx.scanner.entity_extractor import EntityExtractor
from repoctx.scanner.file_scanner import scan_files
from repoctx.scanner.graph_builder import GraphBuilder
from repoctx.scanner.indexer import Indexer
from repoctx.scanner.module_resolver import ModuleResolver
from repoctx.scanner.relation_extractor import RelationExtractor
from repoctx.utils.project import find_project_root


class ScanEngine:
    """Orchestrates the full project scan and indexing pipeline."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.config: RepoCtxConfig | None = None

    def ensure_config(self) -> RepoCtxConfig:
        """Load or generate project configuration.

        Returns:
            Validated project configuration.
        """
        try:
            self.config = load_config(self.project_root)
        except Exception as _exc:
            # Generate template if missing
            template_path = generate_config_template(self.project_root)
            raise RuntimeError(
                f"Project configuration not found. Generated template at: {template_path}\n"
                f"Please edit it and re-run 'repoctx scan'."
            ) from None
        return self.config

    def run(self) -> Path:
        """Execute the full scan pipeline.

        Returns:
            Path to the generated .repograph/ directory.
        """
        config = self.ensure_config()
        scanned_at = datetime.now(timezone.utc).isoformat()

        # Step 1: Scan files
        files = scan_files(config, self.project_root)

        # Step 2: Resolve modules
        resolver = ModuleResolver(config, self.project_root)
        file_to_module = resolver.resolve_all(files)

        # Step 3: Extract entities and relations
        entity_extractor = EntityExtractor()
        relation_extractor = RelationExtractor()

        file_entities: dict[Path, list] = {}
        file_relations: dict[Path, list] = {}

        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            file_entities[file_path] = entity_extractor.extract(file_path, content)
            file_relations[file_path] = relation_extractor.extract(file_path, content)

        # Step 4: Build graph
        builder = GraphBuilder(config, self.project_root)
        graph = builder.build(files, file_to_module, file_entities, file_relations)

        # Step 5: Persist indexes
        indexer = Indexer(config, self.project_root)
        indexer.persist(graph, scanned_at)

        # Step 6: Generate template indexes if missing
        repograph_dir = self.project_root / ".repograph"
        if not (repograph_dir / "protected_core.yaml").exists():
            generate_protected_core_template(self.project_root)
        if not (repograph_dir / "reusable_capabilities.yaml").exists():
            generate_capability_template(self.project_root)

        return repograph_dir


def scan_project(cwd: Path | str | None = None) -> Path:
    """High-level entry point to scan the current project.

    Args:
        cwd: Starting directory for project root discovery.
            Defaults to current working directory.

    Returns:
        Path to the .repograph/ directory.

    Raises:
        ProjectRootError: If project root cannot be found.
        RuntimeError: If configuration is missing or invalid.
    """
    cwd = Path.cwd() if cwd is None else Path(cwd)

    root = find_project_root(cwd)
    engine = ScanEngine(root)
    return engine.run()
