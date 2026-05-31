"""Unit tests for configuration system, models, and utilities."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from repoctx.loader import (
    ConfigNotFoundError,
    generate_config_template,
    load_config,
)
from repoctx.models import (
    ModelProviderConfig,
    RepoCtxConfig,
)
from repoctx.utils.project import ProjectRootError, find_project_root
from repoctx.utils.yaml_io import YAMLError, dump_yaml, load_yaml

# ---------------------------------------------------------------------------
# Model validation
# ---------------------------------------------------------------------------


class TestRepoCtxConfig:
    """Tests for RepoCtxConfig Pydantic model."""

    def test_minimal_valid_config(self) -> None:
        cfg = RepoCtxConfig(project_name="test", language="python", framework="django")
        assert cfg.project_name == "test"
        assert cfg.scan_paths == ["."]
        assert cfg.model_provider.model == "deepseek-v4-flash-202605"

    def test_default_exclude_paths(self) -> None:
        cfg = RepoCtxConfig(project_name="x", language="python", framework="django")
        assert ".git" in cfg.exclude_paths
        assert "node_modules" in cfg.exclude_paths

    def test_api_key_from_config(self) -> None:
        cfg = RepoCtxConfig(
            project_name="x",
            language="python",
            framework="django",
            model_provider=ModelProviderConfig(api_key="file-key-456"),
        )
        assert cfg.get_api_key() == "file-key-456"

    def test_scan_paths_string_coercion(self) -> None:
        cfg = RepoCtxConfig(
            project_name="x",
            language="python",
            framework="django",
            scan_paths="src",  # type: ignore[arg-type]
        )
        assert cfg.scan_paths == ["src"]

    def test_invalid_config_missing_required(self) -> None:
        with pytest.raises(ValidationError):
            RepoCtxConfig(project_name="x")  # missing language and framework


# ---------------------------------------------------------------------------
# YAML utilities
# ---------------------------------------------------------------------------


class TestYamlIO:
    """Tests for safe YAML read/write."""

    def test_roundtrip(self, tmp_path: Path) -> None:
        data = {"project_name": "test", "modules": [{"name": "a", "path": "a", "type": "b"}]}
        path = tmp_path / "test.yaml"
        dump_yaml(data, path)
        loaded = load_yaml(path)
        assert loaded == data

    def test_load_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(YAMLError, match="not found"):
            load_yaml(tmp_path / "missing.yaml")

    def test_dump_creates_parents(self, tmp_path: Path) -> None:
        path = tmp_path / "a" / "b" / "c.yaml"
        dump_yaml({"x": 1}, path)
        assert path.exists()


# ---------------------------------------------------------------------------
# Project root discovery
# ---------------------------------------------------------------------------


class TestFindProjectRoot:
    """Tests for project root auto-discovery."""

    def test_finds_marker_in_current_dir(self, tmp_path: Path) -> None:
        marker = tmp_path / ".repoctx.yaml"
        marker.write_text("project_name: test\n")
        found = find_project_root(tmp_path)
        assert found == tmp_path.resolve()

    def test_finds_marker_in_parent(self, tmp_path: Path) -> None:
        marker = tmp_path / ".repoctx.yaml"
        marker.write_text("project_name: test\n")
        sub = tmp_path / "src" / "app"
        sub.mkdir(parents=True)
        found = find_project_root(sub)
        assert found == tmp_path.resolve()

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ProjectRootError, match="Could not find project root"):
            find_project_root(tmp_path)

    def test_from_file_path(self, tmp_path: Path) -> None:
        marker = tmp_path / ".repoctx.yaml"
        marker.write_text("project_name: test\n")
        some_file = tmp_path / "src" / "main.py"
        some_file.parent.mkdir(parents=True)
        some_file.write_text("pass")
        found = find_project_root(some_file)
        assert found == tmp_path.resolve()


# ---------------------------------------------------------------------------
# Configuration loader
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Tests for load_config and template generation."""

    def test_load_valid_config(self, tmp_path: Path) -> None:
        config_path = tmp_path / ".repoctx.yaml"
        dump_yaml(
            {
                "project_name": "demo",
                "language": "python",
                "framework": "django",
                "scan_paths": ["src"],
            },
            config_path,
        )
        cfg = load_config(tmp_path)
        assert cfg.project_name == "demo"
        assert cfg.language == "python"
        assert cfg.scan_paths == ["src"]

    def test_load_missing_config(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigNotFoundError, match="Configuration file not found"):
            load_config(tmp_path)

    def test_generate_config_template(self, tmp_path: Path) -> None:
        path = generate_config_template(tmp_path)
        assert path.exists()
        loaded = load_yaml(path)
        assert loaded["project_name"] == "my-project"

    def test_auto_discover_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        config_path = tmp_path / ".repoctx.yaml"
        dump_yaml(
            {"project_name": "auto", "language": "python", "framework": "fastapi"},
            config_path,
        )
        sub = tmp_path / "backend" / "app"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        cfg = load_config()
        assert cfg.project_name == "auto"

    def test_load_api_key_from_config_ini(self, tmp_path: Path) -> None:
        dump_yaml(
            {"project_name": "ini", "language": "python", "framework": "django"},
            tmp_path / ".repoctx.yaml",
        )
        # config.ini lives in the repoctx tool root, not the target project root.
        from repoctx import loader

        tool_root = Path(loader.__file__).resolve().parent.parent.parent
        ini_path = tool_root / "config.ini"
        original = ini_path.read_text(encoding="utf-8") if ini_path.exists() else None
        ini_path.write_text("[DEFAULT]\ntencent_cloud_llm_api_key = ini-key-123\n")
        try:
            cfg = load_config(tmp_path)
            assert cfg.get_api_key() == "ini-key-123"
        finally:
            if original is not None:
                ini_path.write_text(original, encoding="utf-8")
            elif ini_path.exists():
                ini_path.unlink()
