"""Tests for entry-driven context analysis."""

from __future__ import annotations

from pathlib import Path

from repoctx.entry_context import EntryContextAnalyzer, _find_file_node, _load_graph
from repoctx.models import (
    BlockPolicy,
    Capability,
    CapabilityIndex,
    EntryPoint,
    ProtectedCore,
    ProtectedCoreIndex,
)
from repoctx.scanner.engine import ScanEngine
from repoctx.utils.yaml_io import dump_yaml


def _create_sample_project(root: Path) -> None:
    """Create a minimal project with cross-module dependencies."""
    dump_yaml(
        {
            "project_name": "demo",
            "language": "python",
            "framework": "django",
            "scan_paths": ["."],
            "modules": [],
        },
        root / ".repoctx.yaml",
    )

    # backend/auth module
    (root / "backend" / "auth").mkdir(parents=True)
    (root / "backend" / "auth" / "views.py").write_text(
        "def login(request): pass\nclass AuthMiddleware: pass\n"
    )

    # backend/credits module — imports auth
    (root / "backend" / "credits").mkdir(parents=True)
    (root / "backend" / "credits" / "services.py").write_text(
        "from backend.auth.views import login\n\n"
        "def get_balance(user_id: str) -> int:\n    return 100\n"
    )

    # backend/freecall module — imports credits and auth
    (root / "backend" / "freecall").mkdir(parents=True)
    (root / "backend" / "freecall" / "views.py").write_text(
        "from backend.credits.services import get_balance\n"
        "from backend.auth.views import login\n\n"
        "def start_call(request):\n    balance = get_balance(request.user)\n"
    )

    # frontend module
    (root / "frontend" / "pages").mkdir(parents=True)
    (root / "frontend" / "pages" / "free-call.vue").write_text(
        "<script>\nexport default { methods: { handleLogin() {} } }\n</script>\n"
    )


class TestLoadGraph:
    """Tests for graph loading utilities."""

    def test_load_graph_after_scan(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        graph = _load_graph(tmp_path)
        assert graph is not None
        assert any(
            data.get("type") == "file"
            for _n, data in graph.nodes(data=True)
        )

    def test_load_graph_missing_returns_none(self, tmp_path: Path) -> None:
        graph = _load_graph(tmp_path)
        assert graph is None


class TestFindFileNode:
    """Tests for file node lookup in graph."""

    def test_finds_exact_match(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)
        graph = _load_graph(tmp_path)
        assert graph is not None

        node_id = _find_file_node(graph, "backend/auth/views.py")
        assert node_id is not None
        assert "auth" in node_id

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)
        graph = _load_graph(tmp_path)
        assert graph is not None

        node_id = _find_file_node(graph, "nonexistent.py")
        assert node_id is None


class TestEntryContextAnalyzer:
    """Integration tests for entry-driven context analysis."""

    def test_analyze_entry_file_downstream(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        analyzer = EntryContextAnalyzer(tmp_path)
        report = analyzer.analyze("backend/freecall/views.py", max_depth=2)

        assert report.entry_file == "backend/freecall/views.py"
        downstream_paths = {d["path"] for d in report.downstream}
        assert "backend/credits/services.py" in downstream_paths or "backend/auth/views.py" in downstream_paths

    def test_analyze_entry_file_upstream(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        analyzer = EntryContextAnalyzer(tmp_path)
        report = analyzer.analyze("backend/auth/views.py", max_depth=2)

        assert report.entry_file == "backend/auth/views.py"
        upstream_paths = {u["path"] for u in report.upstream}
        assert "backend/freecall/views.py" in upstream_paths or "backend/credits/services.py" in upstream_paths

    def test_detects_protected_core_in_radius(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)

        ScanEngine(tmp_path).run(auto_approve=True)

        # Overwrite with a custom core so we can verify cross-reference logic
        core_index = ProtectedCoreIndex(
            version="1.0",
            cores=[
                ProtectedCore(
                    id="core-auth",
                    name="auth core",
                    type="service",
                    files=["backend/auth/views.py"],
                    modules=["backend"],
                    used_by=[],
                    description="Auth core",
                    block_policy=BlockPolicy(
                        default_action="block",
                        required_explanations=["Why"],
                        required_evidence=["Affected flows"],
                        require_regression_tests=True,
                        require_rollback_plan=True,
                    ),
                )
            ],
        )
        from repoctx.loader import dump_protected_core_index
        dump_protected_core_index(core_index, tmp_path)

        analyzer = EntryContextAnalyzer(tmp_path)
        report = analyzer.analyze("backend/freecall/views.py", max_depth=2)

        core_names = [c["name"] for c in report.protected_cores_in_radius]
        assert "auth core" in core_names

    def test_detects_capability_in_radius(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        cap_index = CapabilityIndex(
            version="1.0",
            capabilities=[
                Capability(
                    id="cap-balance",
                    name="get_balance",
                    description="Check credit balance",
                    module_id="credits",
                    entry_points=[
                        EntryPoint(
                            file_path="backend/credits/services.py",
                            function_name="get_balance",
                            signature="def get_balance(user_id: str) -> int",
                            usage_example="get_balance(user_id)",
                        )
                    ],
                    use_cases=[],
                    constraints=[],
                    related_capabilities=[],
                )
            ],
        )
        from repoctx.loader import dump_capability_index
        dump_capability_index(cap_index, tmp_path)

        ScanEngine(tmp_path).run(auto_approve=True)

        analyzer = EntryContextAnalyzer(tmp_path)
        report = analyzer.analyze("backend/freecall/views.py", max_depth=2)

        cap_names = [c["name"] for c in report.capabilities_available]
        assert "get_balance" in cap_names

    def test_format_text_output(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        analyzer = EntryContextAnalyzer(tmp_path)
        report = analyzer.analyze("backend/freecall/views.py", max_depth=1)
        text = analyzer.format_text(report)

        assert "Entry File: backend/freecall/views.py" in text
        assert "RepoCtx Guard — Entry Context Report" in text

    def test_max_depth_limits_traversal(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        analyzer = EntryContextAnalyzer(tmp_path)
        report_depth_1 = analyzer.analyze("backend/freecall/views.py", max_depth=1)
        report_depth_2 = analyzer.analyze("backend/freecall/views.py", max_depth=2)

        # Deeper traversal should see at least as many nodes
        assert len(report_depth_2.downstream) >= len(report_depth_1.downstream)
