"""Experiment monitor thread.

A daemon thread that polls a nohup-launched process. When the process exits,
it waits for file flush, performs light analysis, optional LLM analysis,
persists an ExperimentRun, and sends notifications.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repoctx.models.experiment import (
    ExperimentContract,
    ExperimentRun,
    LightAnalysis,
    LLMAnalysis,
    ResultFile,
)
from repoctx.utils.project import get_repograph_dir
from repoctx.utils.yaml_io import dump_yaml

logger = logging.getLogger("repoctx.experiments.monitor")

# Configurable defaults (could be overridden from .repoctx.yaml later)
_POLL_INTERVAL = 5.0          # seconds
_POST_EXIT_WAIT = 30.0        # seconds
_MAX_NOHUP_SIZE_MB = 50       # safety cap for reading nohup


class ExperimentMonitor(threading.Thread):
    """Background monitor for a single experiment run."""

    def __init__(
        self,
        contract: ExperimentContract,
        nohup_path: Path,
        pid: int,
        output_dir: Path,
        project_root: Path,
        cmd: str,
        notify: bool = False,
        poll_interval: float = _POLL_INTERVAL,
        post_exit_wait: float = _POST_EXIT_WAIT,
    ) -> None:
        super().__init__(daemon=True)
        self.contract = contract
        self.nohup_path = Path(nohup_path)
        self.pid = pid
        self.output_dir = Path(output_dir)
        self.project_root = Path(project_root)
        self.cmd = cmd
        self.notify = notify
        self.poll_interval = poll_interval
        self.post_exit_wait = post_exit_wait

        self.started_at = datetime.now(timezone.utc)
        self.run_id = f"{contract.id}.{self.started_at.strftime('%Y%m%d_%H%M%S')}"
        self.runs_dir = get_repograph_dir(self.project_root) / "experiments" / "runs"
        self.runs_dir.mkdir(parents=True, exist_ok=True)

        # Write a running stub immediately so exp ps can find it
        self._write_stub()

    def run(self) -> None:
        """Monitor loop: poll until process exits, then analyze and persist."""
        logger.info("[%s] Monitor started for PID %d", self.run_id, self.pid)

        # Poll until process dies
        while self._is_alive(self.pid):
            time.sleep(self.poll_interval)

        logger.info("[%s] PID %d has exited. Waiting %.0fs for file flush...",
                    self.run_id, self.pid, self.post_exit_wait)
        time.sleep(self.post_exit_wait)

        # Read nohup
        nohup_text = self._read_nohup()

        # Light analysis
        from repoctx.experiments.light_analyzer import light_analyze
        light_result = light_analyze(nohup_text, self.contract)
        logger.info("[%s] Light analysis: %s", self.run_id, light_result.status)

        # Read result files
        from repoctx.experiments.result_reader import read_results
        result_files = read_results(light_result.hints, self.contract, self.output_dir)
        logger.info("[%s] Result files found: %d", self.run_id, len(result_files))

        # LLM analysis (best-effort)
        llm_result = LLMAnalysis()
        try:
            from repoctx.experiments.llm_analyzer import LLMExperimentAnalyzer
            analyzer = LLMExperimentAnalyzer(self.project_root)
            llm_result = analyzer.analyze(
                nohup_text=nohup_text,
                result_files=result_files,
                contract=self.contract,
                light_result=light_result,
            )
            logger.info("[%s] LLM analysis complete", self.run_id)
        except Exception as e:
            logger.warning("[%s] LLM analysis failed: %s", self.run_id, e)
            llm_result = LLMAnalysis(
                status="unknown",
                summary=f"LLM analysis failed: {e}",
            )

        # Build ExperimentRun
        ended_at = datetime.now(timezone.utc)
        duration = (ended_at - self.started_at).total_seconds()

        run = ExperimentRun(
            id=self.run_id,
            contract_id=self.contract.id,
            cmd=self.cmd,
            pid=self.pid,
            nohup_path=str(self.nohup_path),
            output_dir=str(self.output_dir),
            started_at=self.started_at,
            ended_at=ended_at,
            duration_seconds=duration,
            light_analysis=light_result,
            llm_analysis=llm_result,
            result_files=result_files,
        )

        # Persist
        run_path = self.runs_dir / f"{self.run_id}.yaml"
        dump_yaml(run.to_yaml_dict(), run_path)
        logger.info("[%s] ExperimentRun persisted to %s", self.run_id, run_path)

        # Notify (best-effort)
        if self.notify:
            try:
                from repoctx.experiments.notifier import SlackNotifier
                notifier = SlackNotifier(self.project_root)
                notifier.send(run)
                run.notified = True
                # Re-persist with notified=True
                dump_yaml(run.to_yaml_dict(), run_path)
                logger.info("[%s] Notification sent", self.run_id)
            except Exception as e:
                logger.warning("[%s] Notification failed: %s", self.run_id, e)

        logger.info("[%s] Monitor finished", self.run_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_alive(pid: int) -> bool:
        """Check whether a process is still running."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def _write_stub(self) -> None:
        """Persist a minimal 'running' stub so exp ps can discover active runs."""
        from repoctx.utils.yaml_io import dump_yaml

        stub = ExperimentRun(
            id=self.run_id,
            contract_id=self.contract.id,
            cmd=self.cmd,
            pid=self.pid,
            nohup_path=str(self.nohup_path),
            output_dir=str(self.output_dir),
            started_at=self.started_at,
            light_analysis=LightAnalysis(status="running"),
        )
        run_path = self.runs_dir / f"{self.run_id}.yaml"
        dump_yaml(stub.to_yaml_dict(), run_path)
        logger.info("[%s] Running stub written to %s", self.run_id, run_path)

    def _read_nohup(self) -> str:
        """Read the nohup log, capped to a safe size."""
        if not self.nohup_path.exists():
            return ""
        try:
            size = self.nohup_path.stat().st_size
            max_bytes = _MAX_NOHUP_SIZE_MB * 1024 * 1024
            if size > max_bytes:
                # Read last max_bytes
                with open(self.nohup_path, "rb") as f:
                    f.seek(-max_bytes, 2)
                    return f.read().decode("utf-8", errors="ignore")
            return self.nohup_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            logger.warning("[%s] Failed to read nohup: %s", self.run_id, e)
            return ""
