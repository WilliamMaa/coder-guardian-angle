"""Slack notification for experiment completion."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from repoctx.models.experiment import ExperimentRun
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import load_yaml

logger = logging.getLogger("repoctx.experiments.notifier")

_MAX_BLOCKS_PER_MESSAGE = 10
_MAX_MESSAGE_LEN = 2800

_STATUS_EMOJI = {
    "completed": "✅",
    "failed": "❌",
    "oom": "💥",
    "crashed": "💥",
    "killed": "⚠️",
    "unknown": "❓",
}


class NotifierError(Exception):
    """Raised when notification setup fails."""

    pass


class SlackNotifier:
    """Send experiment completion reports to Slack via webhook."""

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()
        self.webhook_url: str | None = None
        self.on_events: list[str] = []
        self._load_config()

    def _load_config(self) -> None:
        """Read Slack webhook from .repoctx.yaml."""
        config_path = self.project_root / ".repoctx.yaml"
        if not config_path.exists():
            return
        try:
            data = load_yaml(config_path)
        except Exception:
            return

        notifications = data.get("notifications", {}) if isinstance(data, dict) else {}
        slack_cfg = notifications.get("slack", {})
        raw_url = slack_cfg.get("webhook_url", "")
        if raw_url:
            self.webhook_url = os.path.expandvars(raw_url)
        self.on_events = slack_cfg.get("on_events", ["completed", "failed", "crashed", "oom"])

    def send(self, run: ExperimentRun) -> None:
        """Send notification if enabled and event matches."""
        if not self.webhook_url:
            raise NotifierError("Slack webhook URL not configured in .repoctx.yaml")

        status = run.light_analysis.status
        if status not in self.on_events:
            logger.info("Status '%s' not in on_events %s; skipping notification.", status, self.on_events)
            return

        import requests

        blocks = self._build_blocks(run)
        messages = self._chunk_blocks(blocks)

        for i, msg_blocks in enumerate(messages):
            payload = {
                "text": f"Experiment Report ({i+1}/{len(messages)})",
                "blocks": msg_blocks,
            }
            try:
                resp = requests.post(self.webhook_url, json=payload, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Slack notification failed: %s", e)
                raise NotifierError(f"Slack notification failed: {e}") from e

    def _build_blocks(self, run: ExperimentRun) -> list[dict[str, Any]]:
        """Build Slack Block Kit blocks from an ExperimentRun."""
        emoji = _STATUS_EMOJI.get(run.light_analysis.status, "❓")
        duration_str = ""
        if run.duration_seconds is not None:
            m, s = divmod(int(run.duration_seconds), 60)
            h, m = divmod(m, 60)
            duration_str = f"{h}h {m}m {s}s" if h else f"{m}m {s}s"

        blocks: list[dict[str, Any]] = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} [{run.contract_id}] Experiment Complete",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Status:*\n{run.light_analysis.status}"},
                    {"type": "mrkdwn", "text": f"*Duration:*\n{duration_str or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Run ID:*\n`{run.id}`"},
                    {"type": "mrkdwn", "text": f"*PID:*\n{run.pid}"},
                ],
            },
        ]

        if run.light_analysis.hints:
            blocks.append({"type": "divider"})
            hints_text = "\n".join(f"• {h}" for h in run.light_analysis.hints)
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Hints:*\n{hints_text}"},
            })

        if run.result_files:
            blocks.append({"type": "divider"})
            files_text = "\n".join(f"• `{Path(rf.path).name}` ({rf.source})" for rf in run.result_files)
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Result Files:*\n{files_text}"},
            })

        if run.llm_analysis.summary:
            blocks.append({"type": "divider"})
            summary = run.llm_analysis.summary
            if len(summary) > 500:
                summary = summary[:497] + "..."
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*LLM Summary:*\n{summary}"},
            })

        return blocks

    def _chunk_blocks(self, blocks: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Split blocks into messages that fit Slack limits."""
        messages: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_len = 0

        for block in blocks:
            block_text = block.get("text", {}).get("text", "")
            if not block_text:
                block_text = block.get("text", "")
            block_len = len(block_text)

            if current_len + block_len > _MAX_MESSAGE_LEN and current:
                messages.append(current)
                current = [block]
                current_len = block_len
            else:
                current.append(block)
                current_len += block_len

            if len(current) >= _MAX_BLOCKS_PER_MESSAGE:
                messages.append(current)
                current = []
                current_len = 0

        if current:
            messages.append(current)

        return messages if messages else [blocks]
