"""Tests for scripts/preflight.py.

Runs the script as a subprocess so we test the real exit-code behaviour,
including the case where a required binary is absent from PATH.
"""
import os
import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "preflight.py"
_SPEC = spec_from_file_location("preflight", PREFLIGHT)
preflight = module_from_spec(_SPEC)
_SPEC.loader.exec_module(preflight)


def _run(extra_env: dict | None = None, args: list[str] | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(extra_env or {})}
    cmd = [sys.executable, str(PREFLIGHT)] + (args or [])
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


class TestMissingBinaries:
    def test_missing_forge_exits_nonzero(self, tmp_path):
        """Exit 1 when forge/anvil are not on PATH."""
        result = _run(extra_env={"PATH": str(tmp_path)})
        assert result.returncode != 0

    def test_missing_forge_prints_missing_tag(self, tmp_path):
        result = _run(extra_env={"PATH": str(tmp_path)})
        assert "[MISSING]" in result.stdout

    def test_missing_forge_mentions_foundry(self, tmp_path):
        result = _run(extra_env={"PATH": str(tmp_path)})
        assert "foundryup" in result.stdout.lower() or "foundry" in result.stdout.lower()


def _make_stubs(tmp_path: Path, *names: str) -> str:
    """Write minimal executable stubs and return a PATH string containing them."""
    for name in names:
        stub = tmp_path / name
        stub.write_text("#!/bin/sh\necho stub\n")
        stub.chmod(0o755)
    return str(tmp_path) + os.pathsep + os.environ.get("PATH", "")


class TestHappyPath:
    def test_exits_zero_when_forge_present(self, tmp_path):
        result = _run(extra_env={"PATH": _make_stubs(tmp_path, "forge", "anvil")})
        assert result.returncode == 0, (
            f"preflight.py exited {result.returncode}.\nstdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    def test_all_required_checks_passed_message(self, tmp_path):
        result = _run(extra_env={"PATH": _make_stubs(tmp_path, "forge", "anvil")})
        assert "All required checks passed" in result.stdout


def test_import_time_oserror_is_advisory_and_does_not_abort(monkeypatch, capsys):
    def fail_import(_module):
        raise OSError("native library unavailable")

    monkeypatch.setattr(preflight.importlib, "import_module", fail_import)

    preflight._check_importable("torch", "torch", optional=True)

    assert "[WARN]" in capsys.readouterr().out


def test_rpc_success_output_does_not_expose_credentials(monkeypatch, capsys):
    secret = "SENTINEL_RPC_CREDENTIAL"
    url = f"https://rpc.example/{secret}"

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b'{"result":"0x1"}'

    monkeypatch.setattr(preflight.urllib.request, "urlopen", lambda *args, **kwargs: Response())

    assert preflight._check_rpc(url) == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert url not in output
    assert "chainId 1" in output


def test_rpc_failure_output_does_not_expose_credentials_or_exception(monkeypatch, capsys):
    secret = "SENTINEL_RPC_CREDENTIAL"
    url = f"https://rpc.example/{secret}"

    def fail_request(*args, **kwargs):
        raise OSError(f"failed for {url}")

    monkeypatch.setattr(preflight.urllib.request, "urlopen", fail_request)

    assert preflight._check_rpc(url) == 0
    output = capsys.readouterr().out
    assert secret not in output
    assert url not in output
    assert "failed for" not in output


@pytest.mark.parametrize(
    ("assignment", "expected"),
    [
        ('export SEPOLIA_OP_DEVNET_RPC_URL = "https://rpc.example/a#b" # comment', "https://rpc.example/a#b"),
        ("SEPOLIA_OP_DEVNET_RPC_URL='https://rpc.example/a#b'", "https://rpc.example/a#b"),
        ("SEPOLIA_OP_DEVNET_RPC_URL = https://rpc.example/a # comment", "https://rpc.example/a"),
    ],
)
def test_env_reader_accepts_dotenv_assignment_forms(tmp_path, assignment, expected):
    env_file = tmp_path / ".env.network"
    env_file.write_text(f"{assignment}\n", encoding="utf-8")

    assert preflight._read_env_value(env_file, "SEPOLIA_OP_DEVNET_RPC_URL") == expected


def test_missing_network_env_still_checks_ipfs(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(preflight, "_REPO_ROOT", tmp_path)
    checked = []
    monkeypatch.setattr(preflight, "_check_ipfs_config", lambda: checked.append(True) or 0)

    assert preflight._network_checks("local") == 0

    assert checked == [True]
    output = capsys.readouterr().out
    assert ".env.local not found" in output
    assert "Copy .env.example to .env.local" in output


def test_run_annotations_are_postponed_for_python_39_compatibility():
    assert isinstance(preflight.run.__annotations__["network"], str)
