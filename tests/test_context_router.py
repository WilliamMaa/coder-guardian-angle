"""Integration tests for the Context Router."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from repoctx.context_router import ContextReport, ContextRouter
from repoctx.utils.yaml_io import dump_yaml


def _create_project_with_index(root: Path) -> None:
    """Create a minimal project with .repoctx.yaml and .repograph/ index."""
    dump_yaml(
        {
            "project_name": "demo",
            "language": "python",
            "framework": "django",
            "scan_paths": ["."],
            "modules": [
                {"name": "backend", "path": "backend", "type": "backend"},
                {"name": "frontend", "path": "frontend", "type": "frontend"},
            ],
        },
        root / ".repoctx.yaml",
    )

    repograph = root / ".repograph"
    repograph.mkdir()

    # index.json
    (repograph / "index.json").write_text(
        json.dumps(
            {
                "scanned_at": "2024-01-01T00:00:00Z",
                "total_files": 4,
                "total_modules": 2,
                "modules": ["backend", "frontend"],
            }
        )
    )

    # modules/
    (repograph / "modules").mkdir()
    (repograph / "modules" / "backend.json").write_text(
        json.dumps(
            {
                "id": "backend",
                "name": "backend",
                "path": "backend",
                "type": "backend",
                "files": ["backend/auth/views.py", "backend/credits/services.py"],
            }
        )
    )
    (repograph / "modules" / "frontend.json").write_text(
        json.dumps(
            {
                "id": "frontend",
                "name": "frontend",
                "path": "frontend",
                "type": "frontend",
                "files": ["frontend/pages/free-call.vue"],
            }
        )
    )

    # rules/ (empty dir)
    (repograph / "rules").mkdir()


class TestContextRouter:
    """Tests for ContextRouter generate and format methods."""

    def test_generate_returns_report(self, tmp_path: Path) -> None:
        _create_project_with_index(tmp_path)
        router = ContextRouter(tmp_path)

        mock_report = ContextReport(
            related_modules=["backend", "frontend"],
            key_files=["backend/auth/views.py"],
            reusable_capabilities=[],
            protected_cores=["auth/session/login"],
            risk_points=["Do not bypass auth guard"],
            suggested_tests=["test_auth_flow"],
        )

        with patch.object(router, "generate", return_value=mock_report):
            report = router.generate("change free call login timing")

        assert "backend" in report.related_modules
        assert "backend/auth/views.py" in report.key_files

    def test_format_text_output(self, tmp_path: Path) -> None:
        _create_project_with_index(tmp_path)
        router = ContextRouter(tmp_path)

        report = ContextReport(
            related_modules=["backend"],
            key_files=["backend/auth/views.py"],
            reusable_capabilities=[],
            protected_cores=[],
            risk_points=["Do not modify GA4 event name"],
            suggested_tests=["test_login_flow"],
        )

        text = router.format_text(report)
        assert "Related Modules:" in text
        assert "backend" in text
        assert "backend/auth/views.py" in text
        assert "Do not modify GA4 event name" in text
        assert "test_login_flow" in text

    def test_vague_task_raises(self, tmp_path: Path) -> None:
        _create_project_with_index(tmp_path)
        router = ContextRouter(tmp_path)

        with pytest.raises(ValueError, match="too vague"):
            router.generate("x")

    def test_empty_task_raises(self, tmp_path: Path) -> None:
        _create_project_with_index(tmp_path)
        router = ContextRouter(tmp_path)

        with pytest.raises(ValueError, match="too vague"):
            router.generate("   ")


class TestContextCLI:
    """Tests for the repoctx context CLI command."""

    def test_context_command_json_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        _create_project_with_index(tmp_path)
        monkeypatch.chdir(tmp_path)

        mock_report = ContextReport(
            related_modules=["backend"],
            key_files=["backend/auth/views.py"],
            reusable_capabilities=[],
            protected_cores=[],
            risk_points=[],
            suggested_tests=[],
        )

        with patch("repoctx.cli.ContextRouter") as mock_router:
            instance = mock_router.return_value
            instance.generate.return_value = mock_report
            instance.format_text.return_value = "formatted text"

            runner = CliRunner()
            result = runner.invoke(main, ["context", "--format", "json", "change login"])
            assert result.exit_code == 0
            assert "backend" in result.output
            assert "backend/auth/views.py" in result.output

    def test_context_command_text_output(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        _create_project_with_index(tmp_path)
        monkeypatch.chdir(tmp_path)

        mock_report = ContextReport(
            related_modules=["frontend"],
            key_files=["frontend/pages/free-call.vue"],
            reusable_capabilities=[],
            protected_cores=[],
            risk_points=[],
            suggested_tests=[],
        )

        with patch("repoctx.cli.ContextRouter") as mock_router:
            instance = mock_router.return_value
            instance.generate.return_value = mock_report
            instance.format_text.return_value = "Task Context Report"

            runner = CliRunner()
            result = runner.invoke(main, ["context", "change free call login"])
            assert result.exit_code == 0
            assert "Task Context Report" in result.output

    def test_context_command_vague_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        _create_project_with_index(tmp_path)
        monkeypatch.chdir(tmp_path)

        runner = CliRunner()
        result = runner.invoke(main, ["context", "x"])
        assert result.exit_code != 0
        assert "too vague" in result.output or "vague" in result.output
