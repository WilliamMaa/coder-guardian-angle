"""Tests for card lifecycle: skip, force, list, stale, delete."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoctx.semantic_memory.engine import SemanticDigestEngine
from repoctx.utils.yaml_io import dump_yaml, load_yaml

from .test_semantic_memory import MockLLMClient


class TestDigestSkipAndForce:
    """Smart skip based on code_hash and --force override."""

    def test_skips_up_to_date_entry_card(self, tmp_path: Path) -> None:
        """If code_hash matches, EntryCard LLM call should be skipped."""
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )

        # With max_depth=1 there are no symbol nodes, so only EntryCard + ContextPack LLM calls.
        client = MockLLMClient([
            json.dumps({"summary": "ok", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
            # Second digest only needs ContextPack (EntryCard is skipped)
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
        ])
        engine = SemanticDigestEngine(project_root=tmp_path, client=client)

        # First digest — 2 LLM calls (Entry + Context)
        result1 = engine.digest("views.py", target_symbols=["handle"], max_depth=1)
        assert len(result1.cards) == 2
        calls_after_first = len(client.calls)

        # Second digest — EntryCard skipped, only ContextPack re-generated
        result2 = engine.digest("views.py", target_symbols=["handle"], max_depth=1)
        calls_after_second = len(client.calls)

        assert calls_after_second == calls_after_first + 1

    def test_force_regenerates_everything(self, tmp_path: Path) -> None:
        """--force should bypass freshness check and call LLM again."""
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )

        client = MockLLMClient([
            json.dumps({"summary": "ok", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
            # Force re-run needs both again
            json.dumps({"summary": "ok", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
        ])
        engine = SemanticDigestEngine(project_root=tmp_path, client=client)

        engine.digest("views.py", target_symbols=["handle"], max_depth=1)
        calls_after_first = len(client.calls)

        # Force — all LLM calls should run again
        engine.digest("views.py", target_symbols=["handle"], max_depth=1, force=True)
        calls_after_force = len(client.calls)

        assert calls_after_force == calls_after_first + 2

    def test_re_generates_when_source_changes(self, tmp_path: Path) -> None:
        """If source file changes (code_hash differs), EntryCard should re-generate."""
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )

        client = MockLLMClient([
            json.dumps({"summary": "v1", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
            # Second run after source change
            json.dumps({"summary": "v2", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
        ])
        engine = SemanticDigestEngine(project_root=tmp_path, client=client)

        engine.digest("views.py", target_symbols=["handle"], max_depth=1)
        calls_after_first = len(client.calls)

        # Modify source
        (tmp_path / "views.py").write_text("def handle():\n    return 1\n")

        engine.digest("views.py", target_symbols=["handle"], max_depth=1)
        calls_after_second = len(client.calls)

        # EntryCard should have been regenerated (2 more LLM calls)
        assert calls_after_second == calls_after_first + 2
        entry = load_yaml(
            tmp_path / ".repograph" / "semantic_memory" / "entries" / "entry.views.handle.yaml"
        )
        assert entry["summary"] == "v2"


class TestCliListStaleDelete:
    """CLI-level tests for list, stale, delete-card."""

    @pytest.fixture
    def project_with_cards(self, tmp_path: Path) -> Path:
        """Create a project with a few fake cards."""
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )
        base = tmp_path / ".repograph" / "semantic_memory"

        entry_card = {
            "card_type": "entry",
            "id": "entry.views.handle",
            "source": {"file": "views.py", "symbol": "handle"},
            "version": {
                "code_hash": "abc123",
                "dependency_hash": "",
                "git_commit": "deadbeef",
                "generated_at": "2026-06-01T10:00:00",
                "status": "fresh",
            },
        }
        sym_card = {
            "card_type": "symbol",
            "id": "symbol.services.get_data",
            "source": {"file": "services.py", "symbol": "get_data"},
            "version": {
                "code_hash": "def456",
                "dependency_hash": "",
                "git_commit": "deadbeef",
                "generated_at": "2026-06-01T10:00:00",
                "status": "fresh",
            },
        }
        ctx_pack = {
            "id": "context.handle",
            "title": "Handle Flow",
            "version": {
                "code_hash": "",
                "dependency_hash": "",
                "git_commit": "deadbeef",
                "generated_at": "2026-06-01T10:00:00",
                "status": "fresh",
            },
        }

        dump_yaml(entry_card, base / "entries" / "entry.views.handle.yaml")
        dump_yaml(sym_card, base / "symbols" / "symbol.services.get_data.yaml")
        dump_yaml(ctx_pack, base / "context_packs" / "context.handle.yaml")
        return tmp_path

    def test_list_shows_cards(self, project_with_cards: Path) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_with_cards):
            result = runner.invoke(main, ["list"])
            assert result.exit_code == 0, result.output
            assert "entry.views.handle" in result.output
            assert "symbol.services.get_data" in result.output
            assert "context.handle" in result.output

    def test_stale_detects_hash_mismatch(self, project_with_cards: Path) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        # Change the source file so hash no longer matches
        (project_with_cards / "views.py").write_text("def handle():\n    return 2\n")

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_with_cards):
            result = runner.invoke(main, ["stale"])
            assert result.exit_code == 0, result.output
            assert "STALE" in result.output
            assert "entry.views.handle" in result.output

    def test_stale_reports_fresh_when_nothing_changed(self, project_with_cards: Path) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_with_cards):
            result = runner.invoke(main, ["stale"])
            assert result.exit_code == 0, result.output
            assert "All cards are fresh" in result.output

    def test_delete_card_removes_file(self, project_with_cards: Path) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_with_cards):
            result = runner.invoke(main, ["delete-card", "entry.views.handle"])
            assert result.exit_code == 0, result.output
            assert "Deleted entry.views.handle" in result.output
            assert not (
                project_with_cards
                / ".repograph"
                / "semantic_memory"
                / "entries"
                / "entry.views.handle.yaml"
            ).exists()

    def test_delete_card_not_found(self, project_with_cards: Path) -> None:
        from click.testing import CliRunner

        from repoctx.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=project_with_cards):
            result = runner.invoke(main, ["delete-card", "nonexistent"])
            assert result.exit_code != 0
            assert "Card not found" in result.output
