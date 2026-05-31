"""Semantic digest engine: orchestrate tracing, LLM generation, and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from repoctx.tracer.factory import get_tracer
from repoctx.utils.project import find_project_root


@dataclass
class DigestResult:
    """Result of a digest-entry run."""

    cards: list[dict] = field(default_factory=list)
    written_paths: list[Path] = field(default_factory=list)


class SemanticDigestEngine:
    """Orchestrate the full semantic digestion pipeline.

    Pipeline:
        1. Detect language / framework.
        2. Select appropriate tracer (factory pattern).
        3. Trace call graph from entry symbols.
        4. Generate semantic cards (Entry, Symbol, Context Pack).
        5. Persist cards to ``.repograph/semantic_memory/``.
    """

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()

    def digest(
        self,
        file_path: str,
        target_symbols: list[str] | None = None,
        max_depth: int = 3,
    ) -> DigestResult:
        """Digest an entry file and generate semantic memory cards.

        Args:
            file_path: Relative path from project root.
            target_symbols: Specific function/class names to trace.
                If None, all top-level exported symbols are traced.
            max_depth: Maximum call-chain recursion depth.

        Returns:
            DigestResult containing generated cards and their write paths.
        """
        from repoctx.tracer.base import TracerContext

        context = TracerContext(
            project_root=self.project_root,
            max_depth=max_depth,
        )
        tracer = get_tracer(file_path, context)
        tree = tracer.trace(file_path, symbol_names=target_symbols)

        # TODO: Phase 2 — generate cards from CallTree via LLM
        # For now, return a stub result so the CLI can complete.
        cards: list[dict] = []
        written_paths: list[Path] = []

        # Ensure output directory exists
        output_dir = self.project_root / ".repograph" / "semantic_memory"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write a minimal entry card stub
        entry_node = tree.entry
        stub_card = {
            "card_type": "entry",
            "id": f"entry.{entry_node.symbol}",
            "source": {
                "file": file_path,
                "symbol": entry_node.symbol,
            },
            "summary": f"Stub entry card for {entry_node.symbol}",
            "traced_nodes": len(tree.all_nodes),
        }
        cards.append(stub_card)

        entry_path = output_dir / "entries" / f"entry.{entry_node.symbol}.yaml"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        from repoctx.utils.yaml_io import dump_yaml

        dump_yaml(stub_card, entry_path)
        written_paths.append(entry_path)

        return DigestResult(cards=cards, written_paths=written_paths)
