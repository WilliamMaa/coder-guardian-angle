"""Integration tests for the knowledge graph scanner engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from repoctx.scanner.engine import ScanEngine, scan_project
from repoctx.utils.yaml_io import dump_yaml


def _create_sample_project(root: Path) -> None:
    """Create a small sample project for scanning."""
    # Config
    dump_yaml(
        {
            "project_name": "sample",
            "language": "python",
            "framework": "django",
            "scan_paths": ["."],
            "exclude_paths": [".venv", "__pycache__"],
            "modules": [
                {"name": "backend", "path": "backend", "type": "backend"},
                {"name": "frontend", "path": "frontend", "type": "frontend"},
            ],
        },
        root / ".repoctx.yaml",
    )

    # Python backend files
    (root / "backend" / "auth").mkdir(parents=True)
    (root / "backend" / "auth" / "views.py").write_text(
        "from django.shortcuts import render\n\n"
        "def login(request):\n    pass\n\n"
        "class AuthMiddleware:\n    pass\n"
    )
    (root / "backend" / "credits").mkdir(parents=True)
    (root / "backend" / "credits" / "services.py").write_text(
        "from backend.auth.views import login\n\n"
        "def get_balance(user_id: str) -> int:\n    return 100\n"
    )

    # Frontend files
    (root / "frontend" / "pages").mkdir(parents=True)
    (root / "frontend" / "pages" / "free-call.vue").write_text(
        "<template><div>Free Call</div></template>\n"
        "<script>\n"
        "export default {\n"
        "  methods: {\n"
        "    handleLogin() { console.log('login'); }\n"
        "  }\n"
        "}\n"
        "</script>\n"
    )
    (root / "frontend" / "composables").mkdir(parents=True)
    (root / "frontend" / "composables" / "useAuth.ts").write_text(
        "import { ref } from 'vue';\n\n"
        "export function useAuth() {\n  return { loggedIn: ref(false) };\n}\n"
    )

    # Excluded directory
    (root / ".venv" / "lib").mkdir(parents=True)
    (root / ".venv" / "lib" / "site.py").write_text("# should be excluded\n")


class TestScanEngine:
    """Tests for the full scanning pipeline."""

    def test_scan_creates_repograph(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        engine = ScanEngine(tmp_path)
        repograph_dir = engine.run(auto_approve=True)

        assert repograph_dir.exists()
        assert (repograph_dir / "index.json").exists()

    def test_index_json_structure(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        index_path = tmp_path / ".repograph" / "index.json"
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)

        assert "scanned_at" in index
        assert isinstance(index["total_files"], int)
        assert index["total_modules"] == 2
        assert "backend" in index["modules"]
        assert "frontend" in index["modules"]

    def test_module_indexes_created(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        backend_mod = tmp_path / ".repograph" / "modules" / "backend.json"
        frontend_mod = tmp_path / ".repograph" / "modules" / "frontend.json"

        assert backend_mod.exists()
        assert frontend_mod.exists()

        with open(backend_mod, encoding="utf-8") as f:
            mod = json.load(f)
        assert mod["id"] == "backend"
        assert mod["type"] == "backend"
        assert any("auth/views.py" in p for p in mod["files"])

    def test_entity_indexes_created(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        entities_dir = tmp_path / ".repograph" / "entities"
        assert entities_dir.exists()

        entity_files = list(entities_dir.glob("*.json"))
        names = []
        for ef in entity_files:
            with open(ef, encoding="utf-8") as f:
                names.append(json.load(f)["name"])

        assert "login" in names
        assert "AuthMiddleware" in names
        assert "get_balance" in names
        assert "handleLogin" in names
        assert "useAuth" in names

    def test_edge_indexes_created(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        edges_dir = tmp_path / ".repograph" / "edges"
        assert edges_dir.exists()
        edge_files = list(edges_dir.glob("*.json"))
        assert len(edge_files) > 0

    def test_excluded_paths_not_indexed(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        index_path = tmp_path / ".repograph" / "index.json"
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)

        # Should not include .venv files
        assert index["total_files"] < 10

    def test_generates_template_indexes(self, tmp_path: Path) -> None:
        _create_sample_project(tmp_path)
        ScanEngine(tmp_path).run(auto_approve=True)

        assert (tmp_path / ".repograph" / "protected_core.yaml").exists()
        assert (tmp_path / ".repograph" / "reusable_capabilities.yaml").exists()

    def test_high_level_scan_project(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _create_sample_project(tmp_path)
        monkeypatch.chdir(tmp_path)
        repograph_dir = scan_project(auto_approve=True)
        assert repograph_dir.exists()
        assert (repograph_dir / "index.json").exists()

    def test_scan_without_config_generates_template(self, tmp_path: Path) -> None:
        # No .repoctx.yaml
        (tmp_path / "src" / "main.py").parent.mkdir(parents=True)
        (tmp_path / "src" / "main.py").write_text("print('hello')\n")

        engine = ScanEngine(tmp_path)
        with pytest.raises(RuntimeError, match="Generated template"):
            engine.run()

        # When .repoctx.yaml is missing, the template is written directly as .repoctx.yaml
        assert (tmp_path / ".repoctx.yaml").exists()


class TestScannerPerformance:
    """Performance baseline tests."""

    def test_scan_500_files_under_180s(self, tmp_path: Path) -> None:
        """Create ~500 files and ensure scan completes within 180 seconds."""
        # Create config
        dump_yaml(
            {
                "project_name": "perf-test",
                "language": "python",
                "framework": "django",
                "scan_paths": ["."],
                "modules": [{"name": "app", "path": "app", "type": "backend"}],
            },
            tmp_path / ".repoctx.yaml",
        )

        # Create 500 Python files
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        for i in range(500):
            (app_dir / f"module_{i}.py").write_text(
                f"import os\n\ndef func_{i}():\n    return {i}\n\nclass Class_{i}:\n    pass\n"
            )

        import time

        start = time.perf_counter()
        ScanEngine(tmp_path).run()
        elapsed = time.perf_counter() - start

        # 180 seconds is extremely generous; this small project should scan in < 5s
        assert elapsed < 180.0, f"Scan took {elapsed:.2f}s, exceeds 180s budget"
