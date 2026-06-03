"""Read experiment result files on-demand.

Three-tier priority:
1. Files explicitly referenced in nohup output.
2. Files specified in the contract's output_files.
3. Top-level scan of output_dir (non-recursive, capped).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repoctx.models.experiment import ExperimentContract, ResultFile

# File suffixes we consider readable result files
_READABLE_SUFFIXES: set[str] = {
    ".csv",
    ".json",
    ".txt",
    ".log",
    ".yaml",
    ".yml",
    ".md",
}

# Binary suffixes that we note but do not read content for LLM
_BINARY_SUFFIXES: set[str] = {
    ".pt",
    ".pth",
    ".pkl",
    ".ckpt",
}

_MAX_DIR_SCAN = 10


def read_results(
    light_hints: list[str],
    contract: ExperimentContract,
    output_dir: Path,
) -> list[ResultFile]:
    """Collect result files based on hints, contract, and output_dir.

    Args:
        light_hints: Hints produced by light_analyze (e.g. "Result file referenced: ...").
        contract: Experiment contract with output_files patterns.
        output_dir: Inferred or explicit output directory.

    Returns:
        List of ResultFile objects (deduplicated by path).
    """
    seen: set[Path] = set()
    results: list[ResultFile] = []

    # Tier 1: files referenced in nohup output
    for hint in light_hints:
        if hint.startswith("Result file referenced:"):
            ref = hint.replace("Result file referenced:", "").strip()
            path = _resolve_path(ref, output_dir)
            if path and path.exists() and path not in seen:
                seen.add(path)
                results.append(ResultFile(path=str(path), source="nohup_reference"))

    # Tier 2: contract output_files patterns
    for of in contract.contract.output_files:
        pattern = of.pattern
        if "{output_dir}" in pattern:
            pattern = pattern.replace("{output_dir}", str(output_dir))
        path = Path(pattern)
        if not path.is_absolute():
            path = output_dir / path
        if path.exists() and path not in seen:
            seen.add(path)
            results.append(ResultFile(path=str(path), source="contract"))

    # Tier 3: shallow scan of output_dir (only if nothing found yet)
    if not results and output_dir.exists():
        for f in output_dir.iterdir():
            if not f.is_file():
                continue
            if f.suffix in _READABLE_SUFFIXES or f.suffix in _BINARY_SUFFIXES:
                if f not in seen:
                    seen.add(f)
                    results.append(ResultFile(path=str(f), source="output_dir_scan"))
            if len(results) >= _MAX_DIR_SCAN:
                break

    return results


def _resolve_path(ref: str, output_dir: Path) -> Path | None:
    """Resolve a path string from nohup text into an absolute Path."""
    p = Path(ref)
    if p.is_absolute():
        return p
    # Try relative to output_dir first, then to cwd
    candidate = output_dir / p
    if candidate.exists():
        return candidate.resolve()
    if p.exists():
        return p.resolve()
    return candidate  # return anyway so caller can check .exists()
