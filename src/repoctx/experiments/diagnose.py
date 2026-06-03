"""Experiment diagnosis: compare runs and detect regressions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repoctx.models.experiment import ExperimentRun
from repoctx.utils.project import get_repograph_dir
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.experiments.diagnose")


class DiagnoseError(Exception):
    """Raised when diagnosis fails."""

    pass


@dataclass
class DiagnosisReport:
    """Human-readable diagnosis report."""

    contract_id: str
    compared_runs: list[str] = field(default_factory=list)
    markdown: str = ""

    def format(self) -> str:
        return self.markdown


class DiagnoseEngine:
    """Compare experiment runs and produce diagnosis reports."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.runs_dir = get_repograph_dir(self.project_root) / "experiments" / "runs"

    def diagnose(
        self,
        contract_id: str,
        compare_recent_success_num: int = 1,
    ) -> DiagnosisReport:
        """Diagnose the latest run against recent successful runs.

        Args:
            contract_id: Contract to diagnose.
            compare_recent_success_num: How many recent successful runs to compare.

        Returns:
            DiagnosisReport with markdown content.
        """
        runs = self._load_runs_for_contract(contract_id)
        if not runs:
            raise DiagnoseError(f"No runs found for contract '{contract_id}'.")

        latest = runs[0]
        success_runs = [r for r in runs if r.light_analysis.status == "completed"]
        baseline_runs = success_runs[:compare_recent_success_num]

        lines: list[str] = [
            f"# Diagnosis: {contract_id}",
            "",
            f"**Latest run:** `{latest.id}`  ",
            f"Status: {latest.light_analysis.status}  ",
            f"Duration: {_fmt_duration(latest.duration_seconds)}  ",
            f"Started: {latest.started_at or 'N/A'}",
            "",
        ]

        if not baseline_runs:
            lines.append("_No successful runs found for comparison._")
        else:
            lines.append(f"## Comparison against {len(baseline_runs)} recent successful run(s)")
            lines.append("")

            for baseline in baseline_runs:
                lines.append(f"### Baseline: `{baseline.id}`")
                lines.append(f"- Duration: {_fmt_duration(baseline.duration_seconds)}")
                lines.append(f"- Result files: {len(baseline.result_files)}")
                if baseline.llm_analysis.extracted_metrics:
                    for m in baseline.llm_analysis.extracted_metrics:
                        lines.append(f"  - {m.name}: {m.value}")
                lines.append("")

            # Simple trend: duration delta
            if latest.duration_seconds and baseline_runs[0].duration_seconds:
                delta = latest.duration_seconds - baseline_runs[0].duration_seconds
                pct = (delta / baseline_runs[0].duration_seconds) * 100
                direction = "slower" if delta > 0 else "faster"
                lines.append(f"**Duration delta:** {abs(delta):.1f}s ({abs(pct):.1f}% {direction}) vs baseline")
                lines.append("")

        # Issues from latest run
        if latest.llm_analysis.issues:
            lines.append("## Issues from latest run")
            for issue in latest.llm_analysis.issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Recommendations
        if latest.llm_analysis.recommendations:
            lines.append("## Recommendations")
            for rec in latest.llm_analysis.recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        else:
            lines.append("## Recommendations")
            lines.append("- No recommendations recorded.")
            lines.append("")

        return DiagnosisReport(
            contract_id=contract_id,
            compared_runs=[r.id for r in baseline_runs],
            markdown="\n".join(lines),
        )

    def _load_runs_for_contract(self, contract_id: str) -> list[ExperimentRun]:
        """Load all runs for a contract, newest first."""
        runs: list[ExperimentRun] = []
        if not self.runs_dir.exists():
            return runs
        for path in sorted(self.runs_dir.glob("*.yaml"), reverse=True):
            try:
                data = load_yaml(path)
                run = ExperimentRun.from_yaml_dict(data)
                if run.contract_id == contract_id:
                    runs.append(run)
            except Exception:
                continue
        return runs


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "N/A"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s" if h else f"{m}m {s}s"
