"""Data models for Experiment Intelligence Agent.

Pydantic models for ExperimentContract and ExperimentRun,
aligned with EXPERIMENT_AGENT_DESIGN_v4.md.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Sub-models for ExperimentContract
# ---------------------------------------------------------------------------


class OutputFile(BaseModel):
    """An expected output file described in a contract."""

    pattern: str = Field(..., description="Path pattern, may contain {output_dir}")
    note: str = Field(default="", description="Human-readable description")


class LogDestination(BaseModel):
    """Where experiment logs are written."""

    type: str = Field(default="nohup", description="Log type: nohup, tensorboard, etc.")
    path: str = Field(default="", description="Log directory or file path")


class CliArg(BaseModel):
    """A CLI argument expected by the experiment entry point."""

    name: str = Field(..., description="Argument name, e.g. --epoch")
    default: str | None = Field(default=None, description="Default value if any")
    help_text: str = Field(default="", description="Argument description")


class ExpectedBehavior(BaseModel):
    """Success / failure criteria for an experiment."""

    success_criteria: list[str] = Field(default_factory=list)
    failure_signs: list[str] = Field(default_factory=list)


class ContractBody(BaseModel):
    """The substantive part of an experiment contract."""

    purpose: str = Field(default="", description="What this experiment does")
    output_files: list[OutputFile] = Field(default_factory=list)
    log_destinations: list[LogDestination] = Field(default_factory=list)
    cli_args: list[CliArg] = Field(default_factory=list)
    expected_behavior: ExpectedBehavior = Field(default_factory=ExpectedBehavior)


class ExperimentContract(BaseModel):
    """Persistent contract that describes an experiment."""

    id: str = Field(..., description="Unique contract identifier")
    entry_file: str = Field(..., description="Path to entry script, relative to project root")
    entry_symbol: str = Field(default="main", description="Entry function or class method")
    status: str = Field(default="draft", description="draft | reviewed | deprecated")
    contract: ContractBody = Field(default_factory=ContractBody)

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML dumping."""
        return self.model_dump(mode="json")

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> ExperimentContract:
        """Load from a plain dict read from YAML."""
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Sub-models for ExperimentRun
# ---------------------------------------------------------------------------


class LightAnalysis(BaseModel):
    """Fast heuristic analysis of nohup output (no LLM)."""

    status: str = Field(default="unknown", description="unknown | completed | failed | oom | crashed | killed")
    hints: list[str] = Field(default_factory=list)


class ExtractedMetric(BaseModel):
    """A metric extracted by LLM from result files."""

    name: str
    value: str | float | int
    source: str = Field(default="", description="File path or origin")


class LLMAnalysis(BaseModel):
    """Deep analysis produced by LLM after the process exits."""

    status: str = Field(default="unknown")
    summary: str = Field(default="")
    extracted_metrics: list[ExtractedMetric] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ResultFile(BaseModel):
    """A result file that was read during analysis."""

    path: str
    source: str = Field(default="", description="nohup_reference | contract | output_dir_scan")


class ExperimentRun(BaseModel):
    """A single execution of an experiment."""

    id: str = Field(..., description="<contract_id>.<timestamp>")
    contract_id: str = Field(...)
    cmd: str = Field(..., description="The exact command that was executed")
    pid: int | None = Field(default=None)
    nohup_path: str = Field(default="")
    output_dir: str = Field(default="", description="Inferred or explicit output directory")

    # Timing
    started_at: datetime | None = Field(default=None)
    ended_at: datetime | None = Field(default=None)
    duration_seconds: float | None = Field(default=None)

    # Analysis layers
    light_analysis: LightAnalysis = Field(default_factory=LightAnalysis)
    llm_analysis: LLMAnalysis = Field(default_factory=LLMAnalysis)
    result_files: list[ResultFile] = Field(default_factory=list)

    # Notification
    notified: bool = Field(default=False)

    def to_yaml_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML dumping."""
        return self.model_dump(mode="json")

    @classmethod
    def from_yaml_dict(cls, data: dict[str, Any]) -> ExperimentRun:
        """Load from a plain dict read from YAML."""
        return cls.model_validate(data)
