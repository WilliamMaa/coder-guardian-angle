"""Auto module discovery based on project structure and framework."""

from __future__ import annotations

import abc
from pathlib import Path

from repoctx.models import ModuleDefinition

# Directories commonly excluded from module discovery
_EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    ".repograph",
    "migrations",
    "tests",
    "test",
    "docs",
    "scripts",
    "fixtures",
    "assets",
    "dist",
    "build",
}


class BaseDiscoverer(abc.ABC):
    """Base class for framework-specific module discoverers."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    @abc.abstractmethod
    def discover(self) -> list[ModuleDefinition]:
        """Return a list of discovered modules."""
        ...

    def _is_valid_module_dir(self, path: Path) -> bool:
        """Check if a directory looks like a valid module."""
        if not path.is_dir():
            return False
        if path.name.startswith(".") or path.name.startswith("_"):
            return False
        if path.name in _EXCLUDE_DIRS:
            return False
        # Must contain at least one source file (non-test)
        for child in path.iterdir():
            if (
                child.is_file()
                and child.suffix in (".py", ".js", ".ts", ".vue", ".go", ".rs")
                and not child.name.startswith("test_")
                and not child.name.endswith("_test.py")
            ):
                return True
            if child.is_dir() and child.name not in _EXCLUDE_DIRS:
                return True
        return False


class GenericDiscoverer(BaseDiscoverer):
    """Generic discoverer: top-level dirs under project root or src/."""

    def discover(self) -> list[ModuleDefinition]:
        modules: list[ModuleDefinition] = []

        # Prefer src/ if it exists
        src_dir = self.project_root / "src"
        search_roots = [src_dir] if src_dir.exists() else [self.project_root]

        for root in search_roots:
            for child in sorted(root.iterdir()):
                if not self._is_valid_module_dir(child):
                    continue
                rel = child.relative_to(self.project_root).as_posix()
                modules.append(
                    ModuleDefinition(
                        name=child.name,
                        path=rel,
                        type="backend",
                    )
                )

        return modules


class DjangoDiscoverer(BaseDiscoverer):
    """Django discoverer: each app directory containing models.py/views.py/apps.py."""

    def discover(self) -> list[ModuleDefinition]:
        modules: list[ModuleDefinition] = []
        markers = {"models.py", "views.py", "apps.py"}

        # Search up to 2 levels deep for Django apps
        for depth in range(1, 3):
            for path in self.project_root.rglob("*" * depth):
                if not path.is_dir():
                    continue
                if path.name in _EXCLUDE_DIRS:
                    continue
                if any((path / m).exists() for m in markers):
                    rel = path.relative_to(self.project_root).as_posix()
                    # Avoid duplicates from nested discovery
                    if not any(m.path == rel for m in modules):
                        modules.append(
                            ModuleDefinition(
                                name=path.name,
                                path=rel,
                                type="backend",
                            )
                        )

        return modules


class VueDiscoverer(BaseDiscoverer):
    """Vue/Nuxt discoverer: pages, components, composables, stores."""

    def discover(self) -> list[ModuleDefinition]:
        modules: list[ModuleDefinition] = []
        known_dirs = ["pages", "components", "composables", "stores", "views"]

        for name in known_dirs:
            path = self.project_root / name
            if path.exists() and path.is_dir():
                modules.append(
                    ModuleDefinition(
                        name=name,
                        path=name,
                        type="frontend",
                    )
                )

        # Also discover top-level src/ dirs
        src_dir = self.project_root / "src"
        if src_dir.exists():
            for child in sorted(src_dir.iterdir()):
                if self._is_valid_module_dir(child):
                    rel = child.relative_to(self.project_root).as_posix()
                    modules.append(
                        ModuleDefinition(
                            name=child.name,
                            path=rel,
                            type="frontend",
                        )
                    )

        return modules


class FastAPIDiscoverer(BaseDiscoverer):
    """FastAPI/Flask discoverer: api, models, services, routers."""

    def discover(self) -> list[ModuleDefinition]:
        modules: list[ModuleDefinition] = []
        known_dirs = ["api", "models", "services", "routers", "schemas", "core", "db"]

        for name in known_dirs:
            path = self.project_root / name
            if path.exists() and path.is_dir():
                modules.append(
                    ModuleDefinition(
                        name=name,
                        path=name,
                        type="backend",
                    )
                )

        # Fallback to generic if nothing found
        if not modules:
            return GenericDiscoverer(self.project_root).discover()

        return modules


_DISCOVERERS: dict[str, type[BaseDiscoverer]] = {
    "django": DjangoDiscoverer,
    "vue": VueDiscoverer,
    "nuxt": VueDiscoverer,
    "fastapi": FastAPIDiscoverer,
    "flask": FastAPIDiscoverer,
    "generic": GenericDiscoverer,
}


def discover_modules(project_root: Path, framework: str) -> list[ModuleDefinition]:
    """Discover modules for a project based on its framework.

    Args:
        project_root: Absolute path to the project root.
        framework: Framework identifier (django, vue, fastapi, generic, etc.).

    Returns:
        List of discovered modules. May be empty if no modules are found.
    """
    discoverer_cls = _DISCOVERERS.get(framework.lower(), GenericDiscoverer)
    discoverer = discoverer_cls(project_root)
    return discoverer.discover()
