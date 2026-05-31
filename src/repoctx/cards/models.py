"""Data models for semantic memory cards."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CardVersion(BaseModel):
    """Version metadata bound to a specific code state."""

    code_hash: str = Field(..., description="SHA256 of the source file content")
    dependency_hash: str = Field(default="", description="Hash of immediate downstream symbols")
    git_commit: str = Field(default="", description="Git commit SHA at generation time")
    generated_at: str = Field(..., description="ISO 8601 timestamp")
    status: str = Field(default="fresh", description="fresh | stale | deprecated")


class SymbolSource(BaseModel):
    """Source location of a symbol in the codebase."""

    file: str = Field(..., description="Relative file path from project root")
    symbol: str = Field(..., description="Function or class name")
    line_start: int = Field(default=1)
    line_end: int = Field(default=1)


class SemanticCard(BaseModel):
    """Base class for all semantic memory cards."""

    card_type: str = Field(..., description="entry | path | symbol | flow")
    id: str = Field(..., description="Stable card identifier")
    version: CardVersion


class PathBranch(BaseModel):
    """A conditional branch within a business path."""

    summary: str = Field(..., description="What happens on this branch")
    condition: str = Field(default="", description="Trigger condition")


class EntryCard(SemanticCard):
    """Describes what an entry function does from a business perspective."""

    card_type: str = "entry"
    source: SymbolSource
    summary: str = Field(..., description="One-sentence business summary")
    business_role: list[str] = Field(default_factory=list)
    main_downstream: list[str] = Field(
        default_factory=list,
        description="IDs of directly-called symbols",
    )


class PathCard(SemanticCard):
    """Describes a primary business path under an entry point."""

    card_type: str = "path"
    entry: str = Field(..., description="Parent EntryCard.id")
    condition: str = Field(default="", description="When this path is taken")
    steps: list[str] = Field(default_factory=list)
    branches: dict[str, PathBranch] = Field(default_factory=dict)


class ReuseGuidance(BaseModel):
    """Guidance on when and how to reuse a symbol."""

    use_when: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)


class SymbolCard(SemanticCard):
    """Describes the semantic role of a deep function, service, model, or util."""

    card_type: str = "symbol"
    source: SymbolSource
    summary: str = Field(..., description="What this symbol does in project semantics")
    semantic_role: list[str] = Field(default_factory=list)
    side_effects: str = Field(default="none", description="none | read | write | external_call")
    used_by_flows: list[str] = Field(default_factory=list)
    reuse_guidance: ReuseGuidance = Field(default_factory=ReuseGuidance)


class DeepFunctionRef(BaseModel):
    """Reference to an important deep function in a context pack."""

    symbol_id: str
    file: str
    summary: str


class ContextPack(BaseModel):
    """A compressed context document for coders to read."""

    id: str
    title: str
    flow_summary: str = ""
    main_entries: list[str] = Field(default_factory=list)
    main_paths: list[str] = Field(default_factory=list)
    important_deep_functions: list[DeepFunctionRef] = Field(default_factory=list)
    known_pitfalls: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
