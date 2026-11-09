"""Only genuine lint findings may be advisory."""

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ruff_advisory", Path(__file__).resolve().parents[1] / ".github/scripts/ruff_advisory.py"
)
ruff_advisory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ruff_advisory)


def finding(code="F401"):
    return {"code": code, "filename": "example.py", "location": {"row": 2, "column": 1}, "message": "unused import"}


def test_findings_are_visible_and_advisory(capsys):
    ruff_advisory.report(1, json.dumps([finding()]))
    assert "example.py:2:1: F401 unused import" in capsys.readouterr().out


def test_clean_report(capsys):
    ruff_advisory.report(0, "[]")
    assert "findings: 0" in capsys.readouterr().out


@pytest.mark.parametrize("status,output", [
    (2, "[]"), (127, ""), (1, "invalid"), (1, "[]"), (0, "{}"),
    (0, json.dumps([finding()])), (1, json.dumps([finding("E902")])),
    (1, '[{}]'),
])
def test_errors_are_fatal(status, output):
    with pytest.raises((ValueError, KeyError, TypeError)):
        ruff_advisory.report(status, output)


@pytest.mark.parametrize("status,output,expected", [
    (1, json.dumps([finding()]), 0),
    (2, "", 1),
    (1, json.dumps([finding("E902")]), 1),
])
def test_main_preserves_artifact_and_exit(monkeypatch, tmp_path, status, output, expected):
    from types import SimpleNamespace

    destination = tmp_path / "ruff.json"
    monkeypatch.setattr(ruff_advisory.sys, "argv", ["ruff_advisory.py", str(destination)])
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=status, stdout=output, stderr="")

    monkeypatch.setattr(ruff_advisory.subprocess, "run", run)
    assert ruff_advisory.main() == expected
    assert destination.read_text() == output
    assert calls == [[ruff_advisory.sys.executable, "-m", "ruff", "check", ".", "--output-format", "json"]]


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
        ruff_advisory.report(1, json.dumps([item]))


def test_syntax_findings_remain_advisory(capsys):
    ruff_advisory.report(1, json.dumps([finding("invalid-syntax")]))
    assert "invalid-syntax" in capsys.readouterr().out
