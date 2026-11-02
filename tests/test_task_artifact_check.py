"""The post-build gate must reject ABI drift and stale deployable bytecode."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_task_artifacts", Path(__file__).resolve().parents[1] / ".github/scripts/check_task_artifacts.py",
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


@pytest.fixture
def artifacts(tmp_path):
    abi = [{"type": "constructor", "inputs": []}, {"type": "function", "name": "modelId"}]
    for name in checker.CONTRACTS:
        for directory, data in [
            (f"foundry/out/{name}.sol", {"abi": abi, "bytecode": {"object": "0x6001"}}),
            ("dincli/abis", {"abi": list(reversed(abi))}),
            ("cache_model_0/abis", {"abi": abi, "bytecode": "0x6001"}),
        ]:
            path = tmp_path / directory / f"{name}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
    return tmp_path


def test_matching_artifacts_ignore_abi_entry_order(artifacts):
    assert checker.check_artifacts(artifacts) == []


@pytest.mark.parametrize("directory,field,value,error", [
    ("dincli/abis", "abi", [], "ABI differs"),
    ("cache_model_0/abis", "abi", [], "ABI differs"),
    ("cache_model_0/abis", "bytecode", "0x6002", "creation bytecode differs"),
])
def test_stale_bundle_fails_gate(artifacts, directory, field, value, error):
    path = artifacts / directory / "DINTaskAuditor.json"
    data = json.loads(path.read_text())
    data[field] = value
    path.write_text(json.dumps(data))
    assert any(error in result for result in checker.check_artifacts(artifacts))


def test_missing_build_fails_with_build_instruction(tmp_path):
    errors = checker.check_artifacts(tmp_path)
    assert len(errors) == 2
    assert all("run forge build first" in error for error in errors)


def test_empty_build_bytecode_fails(artifacts):
    path = artifacts / "foundry/out/DINTaskAuditor.sol/DINTaskAuditor.json"
    data = json.loads(path.read_text())
    data["bytecode"]["object"] = "0x"
    path.write_text(json.dumps(data))
    assert any("empty build bytecode" in error for error in checker.check_artifacts(artifacts))
