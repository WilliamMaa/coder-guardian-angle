"""Experiment contract management.

Create, load, save, and list experiment contracts. Includes a lightweight
AST extractor that discovers CLI arguments from argparse usage.
"""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path
from typing import Any

from repoctx.models.experiment import CliArg, ContractBody, ExperimentContract
from repoctx.utils.project import find_project_root, get_repograph_dir
from repoctx.utils.yaml_io import dump_yaml, load_yaml

logger = logging.getLogger("repoctx.experiments.contract")


class ContractError(Exception):
    """Raised when contract operations fail."""

    pass


class ContractEngine:
    """CRUD operations for experiment contracts."""

    def __init__(self, project_root: Path | None = None) -> None:
        if project_root is None:
            project_root = find_project_root()
        self.project_root = project_root.resolve()
        self.contracts_dir = get_repograph_dir(self.project_root) / "experiments" / "contracts"
        self.contracts_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(
        self,
        entry_file: str,
        contract_id: str,
        entry_symbol: str = "main",
        purpose: str = "",
    ) -> ExperimentContract:
        """Create a new experiment contract.

        Automatically extracts CLI arguments from the entry file via AST.
        """
        if self.exists(contract_id):
            raise ContractError(f"Contract '{contract_id}' already exists.")

        entry_path = self.project_root / entry_file
        if not entry_path.exists():
            raise ContractError(f"Entry file not found: {entry_path}")

        cli_args = _extract_cli_args(entry_path)

        contract = ExperimentContract(
            id=contract_id,
            entry_file=entry_file,
            entry_symbol=entry_symbol,
            status="draft",
            contract=ContractBody(
                purpose=purpose or f"Experiment: {contract_id}",
                cli_args=cli_args,
            ),
        )
        self.save(contract)
        logger.info("Created experiment contract: %s", contract_id)
        return contract

    def load(self, contract_id: str) -> ExperimentContract:
        """Load an existing contract by ID."""
        path = self._contract_path(contract_id)
        if not path.exists():
            raise ContractError(f"Contract '{contract_id}' not found.")
        data = load_yaml(path)
        return ExperimentContract.from_yaml_dict(data)

    def save(self, contract: ExperimentContract) -> None:
        """Persist a contract to YAML."""
        path = self._contract_path(contract.id)
        dump_yaml(contract.to_yaml_dict(), path)

    def exists(self, contract_id: str) -> bool:
        return self._contract_path(contract_id).exists()

    def list_contracts(self) -> list[str]:
        """Return IDs of all stored contracts."""
        ids: list[str] = []
        if not self.contracts_dir.exists():
            return ids
        for path in sorted(self.contracts_dir.glob("*.yaml")):
            ids.append(path.stem)
        return ids

    def delete(self, contract_id: str) -> None:
        """Delete a contract file."""
        path = self._contract_path(contract_id)
        if path.exists():
            path.unlink()

    def _contract_path(self, contract_id: str) -> Path:
        return self.contracts_dir / f"{contract_id}.yaml"


# ---------------------------------------------------------------------------
# AST extraction helpers
# ---------------------------------------------------------------------------


def _extract_cli_args(entry_path: Path) -> list[CliArg]:
    """Parse a Python file and extract argparse arguments."""
    try:
        source = entry_path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    args: list[CliArg] = []
    parser_vars: set[str] = set()

    # Walk the AST looking for argparse.ArgumentParser() assignments
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            call = _get_call(node.value)
            if call and _is_argparse_parser(call):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        parser_vars.add(target.id)

        elif isinstance(node, ast.Call):
            if _is_add_argument_call(node, parser_vars):
                arg = _parse_add_argument_call(node)
                if arg:
                    args.append(arg)

    return args


def _get_call(node: ast.AST) -> ast.Call | None:
    """Return the node if it is a Call, else None."""
    return node if isinstance(node, ast.Call) else None


def _is_argparse_parser(call: ast.Call) -> bool:
    """Detect ``ArgumentParser(...)`` or ``argparse.ArgumentParser(...)``."""
    func = call.func
    if isinstance(func, ast.Name) and func.id == "ArgumentParser":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "ArgumentParser":
        return True
    return False


def _is_add_argument_call(call: ast.Call, parser_vars: set[str]) -> bool:
    """Detect ``parser.add_argument(...)``."""
    func = call.func
    if not isinstance(func, ast.Attribute) or func.attr != "add_argument":
        return False
    value = func.value
    if isinstance(value, ast.Name) and value.id in parser_vars:
        return True
    return False


def _parse_add_argument_call(call: ast.Call) -> CliArg | None:
    """Extract ``--name`` and default from ``add_argument(...)``."""
    name: str = ""
    default: str | None = None

    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if arg.value.startswith("-"):
                name = arg.value

    for kw in call.keywords:
        if kw.arg == "default" and isinstance(kw.value, ast.Constant):
            default = str(kw.value.value) if kw.value.value is not None else None
        if kw.arg == "help" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            help_text = kw.value.value
        else:
            help_text = ""

    if not name:
        return None
    return CliArg(name=name, default=default, help_text=help_text)
