"""Tests for RefreshEngine (stale detection and incremental refresh)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoctx.semantic_memory.engine import SemanticDigestEngine
from repoctx.semantic_memory.refresh_engine import RefreshEngine
from repoctx.utils.yaml_io import dump_yaml, load_yaml

from .test_semantic_memory import MockLLMClient


class TestFindStale:
    """Tests for RefreshEngine.find_stale."""

    @pytest.fixture
    def project_with_cards(self, tmp_path: Path) -> Path:
        """Create a project with pre-existing cards."""
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )
        base = tmp_path / ".repograph" / "semantic_memory"

        # Entry card
        dump_yaml(
            {
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
            },
            base / "entries" / "entry.views.handle.yaml",
        )

        # Symbol card
        dump_yaml(
            {
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
            },
            base / "symbols" / "symbol.services.get_data.yaml",
        )

        # Source files with matching content so hash differs when we change them
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        (tmp_path / "services.py").write_text("def get_data():\n    return {}\n")

        return tmp_path

    def test_no_stale_when_hashes_match(self, project_with_cards: Path) -> None:
        """If source files haven't changed, no cards are stale."""
        # Update stored hashes to match actual file hashes
        from repoctx.semantic_memory.versioning import compute_file_hash

        views_hash = compute_file_hash(project_with_cards / "views.py")
        svc_hash = compute_file_hash(project_with_cards / "services.py")

        entry_path = (
            project_with_cards
            / ".repograph"
            / "semantic_memory"
            / "entries"
            / "entry.views.handle.yaml"
        )
        entry = load_yaml(entry_path)
        entry["version"]["code_hash"] = views_hash
        dump_yaml(entry, entry_path)

        sym_path = (
            project_with_cards
            / ".repograph"
            / "semantic_memory"
            / "symbols"
            / "symbol.services.get_data.yaml"
        )
        sym = load_yaml(sym_path)
        sym["version"]["code_hash"] = svc_hash
        dump_yaml(sym, sym_path)

        engine = RefreshEngine(project_with_cards)
        report = engine.find_stale()
        assert report.stale_entries == []
        assert report.stale_symbols == []

    def test_detects_stale_entry(self, project_with_cards: Path) -> None:
        """When source file changes, entry card is marked stale."""
        engine = RefreshEngine(project_with_cards)
        report = engine.find_stale()
        assert "entry.views.handle" in report.stale_entries

    def test_detects_stale_symbol(self, project_with_cards: Path) -> None:
        """When symbol source changes, symbol card is marked stale."""
        engine = RefreshEngine(project_with_cards)
        report = engine.find_stale()
        assert "symbol.services.get_data" in report.stale_symbols


class TestRefreshAffected:
    """Tests for RefreshEngine.refresh_affected."""

    def test_refreshes_stale_entry(self, tmp_path: Path) -> None:
        """A stale entry card should trigger re-digest of that entry."""
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")

        # Pre-create a stale entry card
        base = tmp_path / ".repograph" / "semantic_memory"
        dump_yaml(
            {
                "card_type": "entry",
                "id": "entry.views.handle",
                "source": {"file": "views.py", "symbol": "handle"},
                "main_downstream": [],
                "version": {
                    "code_hash": "old_hash",
                    "dependency_hash": "",
                    "git_commit": "deadbeef",
                    "generated_at": "2026-06-01T10:00:00",
                    "status": "fresh",
                },
            },
            base / "entries" / "entry.views.handle.yaml",
        )

        client = MockLLMClient([
            json.dumps({"summary": "v2", "business_role": ["r"], "main_downstream": []}),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
        ])
        digest_engine = SemanticDigestEngine(project_root=tmp_path, client=client)
        refresh_engine = RefreshEngine(tmp_path)

        refreshed, messages = refresh_engine.refresh_affected(digest_engine)
        assert refreshed == 1
        assert any("Refreshed views.py::handle" in m for m in messages)

        # Verify the card was actually updated
        updated = load_yaml(base / "entries" / "entry.views.handle.yaml")
        assert updated["summary"] == "v2"

    def test_stale_symbol_triggers_entry_refresh(self, tmp_path: Path) -> None:
        """If a symbol is stale, entries that reference it should also refresh."""
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        (tmp_path / "services.py").write_text("def get_data():\n    return {}\n")

        base = tmp_path / ".repograph" / "semantic_memory"

        # Entry references services.get_data in main_downstream
        dump_yaml(
            {
                "card_type": "entry",
                "id": "entry.views.handle",
                "source": {"file": "views.py", "symbol": "handle"},
                "main_downstream": ["services.get_data"],
                "version": {
                    "code_hash": "abc123",
                    "dependency_hash": "",
                    "git_commit": "deadbeef",
                    "generated_at": "2026-06-01T10:00:00",
                    "status": "fresh",
                },
            },
            base / "entries" / "entry.views.handle.yaml",
        )

        # Symbol is stale (hash mismatch)
        dump_yaml(
            {
                "card_type": "symbol",
                "id": "symbol.services.get_data",
                "source": {"file": "services.py", "symbol": "get_data"},
                "version": {
                    "code_hash": "old_hash",
                    "dependency_hash": "",
                    "git_commit": "deadbeef",
                    "generated_at": "2026-06-01T10:00:00",
                    "status": "fresh",
                },
            },
            base / "symbols" / "symbol.services.get_data.yaml",
        )

        # Update views hash to match so entry itself is NOT stale
        from repoctx.semantic_memory.versioning import compute_file_hash

        views_hash = compute_file_hash(tmp_path / "views.py")
        entry = load_yaml(base / "entries" / "entry.views.handle.yaml")
        entry["version"]["code_hash"] = views_hash
        dump_yaml(entry, base / "entries" / "entry.views.handle.yaml")

        client = MockLLMClient([
            json.dumps({"summary": "ok", "business_role": ["r"], "main_downstream": ["services.get_data"]}),
            json.dumps([
                {
                    "id": "symbol.services.get_data",
                    "summary": "Retrieves data.",
                    "semantic_role": ["data read"],
                    "side_effects": "none",
                    "used_by_flows": ["handle"],
                    "reuse_guidance": {"use_when": [], "avoid": []},
                }
            ]),
            json.dumps({
                "id": "context.handle", "title": "T", "flow_summary": "S",
                "main_entries": ["handle"], "main_paths": [],
                "important_deep_functions": [], "known_pitfalls": [], "related_tests": [],
            }),
        ])
        digest_engine = SemanticDigestEngine(project_root=tmp_path, client=client)
        refresh_engine = RefreshEngine(tmp_path)

        refreshed, messages = refresh_engine.refresh_affected(digest_engine)
        assert refreshed == 1
        assert any("Refreshed views.py::handle" in m for m in messages)

    def test_nothing_to_refresh(self, tmp_path: Path) -> None:
        """When all cards are fresh, refresh_affected reports nothing to do."""
        (tmp_path / ".repoctx.yaml").write_text(
            "project_name: test\nlanguage: python\nframework: django\n"
        )

        digest_engine = MockLLMClient([])  # won't be used
        # We need a real SemanticDigestEngine for the type, but it won't call LLM
        # because there are no stale cards.
        # Create a minimal one with a dummy client.
        from repoctx.llm.client import LLMClient
        from repoctx.models import ModelProviderConfig

        cfg = ModelProviderConfig(api_key="dummy")
        client = LLMClient(cfg)
        digest_engine = SemanticDigestEngine(project_root=tmp_path, client=client)
        refresh_engine = RefreshEngine(tmp_path)

        refreshed, messages = refresh_engine.refresh_affected(digest_engine)
        assert refreshed == 0
        assert any("All cards are fresh" in m for m in messages)
