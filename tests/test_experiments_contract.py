"""Tests for experiment contract management."""

from __future__ import annotations

import pytest

from repoctx.experiments.contract import ContractEngine, ContractError
from repoctx.models.experiment import ExperimentContract


class TestContractEngine:
    """CRUD operations for experiment contracts."""

    @pytest.fixture
    def engine(self, tmp_path, monkeypatch):
        """Return a ContractEngine using a temporary repograph dir."""
        monkeypatch.setenv("REPOCTX_REPOGRAPH_DIR", str(tmp_path / ".repograph"))
        # Create a fake entry file
        entry = tmp_path / "experiments" / "dummy.py"
        entry.parent.mkdir(parents=True, exist_ok=True)
        entry.write_text(
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--epochs', type=int, default=10)\n"
            "parser.add_argument('--lr', type=float, default=0.001)\n"
            "args = parser.parse_args()\n"
        )
        return ContractEngine(project_root=tmp_path)

    def test_create_contract(self, engine, tmp_path):
        contract = engine.create(
            entry_file="experiments/dummy.py",
            contract_id="test_exp",
            purpose="Test experiment",
        )
        assert contract.id == "test_exp"
        assert contract.entry_file == "experiments/dummy.py"
        assert contract.contract.purpose == "Test experiment"
        # AST extraction should discover --epochs and --lr
        arg_names = [a.name for a in contract.contract.cli_args]
        assert "--epochs" in arg_names
        assert "--lr" in arg_names

    def test_create_duplicate_raises(self, engine):
        engine.create(entry_file="experiments/dummy.py", contract_id="dup")
        with pytest.raises(ContractError, match="already exists"):
            engine.create(entry_file="experiments/dummy.py", contract_id="dup")

    def test_create_missing_entry_raises(self, engine):
        with pytest.raises(ContractError, match="Entry file not found"):
            engine.create(entry_file="nonexistent.py", contract_id="missing")

    def test_load_and_save(self, engine):
        original = engine.create(
            entry_file="experiments/dummy.py",
            contract_id="load_test",
            purpose="original",
        )
        loaded = engine.load("load_test")
        assert loaded.id == "load_test"
        assert loaded.contract.purpose == "original"

        # Modify and save
        loaded.contract.purpose = "modified"
        engine.save(loaded)
        reloaded = engine.load("load_test")
        assert reloaded.contract.purpose == "modified"

    def test_list_and_delete(self, engine):
        engine.create(entry_file="experiments/dummy.py", contract_id="a")
        engine.create(entry_file="experiments/dummy.py", contract_id="b")
        assert set(engine.list_contracts()) == {"a", "b"}

        engine.delete("a")
        assert engine.list_contracts() == ["b"]

    def test_exists(self, engine):
        assert not engine.exists("none")
        engine.create(entry_file="experiments/dummy.py", contract_id="exists")
        assert engine.exists("exists")
