"""Refresh engine for semantic memory cards.

Scans the ``.repograph/semantic_memory/`` directory, detects stale cards by
comparing stored ``code_hash`` values with current file contents, and
orchestrates incremental re-generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from repoctx.semantic_memory.engine import SemanticDigestEngine
from repoctx.semantic_memory.versioning import compute_file_hash
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.semantic_memory")


@dataclass
class StaleReport:
    """Summary of cards whose ``code_hash`` no longer matches the source file."""

    stale_entries: list[str] = field(default_factory=list)
    stale_symbols: list[str] = field(default_factory=list)


class RefreshEngine:
    """Detect stale cards and re-generate them incrementally."""

    def __init__(self, project_root: Path | str) -> None:
        self.project_root = Path(project_root).resolve()
        self._base = self.project_root / ".repograph" / "semantic_memory"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def find_stale(self) -> StaleReport:
        """Return a report of all stale cards.

        A card is stale when the SHA256 hash stored in its ``version.code_hash``
        field differs from the hash of the current source file on disk.
        """
        report = StaleReport()

        entries_dir = self._base / "entries"
        if entries_dir.exists():
            for f in entries_dir.glob("*.yaml"):
                try:
                    raw = load_yaml(f)
                    source_file = raw.get("source", {}).get("file")
                    stored_hash = raw.get("version", {}).get("code_hash", "")
                    cid = raw.get("id", f.stem)
                    if source_file and stored_hash:
                        current_hash = compute_file_hash(
                            self.project_root / source_file
                        )
                        if current_hash != stored_hash:
                            report.stale_entries.append(cid)
                except Exception:
                    continue

        symbols_dir = self._base / "symbols"
        if symbols_dir.exists():
            for f in symbols_dir.glob("*.yaml"):
                try:
                    raw = load_yaml(f)
                    source_file = raw.get("source", {}).get("file")
                    stored_hash = raw.get("version", {}).get("code_hash", "")
                    cid = raw.get("id", f.stem)
                    if source_file and stored_hash:
                        current_hash = compute_file_hash(
                            self.project_root / source_file
                        )
                        if current_hash != stored_hash:
                            report.stale_symbols.append(cid)
                except Exception:
                    continue

        return report

    def refresh_affected(
        self,
        engine: SemanticDigestEngine,
    ) -> tuple[int, list[str]]:
        """Re-generate stale cards and any entries that depend on stale symbols.

        Args:
            engine: A ready-to-use ``SemanticDigestEngine`` instance.

        Returns:
            ``(refreshed_count, messages)`` where *messages* is a list of human
            readable status lines.
        """
        report = self.find_stale()

        if not report.stale_entries and not report.stale_symbols:
            return 0, ["All cards are fresh. Nothing to refresh."]

        # Collect (file, symbol) tuples that need a re-digest
        entries_to_refresh: set[tuple[str, str]] = set()

        # 1. Stale entries directly
        for entry_id in report.stale_entries:
            info = self._entry_source(entry_id)
            if info:
                entries_to_refresh.add(info)

        # 2. Stale symbols -> find entries that reference them
        for sym_id in report.stale_symbols:
            for file_path, symbol in self._entries_referencing(sym_id):
                entries_to_refresh.add((file_path, symbol))

        # 3. Refresh each unique entry
        refreshed = 0
        messages: list[str] = []
        for file_path, symbol in sorted(entries_to_refresh):
            if not file_path or not symbol:
                continue
            logger.info("Refreshing entry: %s::%s", file_path, symbol)
            try:
                engine.digest(
                    file_path,
                    target_symbols=[symbol],
                    max_depth=3,
                    force=True,
                )
                refreshed += 1
                messages.append(f"Refreshed {file_path}::{symbol}")
            except Exception as e:
                msg = f"FAILED {file_path}::{symbol}: {e}"
                messages.append(msg)
                logger.error(msg)

        # Also report stale symbols that were not covered by any entry refresh
        covered_symbols = set()
        for file_path, symbol in entries_to_refresh:
            entry_id = self._guess_entry_id(file_path, symbol)
            covered_symbols.update(self._entry_downstream_symbols(entry_id))

        for sym_id in report.stale_symbols:
            if sym_id not in covered_symbols:
                messages.append(
                    f"NOTICE {sym_id} is stale but no entry references it. "
                    f"Run 'repoctx digest-entry <file>' manually to refresh."
                )

        return refreshed, messages

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _entry_source(self, entry_id: str) -> tuple[str, str] | None:
        """Return ``(file_path, symbol)`` for an existing EntryCard."""
        path = self._base / "entries" / f"{entry_id}.yaml"
        if not path.exists():
            return None
        try:
            raw = load_yaml(path)
            src = raw.get("source", {})
            return src.get("file"), src.get("symbol")
        except Exception:
            return None

    def _entries_referencing(self, sym_id: str) -> set[tuple[str, str]]:
        """Find all entries whose ``main_downstream`` includes *sym_id*."""
        result: set[tuple[str, str]] = set()
        entries_dir = self._base / "entries"
        if not entries_dir.exists():
            return result

        # sym_id looks like "symbol.module.function"
        # main_downstream stores "module.function"
        parts = sym_id.split(".")
        if len(parts) < 2:
            return result
        downstream_ref = ".".join(parts[1:])
        symbol_name = parts[-1]

        for f in entries_dir.glob("*.yaml"):
            try:
                raw = load_yaml(f)
                downstream = raw.get("main_downstream", [])
                if downstream_ref in downstream or any(
                    d.endswith(f".{symbol_name}") or d == symbol_name
                    for d in downstream
                ):
                    src = raw.get("source", {})
                    result.add((src.get("file"), src.get("symbol")))
            except Exception:
                continue

        return result

    def _guess_entry_id(self, file_path: str, symbol: str) -> str:
        """Reconstruct the likely entry id from file + symbol."""
        parts = file_path.replace("\\", "/").split("/")
        if parts[-1].endswith(".py"):
            parts[-1] = parts[-1][:-3]
        module = ".".join(parts)
        return f"entry.{module}.{symbol}"

    def _entry_downstream_symbols(self, entry_id: str) -> set[str]:
        """Return the set of symbol ids referenced by an entry card."""
        path = self._base / "entries" / f"{entry_id}.yaml"
        if not path.exists():
            return set()
        try:
            raw = load_yaml(path)
            downstream = raw.get("main_downstream", [])
            return {f"symbol.{d}" for d in downstream}
        except Exception:
            return set()
