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
from repoctx.scanner.auto_discovery import discover_modules
from repoctx.scanner.entity_extractor import EntityExtractor
from repoctx.scanner.file_scanner import scan_files
from repoctx.scanner.graph_builder import GraphBuilder
from repoctx.scanner.indexer import Indexer
from repoctx.scanner.module_resolver import ModuleResolver
from repoctx.scanner.relation_extractor import RelationExtractor
from repoctx.utils.project import ProjectRootError, find_project_root


class ScanEngine:
    """Orchestrates the full project scan and indexing pipeline."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.config: RepoCtxConfig | None = None

    def ensure_config(self) -> RepoCtxConfig:
        """Load or generate project configuration.

        Auto-discovers modules if none are defined in the config.

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

        # Auto-discover modules if none are explicitly defined
        if not self.config.modules:
            discovered = discover_modules(self.project_root, self.config.framework)
            if discovered:
                self.config.modules = discovered
                print(f"[auto-discovery] Found {len(discovered)} modules:")
                for mod in discovered:
                    print(f"  - {mod.name}  ->  {mod.path}")
                print(
                    "[tip] To fix these modules, add them to .repoctx.yaml.\n"
                    "      Leave 'modules:' empty to auto-discover each time."
                )

        return self.config

    def run(self, auto_approve: bool = False) -> Path:
        """Execute the full scan pipeline.

        Args:
            auto_approve: If True, auto-accept all discovered cores/capabilities.

        Returns:
            Path to the generated .repograph/ directory.
        """
        from repoctx.scanner.auto_analysis import AutoAnalyzer
        from repoctx.scanner.review_interaction import (
            review_capabilities,
            review_protected_cores,
        )
        from repoctx.utils.yaml_io import dump_yaml

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

        # Step 6: Auto-analysis
        repograph_dir = self.project_root / ".repograph"
        analyzer = AutoAnalyzer(graph, config, self.project_root)
        core_candidates = analyzer.analyze_protected_cores()
        cap_candidates = analyzer.analyze_capabilities()

        # Step 7: Review interaction
        if core_candidates.cores or cap_candidates.capabilities:
            confirmed_cores = review_protected_cores(core_candidates, auto_approve=auto_approve)
            confirmed_caps = review_capabilities(cap_candidates, auto_approve=auto_approve)

            # Step 8: Write confirmed indexes
            if confirmed_cores.cores:
                dump_yaml(
                    confirmed_cores.model_dump(mode="json", exclude_none=True),
                    repograph_dir / "protected_core.yaml",
                )
                print(f"[scan] Wrote {len(confirmed_cores.cores)} protected cores.")
            if confirmed_caps.capabilities:
                dump_yaml(
                    confirmed_caps.model_dump(mode="json", exclude_none=True),
                    repograph_dir / "reusable_capabilities.yaml",
                )
                print(f"[scan] Wrote {len(confirmed_caps.capabilities)} reusable capabilities.")
        else:
            # Fallback: generate empty templates if nothing was auto-detected
            if not (repograph_dir / "protected_core.yaml").exists():
                generate_protected_core_template(self.project_root)
            if not (repograph_dir / "reusable_capabilities.yaml").exists():
                generate_capability_template(self.project_root)

        return repograph_dir


def scan_project(cwd: Path | str | None = None, auto_approve: bool = False) -> Path:
    """High-level entry point to scan the current project.

    If no `.repoctx.yaml` marker is found in any parent directory, the
    current working directory is used as the project root and a config
    template is generated automatically.

    Args:
        cwd: Starting directory for project root discovery.
            Defaults to current working directory.

    Returns:
        Path to the .repograph/ directory.

    Raises:
        RuntimeError: If configuration is missing or invalid.
    """
    cwd = Path.cwd() if cwd is None else Path(cwd)

    try:
        root = find_project_root(cwd)
    except ProjectRootError:
        root = cwd

    engine = ScanEngine(root)
    return engine.run(auto_approve=auto_approve)
