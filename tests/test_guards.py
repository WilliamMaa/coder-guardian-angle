"""Tests for Engineering Guards (Phase 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from repoctx.guards.base import (
    GuardViolation,
    get_git_diff_files,
    load_protected_entities,
    load_rules,
)
from repoctx.guards.commit_check import CommitChecker
from repoctx.guards.legacy_check import LegacyChecker
from repoctx.guards.reuse_check import ReuseChecker
from repoctx.guards.structure_check import StructureChecker
from repoctx.guards.test_impact import TestImpactAnalyzer
from repoctx.utils.yaml_io import dump_yaml


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def guard_project(tmp_path: Path) -> Path:
    """Create a minimal project with guards config and semantic memory."""
    # Engineering constitution with rules
    dump_yaml(
        {
            "principles": ["Test principle"],
            "rules": {
                "no_underscore_functions": {"enabled": True, "severity": "error"},
                "mandatory_docstring": {"enabled": True, "severity": "error"},
                "no_getattr_fallback": {"enabled": True, "severity": "error"},
                "exception_logging": {"enabled": False, "severity": "warning"},
                "views_only_entries": {
                    "enabled": True,
                    "severity": "error",
                    "view_file_patterns": ["**/views.py"],
                },
            },
        },
        tmp_path / ".repograph" / "guards" / "engineering_constitution.yaml",
    )

    # Legacy protected entities
    dump_yaml(
        {
            "entities": [
                {
                    "name": "Billing Core",
                    "file": "legacy/billing/core.py",
                    "reason": "Production-critical",
                },
                {
                    "name": "Auth Module",
                    "module": "auth",
                    "reason": "Security sensitive",
                },
            ]
        },
        tmp_path / ".repograph" / "legacy" / "protected_entities.yaml",
    )

    # Semantic memory cards
    dump_yaml(
        {
            "card_type": "entry",
            "id": "entry.views.handle_request",
            "source": {"file": "views.py", "symbol": "handle_request"},
            "summary": "Handles requests",
            "main_downstream": ["services.get_data"],
            "version": {
                "code_hash": "abc",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "status": "fresh",
            },
        },
        tmp_path / ".repograph" / "semantic_memory" / "entries" / "entry.views.handle_request.yaml",
    )

    dump_yaml(
        {
            "id": "context.handle_request",
            "title": "Request Flow",
            "related_tests": ["request tests", "integration tests"],
            "version": {
                "code_hash": "",
                "generated_at": "2024-01-01T00:00:00+00:00",
                "status": "fresh",
            },
        },
        tmp_path / ".repograph" / "semantic_memory" / "context_packs" / "context.handle_request.yaml",
    )

    return tmp_path


# ---------------------------------------------------------------------------
# Base utilities
# ---------------------------------------------------------------------------


class TestBaseUtils:
    def test_load_rules(self, guard_project: Path) -> None:
        rules = load_rules(guard_project)
        assert "no_underscore_functions" in rules
        assert rules["no_underscore_functions"]["enabled"] is True
        assert rules["mandatory_docstring"]["severity"] == "error"

    def test_load_rules_missing_file(self, tmp_path: Path) -> None:
        rules = load_rules(tmp_path)
        assert rules == {}

    def test_load_protected_entities(self, guard_project: Path) -> None:
        config = load_protected_entities(guard_project)
        assert len(config.get("entities", [])) == 2

    def test_guard_violation_format(self) -> None:
        v = GuardViolation(
            rule_id="test",
            severity="error",
            file="a.py",
            line=10,
            message="bad",
            symbol="foo",
        )
        formatted = v.format()
        assert "ERROR" in formatted
        assert "a.py:10" in formatted
        assert "foo" in formatted
        assert "bad" in formatted


# ---------------------------------------------------------------------------
# StructureChecker
# ---------------------------------------------------------------------------


class TestStructureChecker:
    def test_no_violations_clean_code(self, guard_project: Path) -> None:
        (guard_project / "clean.py").write_text(
            'def good_function():\n    """This has a docstring."""\n    pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["clean.py"])
        assert violations == []

    def test_underscore_function(self, guard_project: Path) -> None:
        (guard_project / "bad.py").write_text(
            'def _private_but_public():\n    """Doc."""\n    pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["bad.py"])
        assert len(violations) == 1
        assert violations[0].rule_id == "no_underscore_functions"
        assert "_private_but_public" in violations[0].message

    def test_magic_methods_allowed(self, guard_project: Path) -> None:
        (guard_project / "magic.py").write_text(
            'class Foo:\n    def __init__(self):\n        pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["magic.py"])
        underscore_violations = [v for v in violations if v.rule_id == "no_underscore_functions"]
        assert underscore_violations == []

    def test_missing_docstring(self, guard_project: Path) -> None:
        (guard_project / "nodoc.py").write_text(
            "def no_doc():\n    pass\n"
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["nodoc.py"])
        doc_violations = [v for v in violations if v.rule_id == "mandatory_docstring"]
        assert len(doc_violations) == 1
        assert "no_doc" in doc_violations[0].message

    def test_getattr_fallback(self, guard_project: Path) -> None:
        (guard_project / "getattr_bad.py").write_text(
            "x = getattr(obj, 'attr', None)\n"
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["getattr_bad.py"])
        getattr_violations = [v for v in violations if v.rule_id == "no_getattr_fallback"]
        assert len(getattr_violations) == 1

    def test_getattr_without_fallback_allowed(self, guard_project: Path) -> None:
        (guard_project / "getattr_ok.py").write_text(
            "x = getattr(obj, 'attr')\n"
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["getattr_ok.py"])
        getattr_violations = [v for v in violations if v.rule_id == "no_getattr_fallback"]
        assert getattr_violations == []

    def test_disabled_rule_not_run(self, guard_project: Path) -> None:
        # exception_logging is disabled in the fixture
        (guard_project / "except_block.py").write_text(
            "try:\n    pass\nexcept Exception:\n    pass\n"
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["except_block.py"])
        # Should not produce exception_logging violations because it's disabled
        exc_violations = [v for v in violations if v.rule_id == "exception_logging"]
        assert exc_violations == []

    def test_format_report_no_violations(self) -> None:
        report = StructureChecker.format_report([])
        assert "passed" in report

    def test_format_report_with_violations(self, guard_project: Path) -> None:
        v = GuardViolation(
            rule_id="test", severity="error", file="a.py", line=1, message="bad"
        )
        report = StructureChecker.format_report([v])
        assert "1 violation" in report
        assert "a.py:1" in report

    def test_syntax_error_skipped(self, guard_project: Path) -> None:
        (guard_project / "broken.py").write_text("def broken(\n")
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["broken.py"])
        assert violations == []

    def test_non_python_files_ignored(self, guard_project: Path) -> None:
        (guard_project / "readme.md").write_text("# Hello\n")
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["readme.md"])
        assert violations == []

    def test_empty_rules_dict_enables_all(self, tmp_path: Path) -> None:
        dump_yaml(
            {"principles": [], "rules": {}},
            tmp_path / ".repograph" / "guards" / "engineering_constitution.yaml",
        )
        (tmp_path / "nodoc.py").write_text("def no_doc():\n    pass\n")
        checker = StructureChecker(tmp_path)
        violations = checker.check(files=["nodoc.py"])
        # With empty rules dict, all rules enabled by default
        doc_violations = [v for v in violations if v.rule_id == "mandatory_docstring"]
        assert len(doc_violations) == 1

    def test_views_only_entries_detects_helper(self, guard_project: Path) -> None:
        # views.py has handle_request (registered entry) + _buildReviewGateMessage (helper)
        (guard_project / "views.py").write_text(
            'def handle_request():\n    """Entry."""\n    pass\n\n'
            'def _buildReviewGateMessage():\n    """Helper."""\n    pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["views.py"])
        view_violations = [v for v in violations if v.rule_id == "views_only_entries"]
        assert len(view_violations) == 1
        assert "_buildReviewGateMessage" in view_violations[0].message
        assert "not a registered entry point" in view_violations[0].message

    def test_views_only_entries_allows_registered_entry(self, guard_project: Path) -> None:
        # handle_request IS registered in the fixture entry card
        (guard_project / "views.py").write_text(
            'def handle_request():\n    """Entry."""\n    pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["views.py"])
        view_violations = [v for v in violations if v.rule_id == "views_only_entries"]
        assert view_violations == []

    def test_views_only_entries_skips_non_view_files(self, guard_project: Path) -> None:
        (guard_project / "utils.py").write_text(
            'def _helper():\n    """Helper."""\n    pass\n'
        )
        checker = StructureChecker(guard_project)
        violations = checker.check(files=["utils.py"])
        view_violations = [v for v in violations if v.rule_id == "views_only_entries"]
        assert view_violations == []

    def test_views_only_entries_disabled_by_default(self, tmp_path: Path) -> None:
        # Default stub has views_only_entries.enabled = False
        dump_yaml(
            {
                "principles": [],
                "rules": {
                    "views_only_entries": {"enabled": False, "severity": "error"},
                },
            },
            tmp_path / ".repograph" / "guards" / "engineering_constitution.yaml",
        )
        (tmp_path / "views.py").write_text(
            'def some_helper():\n    """Helper."""\n    pass\n'
        )
        checker = StructureChecker(tmp_path)
        violations = checker.check(files=["views.py"])
        view_violations = [v for v in violations if v.rule_id == "views_only_entries"]
        assert view_violations == []


# ---------------------------------------------------------------------------
# TestImpactAnalyzer
# ---------------------------------------------------------------------------


class TestTestImpactAnalyzer:
    def test_analyze_with_changed_entry_file(self, guard_project: Path) -> None:
        analyzer = TestImpactAnalyzer(guard_project)
        result = analyzer.analyze(files=["views.py"])
        assert "views.py" in result["changed_files"]
        assert "entry.views.handle_request" in result["affected_entries"]
        assert "request tests" in result["related_tests"]
        assert "integration tests" in result["related_tests"]

    def test_analyze_with_downstream_change(self, guard_project: Path) -> None:
        analyzer = TestImpactAnalyzer(guard_project)
        result = analyzer.analyze(files=["services.py"])
        # services.py is downstream of handle_request, so entry should be affected
        assert "entry.views.handle_request" in result["affected_entries"]

    def test_uncovered_files(self, guard_project: Path) -> None:
        analyzer = TestImpactAnalyzer(guard_project)
        result = analyzer.analyze(files=["new_module.py"])
        assert "new_module.py" in result["uncovered_files"]

    def test_format_report(self, guard_project: Path) -> None:
        analyzer = TestImpactAnalyzer(guard_project)
        result = analyzer.analyze(files=["views.py"])
        report = TestImpactAnalyzer.format_report(result)
        assert "Test Impact Analysis" in report
        assert "entry.views.handle_request" in report
        assert "request tests" in report


# ---------------------------------------------------------------------------
# LegacyChecker
# ---------------------------------------------------------------------------


class TestLegacyChecker:
    def test_protected_file_violation(self, guard_project: Path) -> None:
        checker = LegacyChecker(guard_project)
        violations = checker.check(files=["legacy/billing/core.py"])
        assert len(violations) == 1
        assert violations[0].rule_id == "legacy_protection"
        assert "Billing Core" in violations[0].message

    def test_protected_module_prefix(self, guard_project: Path) -> None:
        checker = LegacyChecker(guard_project)
        violations = checker.check(files=["auth/views.py"])
        assert len(violations) == 1
        assert "Auth Module" in violations[0].message

    def test_no_violation(self, guard_project: Path) -> None:
        checker = LegacyChecker(guard_project)
        violations = checker.check(files=["views.py"])
        assert violations == []

    def test_format_report_no_violations(self) -> None:
        report = LegacyChecker.format_report([])
        assert "passed" in report


# ---------------------------------------------------------------------------
# CommitChecker
# ---------------------------------------------------------------------------


class TestCommitChecker:
    def test_passed_clean(self, guard_project: Path) -> None:
        (guard_project / "clean.py").write_text(
            'def good():\n    """Doc."""\n    pass\n'
        )
        checker = CommitChecker(guard_project)
        result = checker.check(files=["clean.py"])
        assert result["passed"] is True
        assert result["structure"] == []
        assert result["legacy"] == []

    def test_failed_structure_and_legacy(self, guard_project: Path) -> None:
        (guard_project / "bad.py").write_text(
            "def _bad():\n    pass\n"
        )
        checker = CommitChecker(guard_project)
        result = checker.check(files=["bad.py", "legacy/billing/core.py"])
        assert result["passed"] is False
        assert len(result["structure"]) > 0
        assert len(result["legacy"]) > 0

    def test_format_report(self, guard_project: Path) -> None:
        checker = CommitChecker(guard_project)
        result = checker.check(files=["views.py"])
        report = CommitChecker.format_report(result)
        assert "Commit Check Report" in report
        assert "Structure check" in report
        assert "Legacy check" in report
        assert "Test Impact Analysis" in report


# ---------------------------------------------------------------------------
# ReuseChecker
# ---------------------------------------------------------------------------


class TestReuseChecker:
    def test_exact_name_match(self, guard_project: Path) -> None:
        # Create a SymbolCard for get_data
        dump_yaml(
            {
                "card_type": "symbol",
                "id": "symbol.services.get_data",
                "source": {"file": "services.py", "symbol": "get_data"},
                "summary": "Retrieves user data from the system",
                "semantic_role": ["data retrieval service"],
                "side_effects": "none",
                "reuse_guidance": {
                    "use_when": ["need user data"],
                    "avoid": ["bypassing this layer"],
                },
                "version": {
                    "generated_at": "2024-01-01T00:00:00+00:00",
                    "status": "fresh",
                },
            },
            guard_project / ".repograph" / "semantic_memory" / "symbols" / "symbol.services.get_data.yaml",
        )

        # New file defines a function with the SAME name as existing symbol
        (guard_project / "new_module.py").write_text(
            "def get_data():\n    return {'name': 'test'}\n"
        )
        checker = ReuseChecker(guard_project)
        suggestions = checker.check(files=["new_module.py"])
        assert len(suggestions) == 1
        assert suggestions[0].confidence == "high"
        assert suggestions[0].existing_symbol_id == "symbol.services.get_data"
        assert "exact name match" in suggestions[0].match_reason

    def test_keyword_match(self, guard_project: Path) -> None:
        dump_yaml(
            {
                "card_type": "symbol",
                "id": "symbol.credits.get_balance",
                "source": {"file": "credits.py", "symbol": "get_balance"},
                "summary": "Public read surface for credit balance",
                "semantic_role": ["credit balance read surface"],
                "side_effects": "none",
                "reuse_guidance": {
                    "use_when": ["checking credit balance"],
                    "avoid": [],
                },
                "version": {
                    "generated_at": "2024-01-01T00:00:00+00:00",
                    "status": "fresh",
                },
            },
            guard_project / ".repograph" / "semantic_memory" / "symbols" / "symbol.credits.get_balance.yaml",
        )

        # New function has different name but same domain keywords
        (guard_project / "new_module.py").write_text(
            "def calculate_credit_balance(user_id):\n"
            "    # check the credit balance for this user\n"
            "    return 100\n"
        )
        checker = ReuseChecker(guard_project)
        suggestions = checker.check(files=["new_module.py"])
        assert len(suggestions) >= 1
        assert any(
            s.existing_symbol_id == "symbol.credits.get_balance"
            for s in suggestions
        )

    def test_no_match(self, guard_project: Path) -> None:
        (guard_project / "new_module.py").write_text(
            "def completely_unrelated_thing():\n    return 42\n"
        )
        checker = ReuseChecker(guard_project)
        suggestions = checker.check(files=["new_module.py"])
        assert suggestions == []

    def test_format_report(self) -> None:
        from repoctx.guards.reuse_check import ReuseSuggestion

        suggestions = [
            ReuseSuggestion(
                new_file="views.py",
                new_symbol="get_data",
                new_line=10,
                existing_symbol_id="symbol.services.get_data",
                existing_summary="Retrieves user data",
                existing_use_when=["need user data"],
                match_reason="exact name match",
                confidence="high",
            )
        ]
        report = ReuseChecker.format_report(suggestions)
        assert "Reuse check" in report
        assert "symbol.services.get_data" in report
        assert "exact name match" in report

    def test_no_symbols_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "foo.py").write_text("def bar(): pass\n")
        checker = ReuseChecker(tmp_path)
        suggestions = checker.check(files=["foo.py"])
        assert suggestions == []

    def test_scan_all(self, guard_project: Path) -> None:
        dump_yaml(
            {
                "card_type": "symbol",
                "id": "symbol.utils.helper",
                "source": {"file": "utils.py", "symbol": "helper"},
                "summary": "A helper function",
                "semantic_role": ["utility"],
                "side_effects": "none",
                "reuse_guidance": {"use_when": [], "avoid": []},
                "version": {
                    "generated_at": "2024-01-01T00:00:00+00:00",
                    "status": "fresh",
                },
            },
            guard_project / ".repograph" / "semantic_memory" / "symbols" / "symbol.utils.helper.yaml",
        )
        (guard_project / "new_module.py").write_text("def helper(): pass\n")
        checker = ReuseChecker(guard_project)
        suggestions = checker.check(scan_all=True)
        assert any(s.new_file == "new_module.py" for s in suggestions)
