"""Data models for reusable_capabilities.yaml index."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EntryPoint(BaseModel):
    """Public entry point for a reusable capability."""

    file_path: str = Field(..., description="File path containing the entry point")
    function_name: str = Field(..., description="Function or method name")
    signature: str = Field(default="", description="Function signature")
    usage_example: str = Field(default="", description="Usage example or snippet")


class Capability(BaseModel):
    """A single reusable capability entry."""

    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Capability name")
    description: str = Field(..., description="Functionality description")
    module_id: str = Field(..., description="Module ID this capability belongs to")
    entry_points: list[EntryPoint] = Field(
        default_factory=list,
        description="Public entry points",
    )
    use_cases: list[str] = Field(
        default_factory=list,
        description="Typical use cases",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Constraints when using this capability",
    )
    related_capabilities: list[str] = Field(
        default_factory=list,
        description="Related capability IDs",
    )


class CapabilityIndex(BaseModel):
    """Root model for reusable_capabilities.yaml."""

    version: str = Field(default="1.0", description="Index format version")
    updated_at: str | None = Field(default=None, description="Last update timestamp (ISO 8601)")
    capabilities: list[Capability] = Field(
        default_factory=list,
        description="Reusable capability entries",
    )
