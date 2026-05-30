"""Tests for file scanner exclusion logic."""

from __future__ import annotations

from pathlib import Path

from repoctx.models import RepoCtxConfig
from repoctx.scanner.file_scanner import scan_files, should_exclude


class TestShouldExclude:
    """Unit tests for should_exclude helper."""

    def test_excludes_by_name(self, tmp_path: Path) -> None:
        file = tmp_path / "foo.pyc"
        file.write_text("x")
        assert should_exclude(file, ["*.pyc"], tmp_path) is True

    def test_excludes_by_relative_path(self, tmp_path: Path) -> None:
        file = tmp_path / "a" / "b" / "secret.txt"
        file.parent.mkdir(parents=True)
        file.write_text("x")
        assert should_exclude(file, ["a/b/*.txt"], tmp_path) is True

    def test_excludes_directory_name(self, tmp_path: Path) -> None:
        """Writing 'migrations' as a plain pattern should exclude anything under migrations/."""
        file = tmp_path / "accounts" / "migrations" / "0001.py"
        file.parent.mkdir(parents=True)
        file.write_text("x")
        assert should_exclude(file, ["migrations"], tmp_path) is True

    def test_excludes_glob_migration_pattern(self, tmp_path: Path) -> None:
        file = tmp_path / "accounts" / "migrations" / "0001_initial.py"
        file.parent.mkdir(parents=True)
        file.write_text("x")
        assert should_exclude(file, ["*/migrations/*"], tmp_path) is True

    def test_keeps_non_migration(self, tmp_path: Path) -> None:
        file = tmp_path / "accounts" / "models.py"
        file.parent.mkdir(parents=True)
        file.write_text("x")
        assert should_exclude(file, ["*/migrations/*"], tmp_path) is False

    def test_keeps_unmatched(self, tmp_path: Path) -> None:
        file = tmp_path / "hello.py"
        file.write_text("x")
        assert should_exclude(file, ["*.pyc"], tmp_path) is False


class TestScanFiles:
    """Integration tests for scan_files."""

    def test_default_excludes_migrations(self, tmp_path: Path) -> None:
        config = RepoCtxConfig(
            project_name="demo",
            language="python",
            framework="django",
        )

        (tmp_path / "accounts" / "migrations").mkdir(parents=True)
        (tmp_path / "accounts" / "migrations" / "0001_initial.py").write_text("x")
        (tmp_path / "accounts" / "models.py").write_text("x")

        files = scan_files(config, tmp_path)
        names = {f.name for f in files}

        assert "0001_initial.py" not in names
        assert "models.py" in names

    def test_custom_exclude_overrides(self, tmp_path: Path) -> None:
        config = RepoCtxConfig(
            project_name="demo",
            language="python",
            framework="django",
            exclude_paths=["*.txt"],
        )

        (tmp_path / "a.py").write_text("x")
        (tmp_path / "b.txt").write_text("x")

        files = scan_files(config, tmp_path)
        names = {f.name for f in files}

        assert "a.py" in names
        assert "b.txt" not in names

    def test_exclude_nested_migration(self, tmp_path: Path) -> None:
        """Migration files nested inside app directories should be excluded."""
        config = RepoCtxConfig(
            project_name="demo",
            language="python",
            framework="django",
        )

        (tmp_path / "apps" / "billing" / "migrations").mkdir(parents=True)
        (tmp_path / "apps" / "billing" / "migrations" / "0002_add_credit.py").write_text("x")
        (tmp_path / "apps" / "billing" / "services.py").write_text("x")

        files = scan_files(config, tmp_path)
        names = {f.name for f in files}

        assert "0002_add_credit.py" not in names
        assert "services.py" in names
