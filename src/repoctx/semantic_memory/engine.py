"""Semantic digest engine: orchestrate tracing, LLM generation, and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from repoctx.cards import (
    CardVersion,
    ContextPack,
    DeepFunctionRef,
    EntryCard,
    ReuseGuidance,
    SymbolCard,
    SymbolSource,
)
from repoctx.llm.client import LLMClient
from repoctx.llm.pipeline import PromptPipeline
from repoctx.semantic_memory.prompt_builder import (
    build_context_prompt,
    build_entry_prompt,
    build_symbol_prompt,
)
from repoctx.semantic_memory.versioning import (
    compute_dependency_hash,
    compute_file_hash,
    get_git_commit,
)
from repoctx.tracer.base import CallNode, CallTree, TracerContext
from repoctx.tracer.factory import get_tracer
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import dump_yaml


@dataclass
class DigestResult:
    """Result of a digest-entry run."""

    cards: list[dict] = field(default_factory=list)
    written_paths: list[Path] = field(default_factory=list)


# ---------------------------------------------------------------------------
# LLM output shapes (intermediate — engine adds source/version afterwards)
# ---------------------------------------------------------------------------


class _EntryOutput(BaseModel):
    summary: str
    business_role: list[str]
    main_downstream: list[str]


class _SymbolOutput(BaseModel):
    id: str
    summary: str
    semantic_role: list[str]
    side_effects: str
    used_by_flows: list[str]
    reuse_guidance: ReuseGuidance


class _ContextOutput(BaseModel):
    id: str
    title: str
    flow_summary: str
    main_entries: list[str]
    main_paths: list[str]
    important_deep_functions: list[DeepFunctionRef]
    known_pitfalls: list[str]
    related_tests: list[str]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SemanticDigestEngine:
    """Orchestrate the full semantic digestion pipeline.

    Pipeline:
        1. Detect language / framework.
        2. Select appropriate tracer (factory pattern).
        3. Trace call graph from entry symbols.
        4. Generate semantic cards (Entry, Symbol, Context Pack) via LLM.
        5. Attach versioning metadata.
        6. Persist cards to ``.repograph/semantic_memory/``.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        client: LLMClient | None = None,
    ) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()

        if client is None:
            self.client = self._auto_client()
        else:
            self.client = client

        self.pipeline = PromptPipeline(self.client)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        context = TracerContext(
            project_root=self.project_root,
            max_depth=max_depth,
        )
        tracer = get_tracer(file_path, context)
        tree = tracer.trace(file_path, symbol_names=target_symbols)

        # The tracer returns a synthetic root when multiple symbols are traced.
        entries = self._extract_entries(tree, file_path)

        all_cards: list[dict] = []
        all_paths: list[Path] = []

        for entry in entries:
            entry_card, symbol_cards, context_pack, paths = self._digest_entry(
                entry, max_depth
            )
            all_cards.extend(
                [
                    entry_card.model_dump(mode="json"),
                    *[sc.model_dump(mode="json") for sc in symbol_cards],
                    context_pack.model_dump(mode="json"),
                ]
            )
            all_paths.extend(paths)

        return DigestResult(cards=all_cards, written_paths=all_paths)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _auto_client(self) -> LLMClient:
        """Build an LLMClient from the project config."""
        try:
            from repoctx.loader import load_config

            cfg = load_config(self.project_root)
        except Exception as e:
            raise RuntimeError(
                "LLM client not configured. "
                "Set an API key in .repoctx.yaml or repoctx config.ini."
            ) from e

        return LLMClient(cfg.model_provider, api_key=cfg.get_api_key())

    def _extract_entries(self, tree: CallTree, file_path: str) -> list[CallNode]:
        """Return the real entry node(s) from a CallTree.

        When the tracer traces a single symbol, ``tree.entry`` is that symbol.
        When it traces multiple symbols, ``tree.entry`` is a synthetic root
        whose children are the real entries.
        """
        if tree.entry.symbol == f"<entry:{file_path}>":
            return tree.entry.children
        return [tree.entry]

    def _digest_entry(
        self,
        entry: CallNode,
        max_depth: int,
    ) -> tuple[EntryCard, list[SymbolCard], ContextPack, list[Path]]:
        """Digest a single entry node and persist its cards."""
        # Version metadata
        code_hash = compute_file_hash(self.project_root / entry.source.file)
        git_commit = get_git_commit(self.project_root)
        dep_hash = compute_dependency_hash(entry)
        generated_at = datetime.now(timezone.utc).isoformat()

        # 1. EntryCard
        entry_card = self._generate_entry_card(
            entry, code_hash, dep_hash, git_commit, generated_at
        )

        # 2. SymbolCards (depth <= 2, non-external)
        symbol_nodes = self._collect_symbol_nodes(entry, max_depth=2)
        symbol_cards = self._generate_symbol_cards(
            symbol_nodes, entry.symbol, git_commit, generated_at
        )

        # 3. ContextPack
        all_nodes = self._flatten(entry)
        context_pack = self._generate_context_pack(
            entry, all_nodes, git_commit, generated_at
        )

        # 4. Persist
        paths = self._persist(entry_card, symbol_cards, context_pack)

        return entry_card, symbol_cards, context_pack, paths

    # ----- LLM generation ------------------------------------------------

    def _generate_entry_card(
        self,
        entry: CallNode,
        code_hash: str,
        dep_hash: str,
        git_commit: str,
        generated_at: str,
    ) -> EntryCard:
        prompt = build_entry_prompt(entry, self.project_root)
        output = self.pipeline.run_inline(prompt, _EntryOutput)

        return EntryCard(
            id=f"entry.{self._module_name(entry.source.file)}.{entry.symbol}",
            source=entry.source,
            summary=output.summary,
            business_role=output.business_role,
            main_downstream=output.main_downstream,
            version=CardVersion(
                code_hash=code_hash,
                dependency_hash=dep_hash,
                git_commit=git_commit,
                generated_at=generated_at,
            ),
        )

    def _generate_symbol_cards(
        self,
        nodes: list[CallNode],
        flow_name: str,
        git_commit: str,
        generated_at: str,
    ) -> list[SymbolCard]:
        if not nodes:
            return []

        prompt = build_symbol_prompt(nodes, self.project_root, flow_name)
        outputs = self.pipeline.run_inline(prompt, list[_SymbolOutput])

        cards: list[SymbolCard] = []
        for out, node in zip(outputs, nodes):
            code_hash = compute_file_hash(self.project_root / node.source.file)
            dep_hash = compute_dependency_hash(node)
            cards.append(
                SymbolCard(
                    id=out.id,
                    source=node.source,
                    summary=out.summary,
                    semantic_role=out.semantic_role,
                    side_effects=out.side_effects,
                    used_by_flows=out.used_by_flows,
                    reuse_guidance=out.reuse_guidance,
                    version=CardVersion(
                        code_hash=code_hash,
                        dependency_hash=dep_hash,
                        git_commit=git_commit,
                        generated_at=generated_at,
                    ),
                )
            )
        return cards

    def _generate_context_pack(
        self,
        entry: CallNode,
        all_nodes: list[CallNode],
        git_commit: str,
        generated_at: str,
    ) -> ContextPack:
        prompt = build_context_prompt(entry, all_nodes, self.project_root)
        output = self.pipeline.run_inline(prompt, _ContextOutput)

        return ContextPack(
            id=output.id,
            title=output.title,
            flow_summary=output.flow_summary,
            main_entries=output.main_entries,
            main_paths=output.main_paths,
            important_deep_functions=output.important_deep_functions,
            known_pitfalls=output.known_pitfalls,
            related_tests=output.related_tests,
            version=CardVersion(
                code_hash="",
                dependency_hash="",
                git_commit=git_commit,
                generated_at=generated_at,
            ),
        )

    # ----- Tree traversal ------------------------------------------------

    def _collect_symbol_nodes(
        self,
        entry: CallNode,
        max_depth: int,
    ) -> list[CallNode]:
        """Collect non-external, non-entry nodes up to *max_depth*."""
        result: list[CallNode] = []

        def walk(node: CallNode, depth: int) -> None:
            if depth > max_depth:
                return
            if node is not entry and not node.is_external:
                result.append(node)
            for child in node.children:
                walk(child, depth + 1)

        walk(entry, 0)
        return result

    def _flatten(self, node: CallNode) -> list[CallNode]:
        """Return node and all descendants."""
        result = [node]
        for child in node.children:
            result.extend(self._flatten(child))
        return result

    # ----- Persistence ---------------------------------------------------

    def _persist(
        self,
        entry_card: EntryCard,
        symbol_cards: list[SymbolCard],
        context_pack: ContextPack,
    ) -> list[Path]:
        base = self.project_root / ".repograph" / "semantic_memory"
        paths: list[Path] = []

        entry_path = base / "entries" / f"{entry_card.id}.yaml"
        entry_path.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml(entry_card.model_dump(mode="json"), entry_path)
        paths.append(entry_path)

        for sc in symbol_cards:
            sym_path = base / "symbols" / f"{sc.id}.yaml"
            sym_path.parent.mkdir(parents=True, exist_ok=True)
            dump_yaml(sc.model_dump(mode="json"), sym_path)
            paths.append(sym_path)

        cp_path = base / "context_packs" / f"{context_pack.id}.yaml"
        cp_path.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml(context_pack.model_dump(mode="json"), cp_path)
        paths.append(cp_path)

        return paths

    # ----- Utilities -----------------------------------------------------

    @staticmethod
    def _module_name(file_path: str) -> str:
        parts = file_path.replace("\\", "/").split("/")
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)
