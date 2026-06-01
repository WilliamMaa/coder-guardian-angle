"""Tests for project initialization logic."""

from __future__ import annotations

from pathlib import Path

import pytest

from repoctx.initialization import (
    InitializationError,
    _DEFAULT_STUB_FILES,
    _REPGRAPH_DIRECTORIES,
    init_project,
)
from repoctx.utils.project import get_repograph_dir
from repoctx.utils.yaml_io import load_yaml


class TestInitProject:
    """Unit tests for ``init_project``."""

    def test_creates_repoctx_yaml(self, tmp_path: Path) -> None:
        """A fresh init should create .repoctx.yaml."""
        created = init_project(tmp_path)
        config_path = tmp_path / ".repoctx.yaml"
        assert config_path in created
        assert config_path.exists()
        raw = load_yaml(config_path)
        assert raw["project_name"] == "my-project"
        assert raw["language"] == "python"
        assert raw["framework"] == "django"

    def test_custom_project_meta(self, tmp_path: Path) -> None:
        """Custom name/language/framework are written to the config."""
        init_project(
            tmp_path,
            project_name="awesome-api",
            language="typescript",
            framework="nextjs",
        )
        raw = load_yaml(tmp_path / ".repoctx.yaml")
        assert raw["project_name"] == "awesome-api"
        assert raw["language"] == "typescript"
        assert raw["framework"] == "nextjs"

    def test_creates_all_directories(self, tmp_path: Path) -> None:
        """All expected .repograph/ subdirectories should exist."""
        init_project(tmp_path)
        repograph_dir = get_repograph_dir(tmp_path)
        for rel in _REPGRAPH_DIRECTORIES:
            assert (repograph_dir / rel).is_dir()

    def test_creates_default_stub_files(self, tmp_path: Path) -> None:
        """Default stub YAML files should be created."""
        created = init_project(tmp_path)
        repograph_dir = get_repograph_dir(tmp_path)
        for rel in _DEFAULT_STUB_FILES:
            file_path = repograph_dir / rel
            assert file_path.exists()

    def test_skips_existing_stub_files(self, tmp_path: Path) -> None:
        """Existing stub files must not be overwritten."""
        repograph_dir = get_repograph_dir(tmp_path)
        stub_path = repograph_dir / "guards" / "structure_rules.yaml"
        stub_path.parent.mkdir(parents=True)
        stub_path.write_text("rules:\n  - existing\n")

        created = init_project(tmp_path)
        assert stub_path not in created
        raw = load_yaml(stub_path)
        assert raw["rules"] == ["existing"]

    def test_raises_when_already_initialized(self, tmp_path: Path) -> None:
        """Without --force, init on an existing project must raise."""
        init_project(tmp_path)
        with pytest.raises(InitializationError, match="already initialized"):
            init_project(tmp_path)

    def test_force_overwrites_config(self, tmp_path: Path) -> None:
        """--force should overwrite .repoctx.yaml while keeping stubs."""
        init_project(tmp_path, project_name="old-name")
        created = init_project(tmp_path, project_name="new-name", force=True)

        config_path = tmp_path / ".repoctx.yaml"
        assert config_path in created
        raw = load_yaml(config_path)
        assert raw["project_name"] == "new-name"

        # Stub files created by the first run must still exist
        repograph_dir = get_repograph_dir(tmp_path)
        for rel in _DEFAULT_STUB_FILES:
            assert (repograph_dir / rel).exists()


class TestCliInit:
    """CLI-level tests for the ``init`` command."""

    def test_init_command_exists(self) -> None:
        """The ``init`` sub-command should be registered."""
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["init", "--help"])
        assert result.exit_code == 0
        assert "Initialize the current project" in result.output

    def test_init_runs_successfully(self, tmp_path: Path) -> None:
        """A full CLI init should exit 0 and create expected files."""
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            result = runner.invoke(main, ["init"])
            assert result.exit_code == 0, result.output
            assert (Path(fs) / ".repoctx.yaml").exists()
            fs_root = Path(fs)
            repograph_dir = get_repograph_dir(fs_root)
            assert (repograph_dir / "semantic_memory" / "entries").is_dir()

    def test_init_refuses_overwrite(self, tmp_path: Path) -> None:
        """Running init twice without --force should fail."""
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            runner.invoke(main, ["init"])
            result = runner.invoke(main, ["init"])
            assert result.exit_code != 0
            assert "already initialized" in result.output

    def test_init_force_overwrite(self, tmp_path: Path) -> None:
        """Running init --force should succeed even when already initialized."""
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path) as fs:
            runner.invoke(main, ["init", "--project-name", "first"])
            result = runner.invoke(main, ["init", "--force", "--project-name", "second"])
            assert result.exit_code == 0, result.output
            raw = load_yaml(Path(fs) / ".repoctx.yaml")
            assert raw["project_name"] == "second"
