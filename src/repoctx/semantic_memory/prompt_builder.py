"""Assemble LLM prompts for semantic card generation.

Each builder function receives a ``CallNode`` (or list of nodes) and the
project root, and returns a fully-formed prompt string ready to be sent to
the LLM.
"""

from __future__ import annotations

from pathlib import Path

from repoctx.tracer.base import CallNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_source(node: CallNode, project_root: Path) -> str:
    """Read the source lines for *node* from disk."""
    path = project_root / node.source.file
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = max(0, node.source.line_start - 1)
    end = node.source.line_end if node.source.line_end > 0 else start + 1
    return "\n".join(lines[start:end])


def _module_name(file_path: str) -> str:
    """Convert ``backend/credits/services.py`` → ``backend.credits.services``."""
    parts = file_path.replace("\\", "/").split("/")
    if parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _format_tree(node: CallNode, depth: int = 0) -> str:
    """Pretty-print a call tree."""
    indent = "  " * depth
    ext = " [external]" if node.is_external else ""
    result = f"{indent}- {node.symbol}{ext}"
    for child in node.children:
        result += "\n" + _format_tree(child, depth + 1)
    return result


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def build_entry_prompt(entry: CallNode, project_root: Path) -> str:
    """Return a prompt that asks the model to generate an EntryCard."""
    source = _read_source(entry, project_root)
    children = "\n".join(
        f"- {c.symbol} ({c.source.file}:{c.source.line_start})"
        for c in entry.children
    ) or "- none"
    module = _module_name(entry.source.file)

    downstream = [
        f'{module}.{c.symbol}'
        for c in entry.children
        if not c.is_external
    ]
    downstream_json = str(downstream).replace("'", '"')

    return (
        "You are a senior software engineer analyzing a Python codebase.\n"
        "Below is the source code of an entry function and its direct callees.\n"
        "Analyze the business purpose and semantic role.\n\n"
        f"Entry function: {entry.symbol}\n"
        f"File: {entry.source.file}\n"
        "Source code:\n"
        "```python\n"
        f"{source}\n"
        "```\n\n"
        "Direct downstream calls:\n"
        f"{children}\n\n"
        "Generate a JSON object with exactly these fields:\n"
        "{\n"
        '  "summary": "One-sentence business description of what this entry '
        'function does",\n'
        '  "business_role": ["semantic role 1", "semantic role 2"],\n'
        f'  "main_downstream": {downstream_json}\n'
        "}\n\n"
        "Requirements:\n"
        "- summary must be concise (1-2 sentences) and business-oriented, "
        "not technical.\n"
        "- business_role should describe what this function represents in the "
        "system (e.g., \"free call start entrypoint\", "
        "\"request validation boundary\").\n"
        '- main_downstream should list IDs of directly-called internal '
        'functions in format "module.function".\n'
    )


def build_symbol_prompt(nodes: list[CallNode], project_root: Path, flow_name: str) -> str:
    """Return a prompt that asks the model to generate SymbolCards in batch."""
    chunks: list[str] = []
    for node in nodes:
        source = _read_source(node, project_root)
        module = _module_name(node.source.file)
        children = [c.symbol for c in node.children if not c.is_external]
        chunks.append(
            f"Function: {module}.{node.symbol}\n"
            f"File: {node.source.file}\n"
            "Source code:\n"
            "```python\n"
            f"{source}\n"
            "```\n"
            f"Direct children: {', '.join(children) if children else 'none'}\n"
            "---"
        )

    funcs_text = "\n".join(chunks)

    return (
        "You are a senior software engineer analyzing a Python codebase.\n"
        "For each function below, analyze its project semantic role and "
        "generate a SymbolCard.\n\n"
        f"These functions are part of the flow: {flow_name}\n\n"
        "Functions:\n"
        f"{funcs_text}\n\n"
        "For each function, generate a SymbolCard with:\n"
        '- id: "symbol.<module>.<function>"\n'
        '- summary: What this symbol does in project semantics (1 sentence)\n'
        '- semantic_role: List of roles '
        '(e.g., ["public read surface", "shared service"])\n'
        '- side_effects: One of "none", "read", "write", "external_call"\n'
        '- used_by_flows: List of flow names that use this symbol\n'
        '- reuse_guidance: { "use_when": [...], "avoid": [...] }\n\n'
        "Generate a JSON array. Each element is a SymbolCard object.\n"
        "Requirements:\n"
        "- Be specific about semantic_role "
        '(e.g., "credit balance read surface" not just "utility function").\n'
        '- side_effects: "write" if it mutates database/state, '
        '"external_call" if it calls external APIs, '
        '"read" if it only reads, "none" if pure logic.\n'
    )


def build_context_prompt(entry: CallNode, all_nodes: list[CallNode], project_root: Path) -> str:
    """Return a prompt that asks the model to generate a ContextPack."""
    source = _read_source(entry, project_root)
    tree_text = _format_tree(entry)

    deep_funcs: list[str] = []
    for node in all_nodes:
        if node == entry or node in entry.children:
            continue
        if not node.is_external:
            module = _module_name(node.source.file)
            deep_funcs.append(f"- {module}.{node.symbol}")
    deep_funcs_text = "\n".join(deep_funcs) if deep_funcs else "- none"

    return (
        "You are a senior software engineer creating a ContextPack for other "
        "engineers. This document should help someone understand a business "
        "flow without reading all the code.\n\n"
        f"Entry function: {entry.symbol}\n"
        f"File: {entry.source.file}\n"
        "Source code:\n"
        "```python\n"
        f"{source}\n"
        "```\n\n"
        "Full call graph:\n"
        f"{tree_text}\n\n"
        "Important deep functions (depth >= 2):\n"
        f"{deep_funcs_text}\n\n"
        "Generate a JSON object with exactly these fields:\n"
        "{\n"
        f'  "id": "context.{entry.symbol}",\n'
        '  "title": "Human-readable flow title",\n'
        '  "flow_summary": "2-3 sentence high-level description of the '
        'business flow",\n'
        f'  "main_entries": ["{entry.symbol}"],\n'
        '  "main_paths": ["Key business path 1", "Key business path 2"],\n'
        '  "important_deep_functions": [\n'
        '    {"symbol_id": "symbol.module.function", '
        '"file": "path/to/file.py", "summary": "What this function does"}\n'
        '  ],\n'
        '  "known_pitfalls": ["Pitfall 1", "Pitfall 2"],\n'
        '  "related_tests": ["Test category 1", "Test category 2"]\n'
        "}\n\n"
        "Requirements:\n"
        "- flow_summary should explain what the flow does from a business "
        "perspective.\n"
        "- main_paths should describe key business paths (success, failure, "
        "edge cases).\n"
        "- important_deep_functions should highlight the most critical "
        "internal functions.\n"
        "- known_pitfalls should warn about common mistakes when modifying "
        "this flow.\n"
        "- related_tests should suggest what kinds of tests cover this flow.\n"
    )
