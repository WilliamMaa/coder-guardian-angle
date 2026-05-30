"""Safe YAML read/write utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class YAMLError(Exception):
    """Raised when YAML parsing or writing fails."""

    pass


def load_yaml(path: Path) -> Any:
    """Load and parse a YAML file safely.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed Python object (dict, list, etc.).

    Raises:
        YAMLError: If the file does not exist or cannot be parsed.
    """
    if not path.exists():
        raise YAMLError(f"YAML file not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise YAMLError(f"Failed to parse YAML from {path}: {e}") from e
    except OSError as e:
        raise YAMLError(f"Failed to read {path}: {e}") from e


def dump_yaml(data: Any, path: Path) -> None:
    """Write data to a YAML file safely.

    Args:
        data: Python object to serialize.
        path: Target file path. Parent directories are created if needed.

    Raises:
        YAMLError: If writing fails.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
                width=120,
            )
    except OSError as e:
        raise YAMLError(f"Failed to write YAML to {path}: {e}") from e
