"""Tests for the extensible call-chain tracer."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from repoctx.tracer.base import TracerContext
from repoctx.tracer.factory import get_tracer
from repoctx.tracer.python import PythonTracer
from repoctx.tracer.python.call_extractor import CallExtractor
from repoctx.tracer.python.import_resolver import ImportMap, ImportResolver
from repoctx.tracer.python.module_resolver import ModulePathResolver


class TestImportResolver:
    """Tests for Python import map resolution."""

    def test_import_simple(self, tmp_path: Path) -> None:
        code = "import backend.credits.services\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(tree, tmp_path / "a.py", tmp_path)
        assert imp.modules["backend.credits.services"] == "backend.credits.services"

    def test_import_as(self, tmp_path: Path) -> None:
        code = "import backend.credits.services as svc\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(tree, tmp_path / "a.py", tmp_path)
        assert imp.modules["svc"] == "backend.credits.services"

    def test_from_import(self, tmp_path: Path) -> None:
        code = "from backend.auth.views import login\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(tree, tmp_path / "a.py", tmp_path)
        assert imp.names["login"] == ("backend.auth.views", "login")
        assert imp.modules["login"] == "backend.auth.views.login"

    def test_from_import_as(self, tmp_path: Path) -> None:
        code = "from backend.credits.services import get_balance as get_bal\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(tree, tmp_path / "a.py", tmp_path)
        assert imp.names["get_bal"] == ("backend.credits.services", "get_balance")

    def test_star_import_ignored(self, tmp_path: Path) -> None:
        code = "from backend.auth.views import *\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(tree, tmp_path / "a.py", tmp_path)
        assert "views" not in imp.names

    def test_relative_import(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "freecall").mkdir(parents=True)
        code = "from ..credits.services import get_balance\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        resolver = ImportResolver()
        imp = resolver.resolve(
            tree, tmp_path / "backend" / "freecall" / "views.py", tmp_path
        )
        assert imp.names["get_balance"] == ("backend.credits.services", "get_balance")


class TestImportMapResolve:
    """Tests for ImportMap.resolve()."""

    def test_resolve_bare_name(self) -> None:
        imp = ImportMap(names={"login": ("backend.auth.views", "login")})
        mod, sym = imp.resolve("login")
        assert mod == "backend.auth.views"
        assert sym == "login"

    def test_resolve_module_attr(self) -> None:
        imp = ImportMap(modules={"services": "backend.credits.services"})
        mod, sym = imp.resolve("services.get_balance")
        assert mod == "backend.credits.services"
        assert sym == "get_balance"

    def test_resolve_self_method(self) -> None:
        imp = ImportMap()
        mod, sym = imp.resolve("self.start_call")
        assert mod is None
        assert sym == "start_call"

    def test_resolve_unknown(self) -> None:
        imp = ImportMap()
        mod, sym = imp.resolve("unknown_func")
        assert mod is None
        assert sym == "unknown_func"


class TestCallExtractor:
    """Tests for call extraction from function bodies."""

    def test_extracts_simple_call(self) -> None:
        code = "def foo():\n    bar()\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        func = tree.body[0]
        extractor = CallExtractor()
        calls = extractor.extract(func)
        assert len(calls) == 1
        assert calls[0]["name"] == "bar"

    def test_extracts_dotted_call(self) -> None:
        code = "def foo():\n    services.get_balance()\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        func = tree.body[0]
        extractor = CallExtractor()
        calls = extractor.extract(func)
        assert len(calls) == 1
        assert calls[0]["name"] == "services.get_balance"

    def test_extracts_multiple_calls(self) -> None:
        code = "def foo():\n    a()\n    b()\n"
        tree = compile(code, "<test>", "exec", ast.PyCF_ONLY_AST)
        func = tree.body[0]
        extractor = CallExtractor()
        calls = extractor.extract(func)
        assert len(calls) == 2
        assert {c["name"] for c in calls} == {"a", "b"}


class TestModulePathResolver:
    """Tests for module-path to file-path resolution."""

    def test_resolves_module_file(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "credits").mkdir(parents=True)
        (tmp_path / "backend" / "credits" / "services.py").write_text("pass\n")
        resolver = ModulePathResolver(tmp_path)
        result = resolver.resolve("backend.credits.services")
        assert result is not None
        assert result.name == "services.py"

    def test_resolves_package_init(self, tmp_path: Path) -> None:
        (tmp_path / "backend" / "auth").mkdir(parents=True)
        (tmp_path / "backend" / "auth" / "__init__.py").write_text("pass\n")
        resolver = ModulePathResolver(tmp_path)
        result = resolver.resolve("backend.auth")
        assert result is not None
        assert result.name == "__init__.py"

    def test_missing_module_returns_none(self, tmp_path: Path) -> None:
        resolver = ModulePathResolver(tmp_path)
        assert resolver.resolve("nonexistent.module") is None


class TestPythonTracer:
    """End-to-end tests for Python call-chain tracing."""

    def _create_project(self, root: Path) -> None:
        """Create a minimal multi-file Python project."""
        (root / "backend" / "auth").mkdir(parents=True)
        (root / "backend" / "auth" / "views.py").write_text(
            "def login(request):\n    pass\n"
        )

        (root / "backend" / "credits").mkdir(parents=True)
        (root / "backend" / "credits" / "services.py").write_text(
            "from backend.auth.views import login\n\n"
            "def get_balance(user_id: str) -> int:\n"
            "    login(user_id)\n"
            "    return 100\n"
        )

        (root / "backend" / "freecall").mkdir(parents=True)
        (root / "backend" / "freecall" / "views.py").write_text(
            "from backend.credits.services import get_balance\n"
            "from backend.auth.views import login\n\n"
            "def start_call(request):\n"
            "    balance = get_balance(request.user)\n"
            "    login(request)\n"
            "    return {'status': 'ok'}\n"
        )

    def test_trace_single_function(self, tmp_path: Path) -> None:
        self._create_project(tmp_path)
        ctx = TracerContext(project_root=tmp_path, max_depth=3)
        tracer = PythonTracer(ctx)
        tree = tracer.trace("backend/freecall/views.py", symbol_names=["start_call"])

        assert tree.entry.symbol == "start_call"
        child_symbols = {c.symbol for c in tree.entry.children}
        assert "get_balance" in child_symbols
        assert "login" in child_symbols

    def test_trace_auto_discover_functions(self, tmp_path: Path) -> None:
        self._create_project(tmp_path)
        ctx = TracerContext(project_root=tmp_path, max_depth=3)
        tracer = PythonTracer(ctx)
        tree = tracer.trace("backend/freecall/views.py")

        # Should discover start_call automatically
        assert tree.entry.symbol == "start_call"

    def test_depth_limits_recursion(self, tmp_path: Path) -> None:
        self._create_project(tmp_path)
        ctx = TracerContext(project_root=tmp_path, max_depth=1)
        tracer = PythonTracer(ctx)
        tree = tracer.trace("backend/freecall/views.py", symbol_names=["start_call"])

        # Depth 1: should find get_balance but NOT trace INTO get_balance
        balance_nodes = [c for c in tree.entry.children if c.symbol == "get_balance"]
        assert len(balance_nodes) == 1
        assert len(balance_nodes[0].children) == 0

    def test_external_marked_correctly(self, tmp_path: Path) -> None:
        self._create_project(tmp_path)
        ctx = TracerContext(project_root=tmp_path, max_depth=3)
        tracer = PythonTracer(ctx)
        tree = tracer.trace("backend/credits/services.py", symbol_names=["get_balance"])

        login_nodes = [c for c in tree.entry.children if c.symbol == "login"]
        assert len(login_nodes) == 1
        assert not login_nodes[0].is_external  # login is in the project


class TestTracerFactory:
    """Tests for tracer factory dispatch."""

    def test_selects_python_tracer(self, tmp_path: Path) -> None:
        ctx = TracerContext(project_root=tmp_path)
        tracer = get_tracer("backend/views.py", ctx)
        assert isinstance(tracer, PythonTracer)

    def test_raises_for_unknown_extension(self, tmp_path: Path) -> None:
        ctx = TracerContext(project_root=tmp_path)
        with pytest.raises(ValueError):
            get_tracer("backend/views.vue", ctx)
