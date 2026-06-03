"""Light-weight nohup analysis without LLM.

Heuristic keyword matching to determine experiment status and extract
result-file references.
"""

from __future__ import annotations

import re
from typing import Any

from repoctx.models.experiment import ExperimentContract, LightAnalysis


# Error signals (ordered by priority)
_ERROR_PATTERNS: list[tuple[str, str]] = [
    ("CUDA out of memory", "oom"),
    ("OOM", "oom"),
    ("Segmentation fault", "crashed"),
    ("Traceback (most recent call last)", "failed"),
    ("Killed", "killed"),
]

# Completion signals
_COMPLETION_KEYWORDS: list[str] = [
    "Done",
    "Complete",
    "Finished",
    "Simulation ended",
    "Training complete",
    "Execution finished",
]

# Regex to find result-file references in nohup output
_FILE_REF_RE = re.compile(
    r"(?:saved|written|output|results?)\s+(?:to|at|in)\s+[\"']?([^\s\"'\n]+)",
    re.IGNORECASE,
)


def light_analyze(nohup_text: str, contract: ExperimentContract) -> LightAnalysis:
    """Quick heuristic analysis of nohup output.

    Args:
        nohup_text: Full content of the nohup log file.
        contract: The experiment contract (used for context, not for rules).

    Returns:
        LightAnalysis with status and hints.
    """
    status = "unknown"
    hints: list[str] = []

    # 1. Check error signals (highest priority)
    for pattern, err_status in _ERROR_PATTERNS:
        if pattern in nohup_text:
            status = err_status
            hints.append(_hint_for_status(err_status))
            break

    # 2. Check completion signals (only if no error found)
    if status == "unknown":
        if any(kw in nohup_text for kw in _COMPLETION_KEYWORDS):
            status = "completed"

    # 3. Extract result-file references
    file_refs = _FILE_REF_RE.findall(nohup_text)
    for ref in file_refs:
        hints.append(f"Result file referenced: {ref}")

    return LightAnalysis(status=status, hints=hints)


def _hint_for_status(status: str) -> str:
    mapping: dict[str, str] = {
        "oom": "CUDA OOM detected",
        "crashed": "Segmentation fault",
        "failed": "Python exception",
        "killed": "Process killed (likely OOM by system)",
    }
    return mapping.get(status, f"Status: {status}")
