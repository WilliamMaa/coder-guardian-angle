"""Semantic digest engine: orchestrate tracing, LLM generation, and persistence."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger("repoctx.semantic_memory")

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
from repoctx.utils.project import find_project_root, get_repograph_dir
from repoctx.utils.yaml_io import dump_yaml, load_yaml


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
        self.repograph_dir = get_repograph_dir(self.project_root)

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
        force: bool = False,
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
        logger.info("Tracing %s (symbols=%s, depth=%d)", file_path, target_symbols, max_depth)
        context = TracerContext(
            project_root=self.project_root,
            max_depth=max_depth,
        )
        tracer = get_tracer(file_path, context)
        tree = tracer.trace(file_path, symbol_names=target_symbols)
        logger.info("Trace complete: %d nodes found", len(tree.all_nodes))

        # The tracer returns a synthetic root when multiple symbols are traced.
        entries = self._extract_entries(tree, file_path)

        all_cards: list[dict] = []
        all_paths: list[Path] = []

        for entry in entries:
            entry_card, symbol_cards, context_pack, paths = self._digest_entry(
                entry, max_depth, force=force
            )
            all_cards.append(entry_card.model_dump(mode="json"))
            all_cards.extend(sc.model_dump(mode="json") for sc in symbol_cards)
            if context_pack is not None:
                all_cards.append(context_pack.model_dump(mode="json"))
            all_paths.extend(paths)

        logger.info("Digest finished: %d cards, %d files written", len(all_cards), len(all_paths))
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
        force: bool = False,
    ) -> tuple[EntryCard, list[SymbolCard], ContextPack | None, list[Path]]:
        """Digest a single entry node and persist its cards incrementally.

        Cards are written to disk as soon as they are generated.  If the
        ContextPack step fails, the EntryCard and SymbolCards already on disk
        are kept.

        When *force* is False and the existing EntryCard's ``code_hash``
        matches the current source file, the entire entry is skipped to avoid
        wasting LLM tokens.
        """
        logger.info("Digesting entry: %s", entry.symbol)

        # Version metadata
        code_hash = compute_file_hash(self.project_root / entry.source.file)
        git_commit = get_git_commit(self.project_root)
        dep_hash = compute_dependency_hash(entry)
        generated_at = datetime.now(timezone.utc).isoformat()
        all_paths: list[Path] = []

        # 1. EntryCard — check freshness, generate + persist immediately
        existing_entry = None if force else self._load_existing_entry_card(entry)
        if existing_entry is not None and existing_entry.version.code_hash == code_hash:
            logger.info("EntryCard is up-to-date (code_hash=%s), skipping LLM", code_hash[:8])
            entry_card = existing_entry
            ep = self._entry_card_path(entry_card)
            all_paths.append(ep)
        else:
            logger.info("Generating EntryCard...")
            entry_card = self._generate_entry_card(
                entry, code_hash, dep_hash, git_commit, generated_at
            )
            logger.info("  → %s", entry_card.id)
            ep = self._persist_entry_card(entry_card)
            all_paths.append(ep)
            logger.info("  Persisted: %s", ep)

        # 2. SymbolCards — check freshness per symbol
        symbol_nodes = self._collect_symbol_nodes(entry, max_depth=2)
        logger.info("Generating SymbolCards (%d symbols)...", len(symbol_nodes))
        symbol_cards: list[SymbolCard] = []
        nodes_to_generate: list[CallNode] = []
        for node in symbol_nodes:
            existing = None if force else self._load_existing_symbol_card(node)
            node_hash = compute_file_hash(self.project_root / node.source.file)
            if existing is not None and existing.version.code_hash == node_hash:
                logger.info("  Symbol %s is up-to-date, skipping", node.symbol)
                symbol_cards.append(existing)
            else:
                nodes_to_generate.append(node)

        if nodes_to_generate:
            new_cards = self._generate_symbol_cards(
                nodes_to_generate, entry.symbol, git_commit, generated_at
            )
            for sc in new_cards:
                logger.info("  → %s", sc.id)
            symbol_cards.extend(new_cards)
            sym_paths = self._persist_symbol_cards(new_cards)
            all_paths.extend(sym_paths)
            for sp in sym_paths:
                logger.info("  Persisted: %s", sp)
        else:
            logger.info("  All symbol cards up-to-date")
            for sc in symbol_cards:
                all_paths.append(self._symbol_card_path(sc))

        # 3. ContextPack — generate + persist, but tolerate failure
        logger.info("Generating ContextPack...")
        all_nodes = self._flatten(entry)
        try:
            context_pack = self._generate_context_pack(
                entry, all_nodes, git_commit, generated_at
            )
            logger.info("  → %s", context_pack.id)
            cp = self._persist_context_pack(context_pack)
            all_paths.append(cp)
            logger.info("  Persisted: %s", cp)
        except Exception as e:
            logger.error("ContextPack generation failed: %s", e)
            context_pack = None

        return entry_card, symbol_cards, context_pack, all_paths

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
        logger.info("Calling LLM for EntryCard (prompt length: %d chars)", len(prompt))
        output = self.pipeline.run_inline(prompt, _EntryOutput)
        logger.info("LLM response received for EntryCard")

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
            logger.info("No symbol nodes to process")
            return []

        prompt = build_symbol_prompt(nodes, self.project_root, flow_name)
        logger.info("Calling LLM for SymbolCards (prompt length: %d chars)", len(prompt))
        outputs = self.pipeline.run_inline(prompt, list[_SymbolOutput])
        logger.info("LLM response received for SymbolCards (%d cards)", len(outputs))

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
        logger.info("Calling LLM for ContextPack (prompt length: %d chars)", len(prompt))
        output = self.pipeline.run_inline(prompt, _ContextOutput)
        logger.info("LLM response received for ContextPack")

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

    def _persist_entry_card(self, entry_card: EntryCard) -> Path:
        path = (
            self.repograph_dir
            / "semantic_memory"
            / "entries"
            / f"{entry_card.id}.yaml"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml(entry_card.model_dump(mode="json"), path)
        return path

    def _persist_symbol_cards(self, symbol_cards: list[SymbolCard]) -> list[Path]:
        paths: list[Path] = []
        for sc in symbol_cards:
            path = (
                self.repograph_dir
                / "semantic_memory"
                / "symbols"
                / f"{sc.id}.yaml"
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            dump_yaml(sc.model_dump(mode="json"), path)
            paths.append(path)
        return paths

    def _persist_context_pack(self, context_pack: ContextPack) -> Path:
        path = (
            self.repograph_dir
            / "semantic_memory"
            / "context_packs"
            / f"{context_pack.id}.yaml"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml(context_pack.model_dump(mode="json"), path)
        return path

    # ----- Existing card helpers -----------------------------------------

    def _entry_card_path(self, entry_card: EntryCard) -> Path:
        return (
            self.repograph_dir
            / "semantic_memory"
            / "entries"
            / f"{entry_card.id}.yaml"
        )

    def _symbol_card_path(self, symbol_card: SymbolCard) -> Path:
        return (
            self.repograph_dir
            / "semantic_memory"
            / "symbols"
            / f"{symbol_card.id}.yaml"
        )

    def _load_existing_entry_card(self, entry: CallNode) -> EntryCard | None:
        module = self._module_name(entry.source.file)
        path = (
            self.repograph_dir
            / "semantic_memory"
            / "entries"
            / f"entry.{module}.{entry.symbol}.yaml"
        )
        if not path.exists():
            return None
        try:
            raw = load_yaml(path)
            return EntryCard.model_validate(raw)
        except Exception:
            return None

    def _load_existing_symbol_card(self, node: CallNode) -> SymbolCard | None:
        module = self._module_name(node.source.file)
        path = (
            self.repograph_dir
            / "semantic_memory"
            / "symbols"
            / f"symbol.{module}.{node.symbol}.yaml"
        )
        if not path.exists():
            return None
        try:
            raw = load_yaml(path)
            return SymbolCard.model_validate(raw)
        except Exception:
            return None

    # ----- Utilities -----------------------------------------------------

    @staticmethod
    def _module_name(file_path: str) -> str:
        parts = file_path.replace("\\", "/").split("/")
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        return ".".join(parts)
