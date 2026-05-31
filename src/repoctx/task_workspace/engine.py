"""Task workspace engine: create, export, validate.

A TaskWorkspace lives under ``.repograph/tasks/<task_id>/`` and contains the
accepted understanding, change plan, out-of-scope list, and frozen assumptions
for a single engineering task.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repoctx.llm.pipeline import PromptPipeline
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import dump_yaml, load_yaml

logger = logging.getLogger("repoctx.task_workspace")


class TaskWorkspaceError(Exception):
    """Raised when task workspace operations fail."""

    pass


@dataclass
class ValidationResult:
    """Result of validating a task workspace against current changes."""

    passed: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines: list[str] = []
        if self.passed and not self.violations and not self.warnings:
            lines.append("Validation passed. No violations found.")
            return "\n".join(lines)
        if self.violations:
            lines.append("Validation FAILED:")
            for v in self.violations:
                lines.append(f"  ✗ {v}")
        if self.warnings:
            lines.append("Warnings:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.passed and (self.warnings or not self.violations):
            lines.append("\nNo hard violations — task constraints satisfied.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_task_id(name: str) -> str:
    """Convert a human task name to a safe directory name with timestamp."""
    safe = re.sub(r"[^\w\s-]", "", name).strip().lower()
    safe = re.sub(r"[-\s]+", "_", safe)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{safe}_{ts}"


def _parse_entry_ref(ref: str) -> tuple[str, str]:
    """Parse ``file.py::symbol`` into ``(file_path, symbol)``."""
    if "::" in ref:
        parts = ref.split("::", 1)
    else:
        raise TaskWorkspaceError(
            f"Invalid entry reference: {ref!r}. "
            "Expected format: 'file.py::symbol_name'"
        )
    return parts[0], parts[1]


def _module_name(file_path: str) -> str:
    """Convert ``backend/credits/views.py`` → ``backend.credits.views``."""
    parts = file_path.replace("\\", "/").split("/")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _entry_card_path(project_root: Path, file_path: str, symbol: str) -> Path | None:
    """Return the path to an existing entry card, or None."""
    module = _module_name(file_path)
    candidates = [
        f"entry.{module}.{symbol}.yaml",
    ]
    # Flat-file fallback for root-level modules
    if "/" not in file_path.replace("\\", "/"):
        candidates.append(f"entry.{symbol}.yaml")

    base = project_root / ".repograph" / "semantic_memory" / "entries"
    for cand in candidates:
        p = base / cand
        if p.exists():
            return p
    return None


def _context_pack_path(project_root: Path, symbol: str) -> Path | None:
    """Return the path to an existing context pack, or None."""
    base = project_root / ".repograph" / "semantic_memory" / "context_packs"
    candidate = base / f"context.{symbol}.yaml"
    return candidate if candidate.exists() else None


def _load_card(path: Path) -> dict[str, Any] | None:
    """Safely load a YAML card."""
    try:
        return load_yaml(path)
    except Exception:
        return None


def _get_git_diff(project_root: Path, name_only: bool = True) -> str:
    """Run ``git diff`` and return stdout."""
    cmd = ["git", "diff", "--name-only" if name_only else ""]
    cmd = [c for c in cmd if c]
    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout
    except FileNotFoundError:
        return ""


def _extract_changed_files(diff: str) -> list[str]:
    """Parse ``git diff --name-only`` output."""
    return [line.strip() for line in diff.splitlines() if line.strip()]


def _build_accepted_understanding_prompt(
    task_name: str,
    entry_ref: str,
    entry_card: dict[str, Any],
    context_pack: dict[str, Any] | None,
) -> str:
    """Assemble the LLM prompt for *accepted_understanding.md*."""
    import json

    entry_json = json.dumps(entry_card, indent=2, ensure_ascii=False)
    ctx_json = (
        json.dumps(context_pack, indent=2, ensure_ascii=False)
        if context_pack
        else "None (context pack not available)"
    )

    return (
        "You are a senior staff engineer. A coding task is about to start.\n"
        "Your job is to produce an **Accepted Understanding** document that\n"
        "becomes the single source of truth for what this task is, what it\n"
        "will change, and what must NOT change.\n\n"
        f"Task name: {task_name}\n"
        f"Entry point: {entry_ref}\n\n"
        "--- Entry Card ---\n"
        f"{entry_json}\n\n"
        "--- Context Pack ---\n"
        f"{ctx_json}\n\n"
        "Generate a markdown document with exactly these sections:\n\n"
        "## 1. Task Goal\n"
        "What is the business/technical goal?\n\n"
        "## 2. Change Scope\n"
        "Which files and functions are expected to be modified?\n\n"
        "## 3. Out of Scope\n"
        "What files, modules, or behaviours must NOT be touched? Be explicit.\n\n"
        "## 4. Frozen Assumptions\n"
        "What assumptions about the system must remain true after this task?\n"
        "(e.g. 'The credit balance must never go negative',\n"
        "'API response format must remain backward compatible')\n\n"
        "## 5. Key Dependencies\n"
        "What other parts of the system does this task depend on or affect?\n\n"
        "## 6. Known Pitfalls\n"
        "What should the implementer be careful about?\n\n"
        "Requirements:\n"
        "- Be specific. Name actual files and functions where possible.\n"
        "- Out of scope and frozen assumptions are the most important sections.\n"
        "- Use markdown only. Do NOT wrap in JSON or code blocks.\n"
        "- If you are unsure about a scope boundary, state the uncertainty.\n"
    )


def _fallback_accepted_understanding(
    task_name: str,
    entry_ref: str,
    entry_card: dict[str, Any],
) -> str:
    """Generate a basic accepted_understanding when the LLM call fails."""
    summary = entry_card.get("summary", "Unknown")
    source_file = entry_card.get("source", {}).get("file", "Unknown")
    return (
        f"# Accepted Understanding: {task_name}\n\n"
        f"**Entry point:** `{entry_ref}`  \n"
        f"**Source file:** `{source_file}`\n\n"
        "## 1. Task Goal\n\n"
        f"{task_name}\n\n"
        "## 2. Change Scope\n\n"
        "TBD — fill in after reviewing the entry card and context pack.\n\n"
        "## 3. Out of Scope\n\n"
        "TBD — list files/modules that must not be modified.\n\n"
        "## 4. Frozen Assumptions\n\n"
        "TBD — list invariants that must be preserved.\n\n"
        "## 5. Key Dependencies\n\n"
        f"Entry function summary: {summary}\n\n"
        "## 6. Known Pitfalls\n\n"
        "TBD — list common mistakes when modifying this flow.\n"
    )


def _generate_accepted_understanding(
    pipeline: PromptPipeline,
    task_name: str,
    entry_ref: str,
    entry_card: dict[str, Any],
    context_pack: dict[str, Any] | None,
) -> str:
    """Call the LLM to generate *accepted_understanding.md*."""
    prompt = _build_accepted_understanding_prompt(
        task_name, entry_ref, entry_card, context_pack
    )
    try:
        raw = pipeline.client.chat_completion_with_retry(
            [{"role": "user", "content": prompt}]
        )
        return raw.strip()
    except Exception as e:
        logger.error("LLM call failed for accepted_understanding: %s", e)
        return _fallback_accepted_understanding(task_name, entry_ref, entry_card)


def _extract_active_files(
    entry_card: dict[str, Any],
    context_pack: dict[str, Any] | None,
) -> list[str]:
    """Build the list of files that are part of this task."""
    files: set[str] = set()

    src = entry_card.get("source", {})
    if src.get("file"):
        files.add(src["file"])

    if context_pack:
        for ref in context_pack.get("important_deep_functions", []):
            f = ref.get("file")
            if f:
                files.add(f)

    return sorted(files)


# ---------------------------------------------------------------------------
# TaskWorkspace
# ---------------------------------------------------------------------------


class TaskWorkspace:
    """A single task workspace under ``.repograph/tasks/<task_id>/``."""

    def __init__(self, project_root: Path, task_id: str) -> None:
        self.project_root = project_root.resolve()
        self.task_id = task_id
        self.task_root = self.project_root / ".repograph" / "tasks" / task_id

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def create(
        cls,
        project_root: Path,
        task_name: str,
        entry_ref: str,
        pipeline: PromptPipeline,
    ) -> TaskWorkspace:
        """Create a new task workspace and populate it.

        Args:
            project_root: Project root directory.
            task_name: Human-readable task name.
            entry_ref: Entry point reference (``file.py::symbol``).
            pipeline: LLM pipeline for generating *accepted_understanding.md*.

        Returns:
            The created :class:`TaskWorkspace`.

        Raises:
            TaskWorkspaceError: If the workspace already exists or the entry
                card cannot be found.
        """
        task_id = _sanitize_task_id(task_name)
        workspace = cls(project_root, task_id)

        if workspace.task_root.exists():
            raise TaskWorkspaceError(
                f"Task workspace already exists: {workspace.task_root}"
            )

        file_path, symbol = _parse_entry_ref(entry_ref)

        entry_card_path = _entry_card_path(project_root, file_path, symbol)
        if entry_card_path is None:
            raise TaskWorkspaceError(
                f"Entry card not found for {entry_ref}. "
                f"Run 'repoctx digest-entry {file_path}' first."
            )
        entry_card = _load_card(entry_card_path)
        if entry_card is None:
            raise TaskWorkspaceError(
                f"Entry card exists but could not be parsed: {entry_card_path}"
            )

        context_pack_path = _context_pack_path(project_root, symbol)
        context_pack = _load_card(context_pack_path) if context_pack_path else None

        # Directory structure
        workspace.task_root.mkdir(parents=True, exist_ok=True)
        (workspace.task_root / "session_notes").mkdir(exist_ok=True)

        # task_intent.md
        intent_lines = [
            f"# Task Intent: {task_name}",
            "",
            f"**Entry point:** `{entry_ref}`",
            "",
            f"**Created:** {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Description",
            "",
            task_name,
            "",
        ]
        (workspace.task_root / "task_intent.md").write_text(
            "\n".join(intent_lines), encoding="utf-8"
        )

        # active_files.yaml
        active_files = _extract_active_files(entry_card, context_pack)
        dump_yaml({"files": active_files}, workspace.task_root / "active_files.yaml")

        # accepted_understanding.md (LLM-generated)
        accepted_md = _generate_accepted_understanding(
            pipeline, task_name, entry_ref, entry_card, context_pack
        )
        (workspace.task_root / "accepted_understanding.md").write_text(
            accepted_md, encoding="utf-8"
        )

        # Stub files
        dump_yaml({"items": []}, workspace.task_root / "out_of_scope.yaml")
        dump_yaml({"assumptions": []}, workspace.task_root / "frozen_assumptions.yaml")
        (workspace.task_root / "change_plan.md").write_text(
            "# Change Plan\n\n"
            "TBD — describe the planned changes here.\n",
            encoding="utf-8",
        )

        return workspace

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export(self) -> str:
        """Export the task workspace as a single unified markdown document."""
        sections: list[str] = []

        sections.append(f"# Task Export: {self.task_id}\n")

        # task_intent.md
        intent_path = self.task_root / "task_intent.md"
        if intent_path.exists():
            sections.append(intent_path.read_text(encoding="utf-8"))
            sections.append("\n---\n")

        # accepted_understanding.md
        understanding_path = self.task_root / "accepted_understanding.md"
        if understanding_path.exists():
            sections.append(understanding_path.read_text(encoding="utf-8"))
            sections.append("\n---\n")

        # change_plan.md
        plan_path = self.task_root / "change_plan.md"
        if plan_path.exists():
            sections.append(plan_path.read_text(encoding="utf-8"))
            sections.append("\n---\n")

        # out_of_scope.yaml
        oos_path = self.task_root / "out_of_scope.yaml"
        if oos_path.exists():
            oos = load_yaml(oos_path)
            sections.append("## Out of Scope\n")
            items = oos.get("items", [])
            if items:
                for item in items:
                    sections.append(f"- {item}")
            else:
                sections.append("_Nothing explicitly declared out of scope._")
            sections.append("\n---\n")

        # frozen_assumptions.yaml
        fa_path = self.task_root / "frozen_assumptions.yaml"
        if fa_path.exists():
            fa = load_yaml(fa_path)
            sections.append("## Frozen Assumptions\n")
            assumptions = fa.get("assumptions", [])
            if assumptions:
                for a in assumptions:
                    sections.append(f"- {a}")
            else:
                sections.append("_No frozen assumptions recorded._")
            sections.append("\n---\n")

        # active_files.yaml
        af_path = self.task_root / "active_files.yaml"
        if af_path.exists():
            af = load_yaml(af_path)
            sections.append("## Active Files\n")
            files = af.get("files", [])
            if files:
                for f in files:
                    sections.append(f"- `{f}`")
            else:
                sections.append("_No active files recorded._")
            sections.append("\n---\n")

        # Session notes
        notes_dir = self.task_root / "session_notes"
        if notes_dir.exists():
            notes = sorted(notes_dir.glob("*.md"))
            if notes:
                sections.append("## Session Notes\n")
                for note in notes:
                    sections.append(f"\n### {note.name}\n")
                    sections.append(note.read_text(encoding="utf-8"))

        return "\n".join(sections)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------

    def validate(self, diff: str | None = None) -> ValidationResult:
        """Validate current working-tree changes against task constraints.

        Checks:
        1. Diff does not modify files listed in ``out_of_scope.yaml``.
        2. (MVP only warns) Diff exists while ``frozen_assumptions.yaml`` is non-empty.

        Args:
            diff: Git diff text.  If *None*, auto-detect via ``git diff --name-only``.
        """
        if diff is None:
            diff = _get_git_diff(self.project_root, name_only=True)

        violations: list[str] = []
        warnings: list[str] = []

        changed_files = _extract_changed_files(diff)

        # 1. out_of_scope check
        oos_path = self.task_root / "out_of_scope.yaml"
        if oos_path.exists():
            oos = load_yaml(oos_path)
            out_of_scope_items = oos.get("items", [])
            for changed_file in changed_files:
                for oos_item in out_of_scope_items:
                    item_norm = oos_item.rstrip("/")
                    if changed_file == oos_item or changed_file.startswith(
                        item_norm + "/"
                    ):
                        violations.append(
                            f"Modified out-of-scope file: {changed_file} "
                            f"(matches rule: {oos_item})"
                        )

        # 2. frozen_assumptions warning (MVP — semantic check deferred to Phase 6)
        fa_path = self.task_root / "frozen_assumptions.yaml"
        if fa_path.exists():
            fa = load_yaml(fa_path)
            assumptions = fa.get("assumptions", [])
            if assumptions and diff.strip():
                warnings.append(
                    f"{len(assumptions)} frozen assumption(s) exist. "
                    "Review manually that the diff does not violate them."
                )

        # 3. Validate diff is non-empty (cosmetic)
        if not diff.strip():
            warnings.append("No uncommitted changes detected. Nothing to validate.")

        return ValidationResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )
