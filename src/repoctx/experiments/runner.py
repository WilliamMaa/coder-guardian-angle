"""Experiment runner: nohup launch and PID tracking."""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from repoctx.utils.project import get_repograph_dir

logger = logging.getLogger("repoctx.experiments.runner")


class RunnerError(Exception):
    """Raised when experiment launch fails."""

    pass


class ExperimentRunner:
    """Launch experiments via nohup and track PIDs."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.nohup_dir = get_repograph_dir(self.project_root) / "experiments" / "nohup_logs"
        self.nohup_dir.mkdir(parents=True, exist_ok=True)

    def nohup_start(
        self,
        cmd: str,
        contract_id: str,
        output_dir: Path | None = None,
    ) -> tuple[int, Path]:
        """Launch a command via nohup and return (pid, nohup_log_path).

        Args:
            cmd: The shell command to execute.
            contract_id: Used to name the nohup log file.
            output_dir: Explicit output directory (optional).

        Returns:
            (pid, nohup_log_path)
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        nohup_name = f"{contract_id}.{timestamp}.nohup"
        nohup_path = self.nohup_dir / nohup_name

        # Build the nohup command
        # Use shell=True so the user can pass complex commands with flags
        shell_cmd = f"nohup {cmd} > {nohup_path} 2>&1 & echo $!"

        logger.info("Launching experiment: %s", cmd)
        logger.info("Nohup log: %s", nohup_path)

        try:
            result = subprocess.run(
                shell_cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
        except OSError as e:
            raise RunnerError(f"Failed to launch experiment: {e}") from e

        stdout = result.stdout.strip()
        if not stdout:
            raise RunnerError("Failed to capture PID from nohup launch.")

        try:
            pid = int(stdout.splitlines()[-1].strip())
        except ValueError as e:
            raise RunnerError(f"Unexpected nohup output: {stdout}") from e

        logger.info("Experiment launched with PID %d", pid)
        return pid, nohup_path
