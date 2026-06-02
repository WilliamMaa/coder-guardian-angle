"""LLM-driven refactoring suggestion engine.

Reads any Python module and asks the LLM to analyze its architecture:
which functions belong here, which should be extracted, whether any
existing symbols can be reused, and general structural improvements.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repoctx.llm.client import LLMClient
from repoctx.llm.pipeline import PromptPipeline
from repoctx.semantic_memory.engine import SemanticDigestEngine
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import dump_yaml, load_yaml

logger = logging.getLogger("repoctx.refactor")


@dataclass
class RefactorSuggestion:
    """A single function-level refactoring suggestion."""

    name: str
    current_file: str
    is_entry: bool
    should_move: bool
    target_module: str = ""
    reason: str = ""
    reuse_existing: str = ""
    action: str = ""  # e.g. "Move to utils/messaging.py"


@dataclass
class RefactorReport:
    """Full report for a file."""

    file: str
    markdown: str = ""

    def format_markdown(self) -> str:
        return self.markdown


class RefactorSuggestEngine:
    """Generate refactoring suggestions for any Python module."""

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()

        # Load existing symbol cards for reuse context
        self._symbols = self._load_symbols()

        # LLM pipeline
        try:
            digest_engine = SemanticDigestEngine(self.project_root)
            self.pipeline = digest_engine.pipeline
        except Exception as e:
            raise RuntimeError(
                "LLM not configured. Set API key in .repoctx.yaml or config.ini."
            ) from e

    def suggest(self, file_path: str) -> RefactorReport:
        """Analyze a single file and return refactoring suggestions.

        Args:
            file_path: Relative path from project root.

        Returns:
            :class:`RefactorReport` with detailed markdown analysis.
        """
        abs_path = self.project_root / file_path
        if not abs_path.exists():
            raise FileNotFoundError(f"File not found: {abs_path}")

        source = abs_path.read_text(encoding="utf-8")
        logger.info("Refactor-suggest analyzing %s (%d chars)", file_path, len(source))

        prompt = self._build_prompt(file_path, source)

        raw = self.pipeline.client.chat_completion_with_retry(
            [{"role": "user", "content": prompt}]
        )

        return RefactorReport(file=file_path, markdown=raw)

    def _load_symbols(self) -> list[dict[str, Any]]:
        """Load existing SymbolCards for reuse context."""
        from repoctx.utils.project import get_repograph_dir

        symbols_dir = get_repograph_dir(self.project_root) / "semantic_memory" / "symbols"
        if not symbols_dir.exists():
            return []
        results: list[dict[str, Any]] = []
        for path in symbols_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                if data and data.get("card_type") == "symbol":
                    results.append(
                        {
                            "id": data.get("id", ""),
                            "summary": data.get("summary", ""),
                            "semantic_role": data.get("semantic_role", []),
                            "reuse_guidance": data.get("reuse_guidance", {}),
                        }
                    )
            except Exception:
                continue
        return results[:20]

    def _load_semantic_memory_for_file(self, file_path: str) -> dict[str, Any]:
        """Load entry cards, symbol cards, and context packs for a specific file."""
        from repoctx.utils.project import get_repograph_dir

        repograph = get_repograph_dir(self.project_root)
        memory: dict[str, Any] = {"entries": [], "symbols": [], "contexts": []}

        entries_dir = repograph / "semantic_memory" / "entries"
        if entries_dir.exists():
            for path in entries_dir.glob("*.yaml"):
                try:
                    data = load_yaml(path)
                    src = data.get("source", {})
                    if src.get("file", "") == file_path:
                        memory["entries"].append(
                            {
                                "id": data.get("id", ""),
                                "summary": data.get("summary", ""),
                                "business_role": data.get("business_role", []),
                                "main_downstream": data.get("main_downstream", []),
                            }
                        )
                except Exception:
                    continue

        symbols_dir = repograph / "semantic_memory" / "symbols"
        if symbols_dir.exists():
            for path in symbols_dir.glob("*.yaml"):
                try:
                    data = load_yaml(path)
                    src = data.get("source", {})
                    if src.get("file", "") == file_path:
                        memory["symbols"].append(
                            {
                                "id": data.get("id", ""),
                                "summary": data.get("summary", ""),
                                "semantic_role": data.get("semantic_role", []),
                                "reuse_guidance": data.get("reuse_guidance", {}),
                            }
                        )
                except Exception:
                    continue

        ctx_dir = repograph / "semantic_memory" / "context_packs"
        if ctx_dir.exists():
            for path in ctx_dir.glob("*.yaml"):
                try:
                    data = load_yaml(path)
                    entries = data.get("main_entries", [])
                    if memory["entries"]:
                        entry_ids = {e["id"] for e in memory["entries"]}
                        if any(eid in entry_ids for eid in entries):
                            memory["contexts"].append(
                                {
                                    "id": data.get("id", ""),
                                    "title": data.get("title", ""),
                                    "flow_summary": data.get("flow_summary", ""),
                                }
                            )
                except Exception:
                    continue

        return memory

    def _load_constitution(self) -> dict[str, Any]:
        """Load engineering constitution rules."""
        from repoctx.utils.project import get_repograph_dir

        path = get_repograph_dir(self.project_root) / "guards" / "engineering_constitution.yaml"
        if not path.exists():
            return {}
        try:
            return load_yaml(path)
        except Exception:
            return {}

    def _build_prompt(self, file_path: str, source: str) -> str:
        """Assemble the LLM prompt with semantic memory + constitution context."""
        # 1. Semantic memory for this file
        memory = self._load_semantic_memory_for_file(file_path)
        memory_block = ""
        if memory["entries"] or memory["symbols"] or memory["contexts"]:
            memory_block = "### Semantic memory (from digest-entry)\n"
            for e in memory["entries"]:
                memory_block += f"- **Entry** `{e['id']}`: {e['summary']}\n"
                if e.get("business_role"):
                    memory_block += f"  - Business role: {', '.join(e['business_role'])}\n"
                if e.get("main_downstream"):
                    memory_block += f"  - Downstream: {', '.join(e['main_downstream'])}\n"
            for s in memory["symbols"]:
                memory_block += f"- **Symbol** `{s['id']}`: {s['summary']}\n"
            for c in memory["contexts"]:
                memory_block += f"- **Context** `{c['id']}`: {c['title']} — {c['flow_summary']}\n"
            memory_block += "\n"
        else:
            memory_block = (
                "> ⚠️ **Note:** This file has NOT been digested yet. "
                f"Run `repoctx digest-entry {file_path}` first for richer analysis.\n\n"
            )

        # 2. Engineering constitution rules
        constitution = self._load_constitution()
        rules_block = ""
        if constitution and constitution.get("rules"):
            rules_block = "### Engineering constitution rules\n"
            for rule_id, cfg in constitution["rules"].items():
                if isinstance(cfg, dict) and cfg.get("enabled", True):
                    desc = cfg.get("description", "")
                    sev = cfg.get("severity", "error")
                    rules_block += f"- **{rule_id}** (`{sev}`)"
                    if desc:
                        rules_block += f" — {desc}"
                    rules_block += "\n"
                    if rule_id == "views_only_entries" and cfg.get("view_file_patterns"):
                        rules_block += f"  - Applies to: {cfg['view_file_patterns']}\n"
            rules_block += "\n"

        # 3. Existing project symbols for reuse
        symbol_block = ""
        if self._symbols:
            symbol_block = "### Existing reusable symbols in the project\n"
            for sym in self._symbols:
                symbol_block += f"- `{sym['id']}`: {sym['summary']}\n"
            symbol_block += "\n"

        return (
            "You are a senior Python architect conducting a **code review with teeth**.\n"
            "You MUST give concrete, actionable refactoring advice. "
            "Saying 'looks good' or 'no changes needed' is NOT acceptable.\n"
            "CRITICAL: Every recommendation you make — including new function names, extracted helpers, "
            "and any refactored code — MUST fully comply with the Engineering Constitution rules listed below. "
            "Do NOT suggest names or patterns that violate any enabled rule.\n\n"
            "## Analysis requirements (MUST address ALL of these)\n\n"
            "1. **Dead / ineffective code** — unused variables, unreachable branches, redundant imports,\n"
            "   duplicated logic, or anything that can be deleted without changing behavior.\n"
            "2. **Function granularity** — any function over 30 lines or with nested control flow > 3 levels\n"
            "   MUST be flagged for splitting. Suggest exact拆分方案 (what to extract, what to name it).\n"
            "   **All suggested new names MUST comply with the Engineering Constitution rules (e.g. if a rule forbids underscore-prefixed functions, do NOT suggest `_foo` names).**\n"
            "3. **Reuse analysis** — if any function's logic overlaps with an existing project symbol,\n"
            "   say exactly which symbol to reuse and how to refactor the call site.\n"
            "4. **Constitution compliance** — check every function against the engineering constitution rules.\n"
            "   If a view file contains helpers, say which ones and where to move them.\n"
            "   **When proposing extracted helpers or new functions, ensure their names and signatures do NOT violate any rule.**\n"
            "5. **Architecture smell** — tight coupling to external services, mixed abstraction levels,\n"
            "   missing error handling, hard-coded values, or import cycles.\n\n"
            "## Output format\n\n"
            "Respond in **Markdown** with these exact sections:\n\n"
            "### 1. Overall Assessment (1-2 sentences, be harsh if warranted)\n"
            "### 2. Dead / Ineffective Code (list each with line numbers if possible)\n"
            "### 3. Functions to Split (for each: current lines, what to extract, new names; new names MUST obey constitution rules)\n"
            "### 4. Reuse Recommendations (map local functions → existing symbols)\n"
            "### 5. Constitution Violations (if any rules are broken, be specific; also confirm that ALL proposed new names are compliant)\n"
            "### 6. Architecture Smells (coupling, abstraction, error handling, etc.)\n"
            "### 7. Action Priority (ordered list: what to do first, second, third)\n\n"
            f"## Target file: `{file_path}`\n\n"
            f"{memory_block}"
            f"{rules_block}"
            f"{symbol_block}"
            "## Source code\n\n"
            "```python\n"
            f"{source}\n"
            "```\n"
        )
