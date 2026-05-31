"""Tests for the Task Workspace engine and CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repoctx.llm.pipeline import PromptPipeline
from repoctx.task_workspace.engine import (
    TaskWorkspace,
    TaskWorkspaceError,
    ValidationResult,
    _extract_active_files,
    _extract_changed_files,
    _generate_accepted_understanding,
    _module_name,
    _parse_entry_ref,
    _sanitize_task_id,
)
from repoctx.utils.yaml_io import dump_yaml, load_yaml


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Fake LLM client that returns pre-canned responses."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls: list[list[dict[str, str]]] = []

    def chat_completion_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> str:
        self.calls.append(messages)
        if not self.responses:
            raise RuntimeError("MockLLMClient: no more responses")
        return self.responses.pop(0)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task_project(tmp_path: Path) -> Path:
    """Create a minimal project with semantic memory cards for task testing."""
    # .repoctx.yaml
    dump_yaml(
        {
            "project_name": "test-project",
            "language": "python",
            "framework": "django",
            "model_provider": {"api_key": "fake-key"},
        },
        tmp_path / ".repoctx.yaml",
    )

    # Source files
    (tmp_path / "views.py").write_text(
        "from services import get_data\n\n"
        "def handle_request():\n"
        '    user = get_data()\n'
        '    return user\n'
    )
    (tmp_path / "services.py").write_text(
        "def get_data():\n"
        '    return {"name": "test"}\n'
    )

    # Entry card
    dump_yaml(
        {
            "card_type": "entry",
            "id": "entry.views.handle_request",
            "source": {"file": "views.py", "symbol": "handle_request", "line_start": 3, "line_end": 5},
            "summary": "Handles incoming web requests.",
            "business_role": ["request handler"],
            "main_downstream": ["services.get_data"],
            "version": {
                "code_hash": "abc123",
                "dependency_hash": "",
                "git_commit": "deadbeef",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "status": "fresh",
            },
        },
        tmp_path / ".repograph" / "semantic_memory" / "entries" / "entry.views.handle_request.yaml",
    )

    # Context pack
    dump_yaml(
        {
            "id": "context.handle_request",
            "title": "Request Handling Flow",
            "flow_summary": "Processes web requests.",
            "main_entries": ["handle_request"],
            "main_paths": ["success path"],
            "important_deep_functions": [
                {"symbol_id": "symbol.services.get_data", "file": "services.py", "summary": "Retrieves data"}
            ],
            "known_pitfalls": ["none"],
            "related_tests": ["request tests"],
            "version": {
                "code_hash": "",
                "dependency_hash": "",
                "git_commit": "deadbeef",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "status": "fresh",
            },
        },
        tmp_path / ".repograph" / "semantic_memory" / "context_packs" / "context.handle_request.yaml",
    )

    return tmp_path


@pytest.fixture
def mock_pipeline() -> PromptPipeline:
    """Return a PromptPipeline backed by a mock LLM client."""
    client = MockLLMClient([
        "# Accepted Understanding\n\n"
        "## 1. Task Goal\nFix the bug.\n\n"
        "## 2. Change Scope\nviews.py\n\n"
        "## 3. Out of Scope\nservices.py\n\n"
        "## 4. Frozen Assumptions\nNone\n\n"
        "## 5. Key Dependencies\nget_data\n\n"
        "## 6. Known Pitfalls\nNone\n"
    ])
    return PromptPipeline(client)


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_sanitize_task_id(self) -> None:
        tid = _sanitize_task_id("Fix Credit Bug!")
        assert tid.startswith("fix_credit_bug_")
        assert len(tid) > len("fix_credit_bug_")

    def test_sanitize_task_id_empty_special_chars(self) -> None:
        tid = _sanitize_task_id("@@@")
        assert tid.startswith("_")
        # Should still have timestamp
        assert len(tid.split("_")) >= 2

    def test_parse_entry_ref_valid(self) -> None:
        assert _parse_entry_ref("views.py::handle_request") == ("views.py", "handle_request")
        assert _parse_entry_ref("a/b/c.py::foo") == ("a/b/c.py", "foo")

    def test_parse_entry_ref_invalid(self) -> None:
        with pytest.raises(TaskWorkspaceError, match="Invalid entry reference"):
            _parse_entry_ref("views.py")

    def test_module_name(self) -> None:
        assert _module_name("views.py") == "views"
        assert _module_name("backend/credits/views.py") == "backend.credits.views"

    def test_extract_changed_files(self) -> None:
        diff = "views.py\nservices.py\n\n"
        assert _extract_changed_files(diff) == ["views.py", "services.py"]

    def test_extract_active_files(self) -> None:
        entry_card = {
            "source": {"file": "views.py"},
            "main_downstream": [],
        }
        context_pack = {
            "important_deep_functions": [
                {"file": "services.py"},
                {"file": "models.py"},
            ]
        }
        files = _extract_active_files(entry_card, context_pack)
        assert files == ["models.py", "services.py", "views.py"]

    def test_extract_active_files_no_context_pack(self) -> None:
        entry_card = {"source": {"file": "views.py"}}
        files = _extract_active_files(entry_card, None)
        assert files == ["views.py"]


# ---------------------------------------------------------------------------
# TaskWorkspace.create
# ---------------------------------------------------------------------------


class TestTaskWorkspaceCreate:
    def test_create_success(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Fix Request Bug",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        assert workspace.task_root.exists()
        assert (workspace.task_root / "task_intent.md").exists()
        assert (workspace.task_root / "accepted_understanding.md").exists()
        assert (workspace.task_root / "out_of_scope.yaml").exists()
        assert (workspace.task_root / "frozen_assumptions.yaml").exists()
        assert (workspace.task_root / "change_plan.md").exists()
        assert (workspace.task_root / "active_files.yaml").exists()
        assert (workspace.task_root / "session_notes").is_dir()

        # Verify active_files
        af = load_yaml(workspace.task_root / "active_files.yaml")
        assert "views.py" in af["files"]
        assert "services.py" in af["files"]

        # Verify accepted_understanding was written
        au = (workspace.task_root / "accepted_understanding.md").read_text(encoding="utf-8")
        assert "Accepted Understanding" in au or "Fix" in au

    def test_create_missing_entry_card(self, tmp_path: Path, mock_pipeline: PromptPipeline) -> None:
        dump_yaml(
            {"project_name": "x", "language": "python", "framework": "django"},
            tmp_path / ".repoctx.yaml",
        )
        with pytest.raises(TaskWorkspaceError, match="Entry card not found"):
            TaskWorkspace.create(
                tmp_path,
                task_name="Test",
                entry_ref="views.py::missing",
                pipeline=mock_pipeline,
            )

    def test_create_duplicate_workspace(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        # First creation
        ws1 = TaskWorkspace.create(
            task_project,
            task_name="Fix Bug",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )
        assert ws1.task_root.exists()

        # Second creation with same name should fail
        with pytest.raises(TaskWorkspaceError, match="already exists"):
            TaskWorkspace.create(
                task_project,
                task_name="Fix Bug",
                entry_ref="views.py::handle_request",
                pipeline=mock_pipeline,
            )

    def test_create_uses_fallback_on_llm_failure(self, task_project: Path) -> None:
        client = MockLLMClient([])  # empty -> will raise
        pipeline = PromptPipeline(client)

        workspace = TaskWorkspace.create(
            task_project,
            task_name="Fix Bug",
            entry_ref="views.py::handle_request",
            pipeline=pipeline,
        )

        au = (workspace.task_root / "accepted_understanding.md").read_text(encoding="utf-8")
        assert "Accepted Understanding" in au
        assert "TBD" in au  # fallback template has TBD placeholders


# ---------------------------------------------------------------------------
# TaskWorkspace.export
# ---------------------------------------------------------------------------


class TestTaskWorkspaceExport:
    def test_export_assembles_markdown(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Export Test",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        # Add a session note
        (workspace.task_root / "session_notes" / "note1.md").write_text(
            "Session 1 progress.", encoding="utf-8"
        )

        # Add out_of_scope items
        dump_yaml({"items": ["legacy/core.py", "config/settings.py"]}, workspace.task_root / "out_of_scope.yaml")

        exported = workspace.export()
        assert "# Task Export:" in exported
        assert "Task Intent:" in exported
        assert "Accepted Understanding" in exported
        assert "Change Plan" in exported
        assert "Out of Scope" in exported
        assert "legacy/core.py" in exported
        assert "Frozen Assumptions" in exported
        assert "Active Files" in exported
        assert "views.py" in exported
        assert "Session Notes" in exported
        assert "note1.md" in exported


# ---------------------------------------------------------------------------
# TaskWorkspace.validate
# ---------------------------------------------------------------------------


class TestTaskWorkspaceValidate:
    def test_validate_passes_no_violations(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Validate Test",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        # Empty diff
        result = workspace.validate(diff="")
        assert result.passed
        assert any("No uncommitted changes" in w for w in result.warnings)

    def test_validate_fails_out_of_scope(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Validate Test",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        dump_yaml({"items": ["legacy/core.py"]}, workspace.task_root / "out_of_scope.yaml")

        diff = "legacy/core.py\nviews.py\n"
        result = workspace.validate(diff=diff)
        assert not result.passed
        assert any("legacy/core.py" in v for v in result.violations)

    def test_validate_prefix_match_out_of_scope(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Validate Test",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        dump_yaml({"items": ["legacy/"]}, workspace.task_root / "out_of_scope.yaml")

        diff = "legacy/core.py\nlegacy/utils.py\n"
        result = workspace.validate(diff=diff)
        assert not result.passed
        assert len(result.violations) == 2

    def test_validate_warns_frozen_assumptions(self, task_project: Path, mock_pipeline: PromptPipeline) -> None:
        workspace = TaskWorkspace.create(
            task_project,
            task_name="Validate Test",
            entry_ref="views.py::handle_request",
            pipeline=mock_pipeline,
        )

        dump_yaml(
            {"assumptions": ["Credit balance must never go negative."]},
            workspace.task_root / "frozen_assumptions.yaml",
        )

        result = workspace.validate(diff="views.py\n")
        assert result.passed  # no hard violations
        assert any("frozen assumption" in w.lower() for w in result.warnings)

    def test_validate_result_format(self) -> None:
        result = ValidationResult(passed=True, violations=[], warnings=[])
        assert "passed" in result.format().lower()

        result = ValidationResult(
            passed=False,
            violations=["v1", "v2"],
            warnings=["w1"],
        )
        formatted = result.format()
        assert "FAILED" in formatted
        assert "v1" in formatted
        assert "w1" in formatted


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestTaskCLI:
    def test_task_list_help(self) -> None:
        from click.testing import CliRunner
        from repoctx.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["task", "list", "--help"])
        assert result.exit_code == 0
        assert "List all task workspaces" in result.output

    def test_task_validate_help(self) -> None:
        from click.testing import CliRunner
        from repoctx.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["task", "validate", "--help"])
        assert result.exit_code == 0
        assert "Validate current changes" in result.output
