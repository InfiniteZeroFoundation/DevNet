"""Lint findings and tool/report failures must fail the CI checker."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ruff_check", Path(__file__).resolve().parents[1] / ".github/scripts/ruff_check.py"
)
ruff_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ruff_check)


def finding(code="F401"):
    return {"code": code, "filename": "example.py", "location": {"row": 2, "column": 1}, "message": "unused import"}


def test_findings_are_visible(capsys):
    ruff_check.report(1, json.dumps([finding()]))
    assert "example.py:2:1: F401 unused import" in capsys.readouterr().out


def test_clean_report(capsys):
    ruff_check.report(0, "[]")
    assert "findings: 0" in capsys.readouterr().out


@pytest.mark.parametrize("status,output", [
    (2, "[]"), (127, ""), (1, "invalid"), (1, "[]"), (0, "{}"),
    (0, json.dumps([finding()])), (1, json.dumps([finding("E902")])),
    (1, '[{}]'),
])
def test_errors_are_fatal(status, output):
    with pytest.raises((ValueError, KeyError, TypeError)):
        ruff_check.report(status, output)


@pytest.mark.parametrize("status,output,expected", [
    (0, "[]", 0),
    (1, json.dumps([finding()]), 1),
    (1, json.dumps([finding("invalid-syntax")]), 1),
    (1, "invalid json", 1),
    (2, "", 1),
    (1, json.dumps([finding("E902")]), 1),
])
def test_main_preserves_artifact_and_exit(monkeypatch, tmp_path, status, output, expected):
    from types import SimpleNamespace

    destination = tmp_path / "ruff.json"
    monkeypatch.setattr(ruff_check.sys, "argv", ["ruff_check.py", str(destination)])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=status, stdout=output, stderr="")

    monkeypatch.setattr(ruff_check.subprocess, "run", run)
    assert ruff_check.main() == expected
    assert destination.read_text() == output
    assert calls == [[ruff_check.sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"]]


@pytest.mark.parametrize("field,value", [
    ("code", None), ("code", ""), ("filename", 12), ("message", []),
    ("location", None), ("location", {"row": None, "column": None}),
    ("location", {"row": 0, "column": 1}),
    ("location", {"row": True, "column": 1}),
])
def test_invalid_finding_fields_are_fatal(field, value):
    item = finding()
    item[field] = value
    with pytest.raises(ValueError):
        ruff_check.report(1, json.dumps([item]))


def test_syntax_findings_are_visible(capsys):
    ruff_check.report(1, json.dumps([finding("invalid-syntax")]))
    assert "invalid-syntax" in capsys.readouterr().out


@pytest.mark.parametrize("source,expected,code", [
    ("value = 1\n", 0, None),
    ("import os\n", 1, "F401"),
    ("def broken(:\n", 1, "invalid-syntax"),
])
def test_real_checker_exit_and_artifact(tmp_path, source, expected, code):
    import subprocess
    import sys

    if importlib.util.find_spec("ruff") is None:
        pytest.skip("Ruff is installed separately in CI; install ruff==0.16.4 locally")
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pyproject.toml").write_text((root / "pyproject.toml").read_text())
    (tmp_path / "example.py").write_text(source)
    destination = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, str(root / ".github/scripts/ruff_check.py"), str(destination)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == expected, result.stderr
    findings = json.loads(destination.read_text())
    if code:
        assert code in [item["code"] for item in findings]
        assert code in result.stdout
    else:
        assert findings == []


@pytest.mark.parametrize("failure", ["config", "artifact"])
def test_real_checker_operational_failure(tmp_path, failure):
    import subprocess
    import sys

    if importlib.util.find_spec("ruff") is None:
        pytest.skip("Ruff is installed separately in CI; install ruff==0.16.4 locally")
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff\n" if failure == "config" else (root / "pyproject.toml").read_text()
    )
    destination = tmp_path / "report.json"
    if failure == "artifact":
        destination.mkdir()
    result = subprocess.run(
        [sys.executable, str(root / ".github/scripts/ruff_check.py"), str(destination)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert result.stderr
    if failure == "config":
        assert destination.is_file()
