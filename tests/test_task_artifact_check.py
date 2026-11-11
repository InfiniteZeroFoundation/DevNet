"""The post-build gate must reject ABI drift and stale deployable bytecode."""
import hashlib
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


def test_bytecode_mismatch_reports_build_settings_without_passing(artifacts):
    path = artifacts / "foundry/out/DINTaskAuditor.sol/DINTaskAuditor.json"
    data = json.loads(path.read_text())
    data["bytecode"]["object"] = "0x6002"
    data["metadata"] = {"compiler": {"version": "0.8.28"}, "settings": {"viaIR": True}}
    path.write_text(json.dumps(data))
    errors = checker.check_artifacts(artifacts)
    assert any("creation bytecode differs from build" in error for error in errors)
    diagnostic = next(error for error in errors if "first differing byte:" in error)
    assert "first differing byte: 1" in diagnostic
    assert "bundled sha256:" in diagnostic and "build sha256:" in diagnostic
    assert '"version": "0.8.28"' in diagnostic
    assert '"viaIR": true' in diagnostic


@pytest.mark.parametrize("metadata", [None, [], "null", "[]", "invalid json"])
def test_unusable_metadata_preserves_mismatch_reporting(artifacts, metadata, monkeypatch, capsys):
    path = artifacts / "foundry/out/DINTaskAuditor.sol/DINTaskAuditor.json"
    data = json.loads(path.read_text())
    data.update(metadata=metadata, bytecode={"object": "0x6002"})
    path.write_text(json.dumps(data))
    monkeypatch.setattr("sys.argv", ["check_task_artifacts.py", "--root", str(artifacts)])
    assert checker.main() == 1
    output = capsys.readouterr().out
    assert "creation bytecode differs from build" in output
    assert "first differing byte: 1" in output
    assert "build metadata: unavailable" in output


def test_formatting_only_difference_still_fails_gate(artifacts):
    path = artifacts / "cache_model_0/abis/DINTaskAuditor.json"
    data = json.loads(path.read_text())
    data["bytecode"] = "6001"
    path.write_text(json.dumps(data))
    errors = checker.check_artifacts(artifacts)
    assert any("creation bytecode differs from build" in error for error in errors)
    assert any("decoded bytes identical; textual representation differs" in error for error in errors)
    assert not any("first differing byte:" in error for error in errors)


@pytest.mark.parametrize("saved,built,offset", [
    ("0x6001", "0x6101", 0),
    ("0x60", "0x6001", 1),
    ("0x6001", "0x60", 1),
])
def test_diagnostic_byte_offsets_lengths_and_hashes(saved, built, offset):
    result = checker.bytecode_diagnostics(saved, built, {})
    assert f"first differing byte: {offset}" in result
    for label, code in (("bundled", saved), ("build", built)):
        raw = bytes.fromhex(code[2:])
        assert f"{label} length: {len(raw)};" in result
        assert f"{label} sha256: {hashlib.sha256(raw).hexdigest()};" in result


@pytest.mark.parametrize("as_string", [False, True])
def test_diagnostics_report_sorted_source_hashes_and_metadata(as_string):
    metadata = {
        "compiler": {"version": "0.8.28"}, "settings": {"viaIR": True},
        "sources": {"z.sol": {"keccak256": "0x22"}, "a.sol": {"keccak256": "0x11"}},
    }
    result = checker.bytecode_diagnostics("0x6001", "0x6002", {
        "metadata": json.dumps(metadata) if as_string else metadata,
    })
    assert 'build source hashes: {"a.sol": "0x11", "z.sol": "0x22"}' in result
    assert '"version": "0.8.28"' in result
    assert '"viaIR": true' in result


def test_hex_case_difference_has_no_differing_byte():
    result = checker.bytecode_diagnostics("0x60AA", "0x60aa", {})
    assert "decoded bytes identical; textual representation differs" in result
    assert "first differing byte:" not in result
