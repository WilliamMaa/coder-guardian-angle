"""Tests for the unified AuditEngine."""

from __future__ import annotations

from pathlib import Path

import pytest

from repoctx.audit import AuditEngine, AuditResult
from repoctx.utils.yaml_io import dump_yaml


@pytest.fixture
def audit_project(tmp_path: Path) -> Path:
    """Create a minimal project ready for audit."""
    # Engineering constitution
    dump_yaml(
        {
            "principles": [],
            "rules": {
                "no_underscore_functions": {"enabled": True, "severity": "error"},
                "mandatory_docstring": {"enabled": True, "severity": "error"},
                "views_only_entries": {
                    "enabled": True,
                    "severity": "error",
                    "view_file_patterns": ["**/views.py"],
                },
            },
        },
        tmp_path / ".repograph" / "guards" / "engineering_constitution.yaml",
    )

    # Legacy
    dump_yaml(
        {"entities": [{"name": "Core", "file": "legacy/core.py", "reason": "Protected"}]},
        tmp_path / ".repograph" / "legacy" / "protected_entities.yaml",
    )

    # Entry card for views.py
    dump_yaml(
        {
            "card_type": "entry",
            "id": "entry.views.handle_request",
            "source": {"file": "views.py", "symbol": "handle_request"},
            "summary": "Handles requests",
            "main_downstream": [],
            "version": {"generated_at": "2024-01-01T00:00:00+00:00", "status": "fresh"},
        },
        tmp_path / ".repograph" / "semantic_memory" / "entries" / "entry.views.handle_request.yaml",
    )

    # Source files
    (tmp_path / "views.py").write_text(
        'def handle_request():\n    """Entry."""\n    pass\n\n'
        'def _helper():\n    """Helper."""\n    pass\n'
    )
    (tmp_path / "services.py").write_text(
        'def get_data():\n    """Get data."""\n    pass\n'
    )
    (tmp_path / "legacy").mkdir(exist_ok=True)
    (tmp_path / "legacy" / "core.py").write_text("def core(): pass\n")

    return tmp_path


class TestAuditEngine:
    def test_audit_scans_specified_files(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["views.py"])
        assert "views.py" in result.files_scanned
        assert "services.py" not in result.files_scanned

    def test_audit_finds_missing_digest(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["views.py", "services.py"])
        # views.py has entry card, services.py does not
        assert "services.py" in result.files_missing_digest
        assert "views.py" not in result.files_missing_digest

    def test_audit_structure_violations(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["views.py"])
        # _helper starts with underscore
        underscore = [v for v in result.structure_violations if v.rule_id == "no_underscore_functions"]
        assert len(underscore) == 1

    def test_audit_legacy_violations(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["legacy/core.py"])
        assert len(result.legacy_violations) == 1

    def test_audit_report_format(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["views.py"])
        report = AuditEngine.generate_report(result)
        assert "# RepoCtx Audit Report" in report
        assert "Structure Check" in report
        assert "Legacy Check" in report
        assert "Reuse Check" in report

    def test_audit_all_mode(self, audit_project: Path) -> None:
        engine = AuditEngine(audit_project)
        result = engine.audit(scan_all=True)
        assert "views.py" in result.files_scanned
        assert "services.py" in result.files_scanned

    def test_audit_empty_no_errors(self, audit_project: Path) -> None:
        (audit_project / "clean.py").write_text(
            'def good():\n    """Doc."""\n    pass\n'
        )
        engine = AuditEngine(audit_project)
        result = engine.audit(files=["clean.py"])
        assert result.structure_violations == []
        assert result.legacy_violations == []


class TestAuditCLI:
    def test_audit_command_exists(self) -> None:
        from click.testing import CliRunner
        from repoctx.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["audit", "--help"])
        assert result.exit_code == 0
        assert "audit" in result.output
        assert "--all" in result.output
        assert "--digest" in result.output
