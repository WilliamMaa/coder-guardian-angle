"""Tests for the SemanticDigestEngine and supporting utilities."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoctx.cards.models import CardVersion, ContextPack, EntryCard, SymbolCard
from repoctx.llm.errors import LLMParseError
from repoctx.semantic_memory.engine import DigestResult, SemanticDigestEngine
from repoctx.semantic_memory.prompt_builder import (
    build_context_prompt,
    build_entry_prompt,
    build_symbol_prompt,
)
from repoctx.semantic_memory.versioning import (
    compute_dependency_hash,
    compute_file_hash,
    get_git_commit,
)
from repoctx.tracer.base import CallNode, SymbolSource
from repoctx.utils.yaml_io import load_yaml


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Fake LLM client that returns pre-canned responses in order."""

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
def mini_project(tmp_path: Path) -> Path:
    """Create a tiny two-file Python project under *tmp_path*."""
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
    return tmp_path


@pytest.fixture
def mock_responses() -> list[str]:
    """Pre-canned JSON responses for entry → symbols → context prompts."""
    return [
        json.dumps({
            "summary": "Handles incoming web requests and retrieves user data.",
            "business_role": ["request handler entrypoint"],
            "main_downstream": ["services.get_data"],
        }),
        json.dumps([
            {
                "id": "symbol.services.get_data",
                "summary": "Retrieves user data from the system.",
                "semantic_role": ["data retrieval service"],
                "side_effects": "none",
                "used_by_flows": ["handle_request"],
                "reuse_guidance": {
                    "use_when": ["need user data"],
                    "avoid": ["bypassing this layer"],
                },
            }
        ]),
        json.dumps({
            "id": "context.handle_request",
            "title": "Request Handling Flow",
            "flow_summary": "Processes web requests by fetching user data.",
            "main_entries": ["handle_request"],
            "main_paths": ["success path"],
            "important_deep_functions": [
                {
                    "symbol_id": "symbol.services.get_data",
                    "file": "services.py",
                    "summary": "Retrieves data",
                }
            ],
            "known_pitfalls": ["none"],
            "related_tests": ["request tests"],
        }),
    ]


# ---------------------------------------------------------------------------
# Versioning utilities
# ---------------------------------------------------------------------------


class TestVersioning:
    def test_compute_file_hash(self, tmp_path: Path) -> None:
        path = tmp_path / "foo.py"
        path.write_text("print(1)")
        h1 = compute_file_hash(path)
        h2 = compute_file_hash(path)
        assert len(h1) == 64
        assert h1 == h2

    def test_compute_file_hash_changes_on_content_change(self, tmp_path: Path) -> None:
        path = tmp_path / "foo.py"
        path.write_text("print(1)")
        h1 = compute_file_hash(path)
        path.write_text("print(2)")
        h2 = compute_file_hash(path)
        assert h1 != h2

    def test_get_git_commit(self) -> None:
        # This repo is a git repo, so we should get a non-empty short SHA
        commit = get_git_commit(Path.cwd())
        assert isinstance(commit, str)
        # If run outside git, it could be empty; inside this project it is not.
        if (Path.cwd() / ".git").exists():
            assert len(commit) > 0

    def test_compute_dependency_hash(self) -> None:
        child = CallNode(
            symbol="get_data",
            module_path=None,
            source=SymbolSource(file="services.py", symbol="get_data"),
        )
        parent = CallNode(
            symbol="handle_request",
            module_path=None,
            source=SymbolSource(file="views.py", symbol="handle_request"),
            children=[child],
        )
        h = compute_dependency_hash(parent)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_compute_dependency_hash_empty_children(self) -> None:
        node = CallNode(
            symbol="handle_request",
            module_path=None,
            source=SymbolSource(file="views.py", symbol="handle_request"),
        )
        assert compute_dependency_hash(node) == ""


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


class TestPromptBuilder:
    def test_build_entry_prompt_contains_symbol_and_source(self, tmp_path: Path) -> None:
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        node = CallNode(
            symbol="handle",
            module_path=None,
            source=SymbolSource(file="views.py", symbol="handle", line_start=1, line_end=2),
        )
        prompt = build_entry_prompt(node, tmp_path)
        assert "handle" in prompt
        assert "views.py" in prompt
        assert "def handle():" in prompt

    def test_build_symbol_prompt_contains_functions(self, tmp_path: Path) -> None:
        (tmp_path / "svc.py").write_text("def get():\n    return 1\n")
        nodes = [
            CallNode(
                symbol="get",
                module_path=None,
                source=SymbolSource(file="svc.py", symbol="get", line_start=1, line_end=2),
            )
        ]
        prompt = build_symbol_prompt(nodes, tmp_path, "test_flow")
        assert "get" in prompt
        assert "test_flow" in prompt
        assert "def get():" in prompt

    def test_build_context_prompt_contains_tree(self, tmp_path: Path) -> None:
        (tmp_path / "views.py").write_text("def handle():\n    pass\n")
        entry = CallNode(
            symbol="handle",
            module_path=None,
            source=SymbolSource(file="views.py", symbol="handle", line_start=1, line_end=2),
        )
        prompt = build_context_prompt(entry, [entry], tmp_path)
        assert "handle" in prompt
        assert "Full call graph" in prompt


# ---------------------------------------------------------------------------
# SemanticDigestEngine
# ---------------------------------------------------------------------------


class TestSemanticDigestEngine:
    def test_digest_generates_all_cards(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        assert isinstance(result, DigestResult)
        # entry + 1 symbol + context = 3 cards
        assert len(result.cards) == 3
        assert len(result.written_paths) == 3
        assert len(client.calls) == 3  # entry, symbols, context

    def test_entry_card_structure(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        entry = result.cards[0]
        assert entry["card_type"] == "entry"
        assert entry["id"] == "entry.views.handle_request"
        assert entry["summary"] == "Handles incoming web requests and retrieves user data."
        assert entry["business_role"] == ["request handler entrypoint"]
        assert entry["main_downstream"] == ["services.get_data"]
        assert "source" in entry
        assert entry["source"]["file"] == "views.py"
        assert entry["source"]["symbol"] == "handle_request"

    def test_symbol_card_structure(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        symbol = result.cards[1]
        assert symbol["card_type"] == "symbol"
        assert symbol["id"] == "symbol.services.get_data"
        assert symbol["semantic_role"] == ["data retrieval service"]
        assert symbol["side_effects"] == "none"
        assert symbol["reuse_guidance"]["use_when"] == ["need user data"]

    def test_context_pack_structure(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        ctx = result.cards[2]
        assert ctx["id"] == "context.handle_request"
        assert ctx["title"] == "Request Handling Flow"
        assert len(ctx["important_deep_functions"]) == 1

    def test_all_cards_have_version(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        for card in result.cards:
            assert "version" in card
            ver = card["version"]
            assert "generated_at" in ver
            assert ver["generated_at"] != ""
            assert ver["status"] == "fresh"

        # Entry and Symbol should have a code_hash; ContextPack may be empty
        assert result.cards[0]["version"]["code_hash"] != ""
        assert result.cards[1]["version"]["code_hash"] != ""

    def test_persists_to_correct_paths(self, mini_project: Path, mock_responses: list[str]) -> None:
        client = MockLLMClient(mock_responses.copy())
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=2
        )

        base = mini_project / ".repograph" / "semantic_memory"
        assert (base / "entries" / "entry.views.handle_request.yaml").exists()
        assert (base / "symbols" / "symbol.services.get_data.yaml").exists()
        assert (base / "context_packs" / "context.handle_request.yaml").exists()

        # Verify YAML is loadable and matches the card
        raw_entry = load_yaml(base / "entries" / "entry.views.handle_request.yaml")
        assert raw_entry["card_type"] == "entry"

    def test_no_symbol_nodes_returns_empty_symbols(self, mini_project: Path) -> None:
        """With max_depth=1 there are no internal symbol nodes."""
        client = MockLLMClient([
            json.dumps({
                "summary": "Handles requests.",
                "business_role": ["handler"],
                "main_downstream": [],
            }),
            json.dumps([]),  # empty symbol array
            json.dumps({
                "id": "context.handle_request",
                "title": "Flow",
                "flow_summary": "...",
                "main_entries": ["handle_request"],
                "main_paths": [],
                "important_deep_functions": [],
                "known_pitfalls": [],
                "related_tests": [],
            }),
        ])
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        result = engine.digest(
            "views.py", target_symbols=["handle_request"], max_depth=1
        )

        # entry + 0 symbols + context = 2 cards
        assert len(result.cards) == 2
        assert result.cards[0]["card_type"] == "entry"
        assert result.cards[1]["id"] == "context.handle_request"

    def test_auto_client_raises_without_config(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="LLM client not configured"):
            SemanticDigestEngine(project_root=tmp_path)

    def test_invalid_llm_response_raises(self, mini_project: Path) -> None:
        """If the model returns malformed JSON, LLMParseError should propagate."""
        client = MockLLMClient(["this is not json"])
        engine = SemanticDigestEngine(project_root=mini_project, client=client)
        with pytest.raises(LLMParseError):
            engine.digest(
                "views.py", target_symbols=["handle_request"], max_depth=2
            )
