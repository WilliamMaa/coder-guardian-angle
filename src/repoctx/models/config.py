"""Data models for .repoctx.yaml project configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ModuleDefinition(BaseModel):
    """Definition of a project module."""

    name: str = Field(..., description="Module name")
    path: str = Field(..., description="Module root directory path")
    type: str = Field(..., description="Module type: frontend, backend, shared, service, utils, test, etc.")


class ModelProviderConfig(BaseModel):
    """Configuration for the LLM model provider (Tencent MaaS)."""

    api_key: str | None = Field(
        default=None,
        description="API key for the model provider. Can be overridden by REPOCTX_TENCENT_API_KEY env var.",
    )
    base_url: str = Field(
        default="https://tokenhub.tencentmaas.com/v1",
        description="Base URL for the model provider API",
    )
    model: str = Field(
        default="deepseek-v4-flash-202605",
        description="Model identifier to use for completions",
    )
    timeout: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Request timeout in seconds",
    )


class RepoCtxConfig(BaseModel):
    """Root configuration model for .repoctx.yaml."""

    model_config = {"protected_namespaces": ()}

    project_name: str = Field(..., description="Project name")
    version: str = Field(default="0.1.0", description="RepoCtx Guard config format version")
    language: str = Field(..., description="Primary programming language")
    framework: str = Field(..., description="Primary framework")
    scan_paths: list[str] = Field(default=["."], description="Directories to scan")
    exclude_paths: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".repograph",
            "*.egg-info",
            "*/migrations/*",
            "db/migrate/*",
        ],
        description="Patterns to exclude from scanning",
    )
    modules: list[ModuleDefinition] = Field(default_factory=list, description="Module definitions")
    rules_file: str = Field(
        default=".repograph/rules/project_rules.yaml",
        description="Path to project rules file",
    )
    protected_core_file: str = Field(
        default=".repograph/protected_core.yaml",
        description="Path to protected core index file",
    )
    reusable_capabilities_file: str = Field(
        default=".repograph/reusable_capabilities.yaml",
        description="Path to reusable capabilities index file",
    )
    experiment_dir: str = Field(
        default=".repograph/experiments",
        description="Directory for experiment memory storage",
    )
    model_provider: ModelProviderConfig = Field(
        default_factory=ModelProviderConfig,
        description="LLM model provider configuration",
    )

    @field_validator("scan_paths", "exclude_paths", mode="before")
    @classmethod
    def _ensure_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        if isinstance(v, list):
            return v
        raise ValueError("Expected string or list of strings")

    def get_api_key(self) -> str | None:
        """Return API key from env var or config file, preferring env var."""
        import os

        env_key = os.environ.get("REPOCTX_TENCENT_API_KEY")
        if env_key:
            return env_key
        return self.model_provider.api_key

    def resolved_experiment_dir(self, project_root: Path) -> Path:
        """Return absolute path to experiment directory."""
        path = Path(self.experiment_dir)
        if not path.is_absolute():
            path = project_root / path
        return path
