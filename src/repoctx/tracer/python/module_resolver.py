"""Map Python module paths to file system paths."""

from __future__ import annotations

from pathlib import Path


class ModulePathResolver:
    """Map Python module paths to file system paths."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def resolve(self, module_path: str) -> Path | None:
        """Convert 'backend.credits.services' to a file Path."""
        relative = module_path.replace(".", "/")
        candidates = [
            self.project_root / f"{relative}.py",
            self.project_root / relative / "__init__.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None
