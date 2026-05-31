"""Configuration loading and template generation."""

from __future__ import annotations

from pathlib import Path

from repoctx.models import (
    ModuleDefinition,
    RepoCtxConfig,
)
from repoctx.utils.project import find_project_root
from repoctx.utils.yaml_io import dump_yaml, load_yaml


class ConfigNotFoundError(Exception):
    """Raised when .repoctx.yaml is missing or invalid."""

    pass


def load_config(project_root: Path | str | None = None) -> RepoCtxConfig:
    """Load .repoctx.yaml from the project root.

    If *project_root* is not provided, the root is auto-discovered by searching
    upward from the current working directory for .repoctx.yaml.

    Args:
        project_root: Explicit project root path, or None to auto-discover.

    Returns:
        Validated RepoCtxConfig instance.

    Raises:
        ConfigNotFoundError: If the config file is missing or cannot be parsed.
    """
    root = find_project_root() if project_root is None else Path(project_root).resolve()

    config_path = root / ".repoctx.yaml"
    if not config_path.exists():
        raise ConfigNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Run 'repoctx init' to initialize the project."
        )

    try:
        raw = load_yaml(config_path)
    except Exception as e:
        raise ConfigNotFoundError(f"Failed to load config from {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigNotFoundError(f"Invalid config format in {config_path}: expected mapping")

    cfg = RepoCtxConfig.model_validate(raw)

    # Fallback: read API key from config.ini if still not configured
    if not cfg.get_api_key():
        ini_path = root / "config.ini"
        if ini_path.exists():
            import configparser

            parser = configparser.ConfigParser()
            parser.read(ini_path, encoding="utf-8")
            key = parser.get("DEFAULT", "tencent_cloud_llm_api_key", fallback=None)
            if key:
                cfg.model_provider.api_key = key

    return cfg


def generate_config_template(project_root: Path | str) -> Path:
    """Generate a .repoctx.yaml template in the given project root.

    If the file already exists, a .repoctx.yaml.template is created instead.

    Args:
        project_root: Target project directory.

    Returns:
        Path to the generated template file.
    """
    root = Path(project_root).resolve()
    config_path = root / ".repoctx.yaml"
    template_path = root / ".repoctx.yaml.template"

    target = template_path if config_path.exists() else config_path

    default = RepoCtxConfig(
        project_name="my-project",
        language="python",
        framework="django",
        modules=[
            ModuleDefinition(name="backend", path="backend", type="backend"),
            ModuleDefinition(name="frontend", path="frontend", type="frontend"),
        ],
    )

    dump_yaml(default.model_dump(mode="json", exclude_none=True), target)
    return target
