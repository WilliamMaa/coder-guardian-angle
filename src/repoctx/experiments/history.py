"""Experiment history query and listing."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from repoctx.models.experiment import ExperimentRun
from repoctx.utils.project import get_repograph_dir
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.experiments.history")


class HistoryError(Exception):
    """Raised when history operations fail."""

    pass


@dataclass
class HistoryEntry:
    """A lightweight view of a run for listing."""

    run_id: str
    contract_id: str
    status: str
    started_at: str
    duration: str
    result_count: int


class HistoryEngine:
    """List and filter experiment runs."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.runs_dir = get_repograph_dir(self.project_root) / "experiments" / "runs"

    def list_runs(
        self,
        contract_id: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
    ) -> list[HistoryEntry]:
        """List runs, optionally filtered by contract and status."""
        entries: list[HistoryEntry] = []
        if not self.runs_dir.exists():
            return entries

        for path in sorted(self.runs_dir.glob("*.yaml"), reverse=True):
            try:
                data = load_yaml(path)
                run = ExperimentRun.from_yaml_dict(data)
            except Exception:
                continue

            if contract_id and run.contract_id != contract_id:
                continue
            if status_filter and run.light_analysis.status != status_filter:
                continue

            started = run.started_at.strftime("%Y-%m-%d %H:%M") if run.started_at else "N/A"
            duration = ""
            if run.duration_seconds is not None:
                m, s = divmod(int(run.duration_seconds), 60)
                h, m = divmod(m, 60)
                duration = f"{h}h{m}m{s}s" if h else f"{m}m{s}s"

            entries.append(
                HistoryEntry(
                    run_id=run.id,
                    contract_id=run.contract_id,
                    status=run.light_analysis.status,
                    started_at=started,
                    duration=duration,
                    result_count=len(run.result_files),
                )
            )

            if len(entries) >= limit:
                break

        return entries

    def get_run(self, run_id: str) -> ExperimentRun:
        """Load a single run by its full ID."""
        path = self.runs_dir / f"{run_id}.yaml"
        if not path.exists():
            raise HistoryError(f"Run '{run_id}' not found.")
        data = load_yaml(path)
        return ExperimentRun.from_yaml_dict(data)

    def list_contracts_with_runs(self) -> list[str]:
        """Return contract IDs that have at least one run."""
        ids: set[str] = set()
        if not self.runs_dir.exists():
            return []
        for path in self.runs_dir.glob("*.yaml"):
            try:
                data = load_yaml(path)
                ids.add(data.get("contract_id", ""))
            except Exception:
                continue
        return sorted(ids)
