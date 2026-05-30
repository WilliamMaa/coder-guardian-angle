"""Module resolution: map files to their owning module."""

from __future__ import annotations

from pathlib import Path

from repoctx.models import RepoCtxConfig


class ModuleResolver:
    """Resolves which module a given file belongs to."""

    def __init__(self, config: RepoCtxConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root
        self._module_paths: dict[Path, str] = {}
        for mod in config.modules:
            mod_path = (project_root / mod.path).resolve()
            self._module_paths[mod_path] = mod.name

    def resolve(self, file_path: Path) -> str | None:
        """Return the module name that owns *file_path*, or None.

        A file belongs to a module if its resolved path is inside the
        module's root directory. The longest (most specific) match wins.
        """
        resolved = file_path.resolve()
        best_match: str | None = None
        best_len = 0

        for mod_path, mod_name in self._module_paths.items():
            try:
                resolved.relative_to(mod_path)
            except ValueError:
                continue
            if len(mod_path.parts) > best_len:
                best_len = len(mod_path.parts)
                best_match = mod_name

        return best_match

    def resolve_all(self, files: list[Path]) -> dict[Path, str | None]:
        """Resolve modules for a list of files."""
        return {f: self.resolve(f) for f in files}
