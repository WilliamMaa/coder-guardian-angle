"""Auto-analysis: identify candidate protected cores and reusable capabilities."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from repoctx.models import (
    BlockPolicy,
    Capability,
    CapabilityIndex,
    EntryPoint,
    ProtectedCore,
    ProtectedCoreIndex,
    RepoCtxConfig,
)

# Keywords that suggest a file is sensitive / core
_PROTECTED_KEYWORDS = [
    "auth",
    "session",
    "login",
    "payment",
    "billing",
    "subscription",
    "credit",
    "core",
    "common",
    "utils",
]

# Verb prefixes that suggest a function is a reusable capability
_CAPABILITY_VERBS = [
    "get_",
    "check_",
    "validate_",
    "calculate_",
    "compute_",
    "parse_",
    "convert_",
    "fetch_",
    "create_",
    "build_",
    "generate_",
    "evaluate_",
    "predict_",
    "fit_",
    "transform_",
    "aggregate_",
    "summarize_",
]


class AutoAnalyzer:
    """Analyze the knowledge graph and propose protected cores / capabilities."""

    def __init__(self, graph: nx.DiGraph, config: RepoCtxConfig, project_root: Path) -> None:
        self.graph = graph
        self.config = config
        self.project_root = project_root

    # ------------------------------------------------------------------
    # Protected Core Analysis
    # ------------------------------------------------------------------

    def analyze_protected_cores(self) -> ProtectedCoreIndex:
        """Return candidate protected cores based on heuristics."""
        candidates: list[ProtectedCore] = []
        seen_files: set[str] = set()

        for node_id, data in self.graph.nodes(data=True):
            if data.get("type") != "file":
                continue

            file_path = data.get("path", "")
            module_id = data.get("module_id")
            if not file_path or file_path in seen_files:
                continue
            seen_files.add(file_path)

            score = 0
            reasons: list[str] = []

            # Heuristic 1: path keywords
            lower_path = file_path.lower()
            matched_kws = [kw for kw in _PROTECTED_KEYWORDS if kw in lower_path]
            if matched_kws:
                score += 3
                reasons.append(f"Path contains sensitive keywords: {matched_kws}")

            # Heuristic 2: fan-in (how many files import this module)
            in_edges = list(self.graph.in_edges(node_id, data=True))
            # Filter to internal project imports (exclude external:xxx)
            internal_importers = [
                src for src, _, edge_data in in_edges
                if not edge_data.get("type", "").startswith("external")
            ]
            if len(internal_importers) >= 3:
                score += 2
                reasons.append(f"High fan-in: imported by {len(internal_importers)} internal files")

            # Heuristic 3: entity density
            entity_count = sum(
                1
                for n, d in self.graph.nodes(data=True)
                if d.get("type") not in ("module", "file")
                and d.get("file_path") == file_path
            )
            if entity_count >= 5:
                score += 1
                reasons.append(f"High entity density: {entity_count} functions/classes")

            if score >= 3:
                candidates.append(
                    ProtectedCore(
                        id=f"core-auto-{file_path.replace('/', '_').replace('.', '_')}",
                        name=file_path,
                        type="service",
                        files=[file_path],
                        modules=[module_id] if module_id else [],
                        used_by=list(set(internal_importers)) if internal_importers else [],
                        description="; ".join(reasons),
                        block_policy=BlockPolicy(
                            default_action="block",
                            required_explanations=["Why core change is necessary"],
                            required_evidence=["Affected flows list"],
                            require_regression_tests=True,
                            require_rollback_plan=True,
                        ),
                    )
                )

        return ProtectedCoreIndex(version="1.0", cores=candidates)

    # ------------------------------------------------------------------
    # Reusable Capability Analysis
    # ------------------------------------------------------------------

    def analyze_capabilities(self) -> CapabilityIndex:
        """Return candidate reusable capabilities based on heuristics."""
        candidates: list[Capability] = []
        seen: set[str] = set()

        for _node_id, data in self.graph.nodes(data=True):
            if data.get("type") not in ("function", "method"):
                continue

            name = data.get("name", "")
            file_path = data.get("file_path", "")
            module_id = data.get("module_id")
            signature = data.get("signature", "")

            if not name or name.startswith("_"):
                continue

            # Heuristic 1: verb prefix
            has_verb = any(name.startswith(v) for v in _CAPABILITY_VERBS)
            if not has_verb:
                continue

            # Heuristic 2: not a test function
            if name.startswith("test_") or file_path.startswith("tests/"):
                continue

            unique_key = f"{file_path}::{name}"
            if unique_key in seen:
                continue
            seen.add(unique_key)

            candidates.append(
                Capability(
                    id=f"cap-auto-{unique_key.replace('/', '_').replace('.', '_')}",
                    name=name,
                    description=f"Auto-detected capability: {signature or name}",
                    module_id=module_id or "unknown",
                    entry_points=[
                        EntryPoint(
                            file_path=file_path,
                            function_name=name,
                            signature=signature,
                            usage_example=f"{name}(...)",
                        )
                    ],
                    use_cases=[],
                    constraints=["Do not modify this function for domain-specific logic"],
                    related_capabilities=[],
                )
            )

        # Cap to avoid overwhelming the user in MVP
        if len(candidates) > 30:
            candidates = candidates[:30]

        return CapabilityIndex(version="1.0", capabilities=candidates)
