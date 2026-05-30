"""LLM call logging utilities."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class LLMCallLogger:
    """Log LLM requests and responses to a file (API key is never logged)."""

    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_file = log_dir / "llm_calls.log"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        prompt_summary: str,
        response_summary: str,
        duration_ms: float,
        model: str,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """Append a single log entry.

        Args:
            prompt_summary: Short description of the prompt (first 200 chars).
            response_summary: Short description of the response (first 200 chars).
            duration_ms: Request duration in milliseconds.
            model: Model identifier used.
            success: Whether the call succeeded.
            error: Error message if the call failed.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "prompt_summary": prompt_summary[:200],
            "response_summary": response_summary[:200],
        }
        if error:
            entry["error"] = error

        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
