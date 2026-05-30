"""Data models for protected_core.yaml index."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BlockPolicy(BaseModel):
    """Policy enforced when protected core is modified."""

    default_action: str = Field(
        default="block",
        description="Default action: block, warn, or log",
    )
    required_explanations: list[str] = Field(
        default_factory=list,
        description="List of required explanation items",
    )
    required_evidence: list[str] = Field(
        default_factory=list,
        description="List of required evidence items",
    )
    require_regression_tests: bool = Field(
        default=True,
        description="Whether regression tests are mandatory",
    )
    require_rollback_plan: bool = Field(
        default=True,
        description="Whether rollback plan is mandatory",
    )


class ProtectedCore(BaseModel):
    """A single protected core entry."""

    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    type: str = Field(
        ...,
        description="Core type: service, model, util, api, event, queue, job, client",
    )
    files: list[str] = Field(
        default_factory=list,
        description="File paths or glob patterns belonging to this core",
    )
    modules: list[str] = Field(
        default_factory=list,
        description="Module IDs this core belongs to",
    )
    used_by: list[str] = Field(
        default_factory=list,
        description="Business flows or modules that use this core",
    )
    description: str = Field(..., description="Core responsibility description")
    block_policy: BlockPolicy = Field(
        default_factory=BlockPolicy,
        description="Block policy for this core",
    )


class ProtectedCoreIndex(BaseModel):
    """Root model for protected_core.yaml."""

    version: str = Field(default="1.0", description="Index format version")
    updated_at: str | None = Field(default=None, description="Last update timestamp (ISO 8601)")
    cores: list[ProtectedCore] = Field(default_factory=list, description="Protected core entries")
