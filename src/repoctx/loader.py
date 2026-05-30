"""Configuration loading and template generation."""

from __future__ import annotations

from pathlib import Path

from repoctx.models import (
    BlockPolicy,
    Capability,
    CapabilityIndex,
    EntryPoint,
    ModuleDefinition,
    ProtectedCore,
    ProtectedCoreIndex,
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
            f"Run 'repoctx scan' to generate a template, or create it manually."
        )

    try:
        raw = load_yaml(config_path)
    except Exception as e:
        raise ConfigNotFoundError(f"Failed to load config from {config_path}: {e}") from e

    if not isinstance(raw, dict):
        raise ConfigNotFoundError(f"Invalid config format in {config_path}: expected mapping")

    return RepoCtxConfig.model_validate(raw)


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


def load_protected_core_index(project_root: Path | str) -> ProtectedCoreIndex:
    """Load the protected core index from the configured path.

    Args:
        project_root: Project root directory.

    Returns:
        ProtectedCoreIndex instance. Returns an empty index if the file
        does not exist, so callers can decide whether to warn or error.
    """
    root = Path(project_root).resolve()
    config = load_config(root)
    path = root / config.protected_core_file

    if not path.exists():
        return ProtectedCoreIndex()

    raw = load_yaml(path)
    if not isinstance(raw, dict):
        return ProtectedCoreIndex()

    return ProtectedCoreIndex.model_validate(raw)


def load_capability_index(project_root: Path | str) -> CapabilityIndex:
    """Load the reusable capability index from the configured path.

    Args:
        project_root: Project root directory.

    Returns:
        CapabilityIndex instance. Returns an empty index if the file
        does not exist.
    """
    root = Path(project_root).resolve()
    config = load_config(root)
    path = root / config.reusable_capabilities_file

    if not path.exists():
        return CapabilityIndex()

    raw = load_yaml(path)
    if not isinstance(raw, dict):
        return CapabilityIndex()

    return CapabilityIndex.model_validate(raw)


def generate_protected_core_template(project_root: Path | str) -> Path:
    """Generate a protected_core.yaml template with sample entries.

    Args:
        project_root: Project root directory.

    Returns:
        Path to the generated file.
    """
    root = Path(project_root).resolve()
    config = load_config(root)
    path = root / config.protected_core_file

    if path.exists():
        return path

    sample = ProtectedCoreIndex(
        version="1.0",
        cores=[
            ProtectedCore(
                id="core-auth",
                name="auth/session/login",
                type="service",
                files=["backend/auth/*.py"],
                modules=["auth"],
                used_by=["free_call", "subscription", "verification_channel"],
                description="Authentication and session management core. Do not modify internals.",
                block_policy=BlockPolicy(
                    default_action="block",
                    required_explanations=[
                        "Why core change is necessary",
                        "Why wrapper/adapter is insufficient",
                    ],
                    required_evidence=["Affected flows list"],
                    require_regression_tests=True,
                    require_rollback_plan=True,
                ),
            ),
        ],
    )

    dump_yaml(sample.model_dump(mode="json", exclude_none=True), path)
    return path


def generate_capability_template(project_root: Path | str) -> Path:
    """Generate a reusable_capabilities.yaml template with sample entries.

    Args:
        project_root: Project root directory.

    Returns:
        Path to the generated file.
    """
    root = Path(project_root).resolve()
    config = load_config(root)
    path = root / config.reusable_capabilities_file

    if path.exists():
        return path

    sample = CapabilityIndex(
        version="1.0",
        capabilities=[
            Capability(
                id="cap-balance-check",
                name="credit balance check",
                description="Get available credit balance for a user.",
                module_id="credits",
                entry_points=[
                    EntryPoint(
                        file_path="backend/credits/services.py",
                        function_name="get_available_balance",
                        signature="def get_available_balance(user_id: str) -> int",
                        usage_example="balance = get_available_balance(user_id)",
                    )
                ],
                use_cases=["Before initiating a paid call", "Before subscription renewal"],
                constraints=["Do not modify this function for domain-specific logic"],
                related_capabilities=[],
            ),
        ],
    )

    dump_yaml(sample.model_dump(mode="json", exclude_none=True), path)
    return path
