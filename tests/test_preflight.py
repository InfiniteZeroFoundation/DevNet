"""Tests for scripts/preflight.py.

Uses isolated subprocess fixtures for exit codes and mocks for network checks.
No installed third-party packages or live RPC/IPFS services are required.
"""
import json
import os
import subprocess
import sys
import types
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO_ROOT / "scripts" / "preflight.py"
_SPEC = spec_from_file_location("preflight", PREFLIGHT)
preflight = module_from_spec(_SPEC)
_SPEC.loader.exec_module(preflight)


class TestMissingBinaries:
    def test_missing_forge_exits_nonzero(self, standalone):
        """Exit 1 when forge/anvil are not on PATH."""
        root, _, run = standalone
        result = run({"PATH": str(root / "empty-path")})
        assert result.returncode == 1

    def test_missing_forge_prints_missing_tag(self, standalone):
        root, _, run = standalone
        result = run({"PATH": str(root / "empty-path")})
        assert "[MISSING] forge not found on PATH" in result.stdout
        assert "[MISSING] anvil not found on PATH" in result.stdout
        assert result.stdout.count("[MISSING]") == 2
        assert "2 required check(s) failed" in result.stdout

    def test_missing_forge_mentions_foundry(self, standalone):
        root, _, run = standalone
        result = run({"PATH": str(root / "empty-path")})
        assert "foundryup" in result.stdout.lower()


def _make_stubs(tmp_path: Path, *names: str) -> str:
    """Write minimal executable stubs and return a PATH string containing them."""
    for name in names:
        stub = tmp_path / name
        stub.write_text("#!/bin/sh\necho stub\n")
        stub.chmod(0o755)
    return str(tmp_path)


@pytest.fixture
def local_checks(monkeypatch, tmp_path):
    """Required checks succeed without installed tools or third-party modules."""
    (tmp_path / "foundry" / "node_modules").mkdir(parents=True)
    monkeypatch.setattr(preflight, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(preflight.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setattr(preflight.importlib, "import_module", lambda name: None)


@pytest.fixture
def standalone(tmp_path):
    """A stdlib-only clone fixture, independent of the active venv and checkout."""
    script = tmp_path / "scripts" / "preflight.py"
    script.parent.mkdir()
    script.write_text(PREFLIGHT.read_text(), encoding="utf-8")
    (tmp_path / "foundry" / "node_modules").mkdir(parents=True)
    modules = tmp_path / "modules"
    modules.mkdir()
    for name in ("eth_account", "multibase", "web3"):
        (modules / f"{name}.py").write_text("")
    (modules / "torch.py").write_text("raise ImportError('optional torch absent')")
    # No default check may depend on importing dincli.
    (modules / "dincli.py").write_text("raise AssertionError('dincli imported')")
    path = _make_stubs(tmp_path, "forge", "anvil")

    def run(extra_env=None):
        return subprocess.run(
            [sys.executable, "-S", str(script)], cwd=tmp_path,
            env={**os.environ, "PATH": path, "PYTHONPATH": str(modules),
                 **(extra_env or {})},
            capture_output=True, text=True,
        )

    return tmp_path, modules, run


def test_standalone_success_without_optional_torch(standalone):
    _, _, run = standalone
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[WARN]   torch not importable (optional" in result.stdout
    assert result.stdout.count("[WARN]") == 1
    assert "[MISSING]" not in result.stdout
    assert "All required checks passed" in result.stdout
    assert result.stderr == ""


def test_standalone_missing_node_modules_exits_one(standalone):
    root, _, run = standalone
    (root / "foundry" / "node_modules").rmdir()
    result = run()
    assert result.returncode == 1
    assert "[MISSING] foundry/node_modules not found" in result.stdout
    assert result.stdout.count("[MISSING]") == 1
    assert "1 required check(s) failed" in result.stdout
    assert "All required checks passed" not in result.stdout


@pytest.mark.parametrize("module", ["eth_account", "multibase", "web3"])
@pytest.mark.parametrize("error", ["ImportError", "OSError"])
def test_standalone_required_import_failure_continues(standalone, module, error):
    _, modules, run = standalone
    (modules / f"{module}.py").write_text(
        f"raise {error}('SENTINEL_IMPORT_SECRET')"
    )
    result = run()
    assert result.returncode == 1
    assert "1 required check(s) failed" in result.stdout
    package = {"eth_account": "eth-account", "multibase": "py-multibase", "web3": "web3"}[module]
    assert f"[MISSING] {package} not importable" in result.stdout
    assert result.stdout.count("[MISSING]") == 1
    for other, package in (
        ("eth_account", "eth-account"),
        ("multibase", "py-multibase"),
        ("web3", "web3"),
    ):
        if other != module:
            assert f"[OK]     {package} importable" in result.stdout
    assert "torch not importable (optional" in result.stdout
    assert "SENTINEL_IMPORT_SECRET" not in result.stdout + result.stderr
    assert result.stderr == ""


def test_no_network_activity_without_flag(local_checks, monkeypatch):
    request = Mock(side_effect=AssertionError("unexpected network activity"))
    network = Mock(side_effect=AssertionError("unexpected network check"))
    monkeypatch.setattr(preflight.urllib.request, "urlopen", request)
    monkeypatch.setattr(preflight, "_network_checks", network)
    monkeypatch.setitem(sys.modules, "dincli", None)
    assert preflight.run() == 0
    request.assert_not_called()
    network.assert_not_called()


def test_import_time_oserror_is_advisory_and_does_not_abort(monkeypatch, capsys):
    def fail_import(_module):
        raise OSError("native library unavailable")

    monkeypatch.setattr(preflight.importlib, "import_module", fail_import)

    assert preflight._check_importable("torch", "torch", optional=True) == 0

    output = capsys.readouterr().out
    assert "[WARN]   torch not importable (optional" in output
    assert "[MISSING]" not in output


def test_rpc_success_output_does_not_expose_credentials(monkeypatch, capsys):
    secret = "SENTINEL_RPC_CREDENTIAL"
    url = f"https://user:{secret}@rpc.example/{secret}?key={secret}#{secret}"

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
    assert "[OK]     RPC reachable:" in output
    assert "[MISSING]" not in output
    assert secret not in output
    assert url not in output
    assert "chainId 1" in output


def test_rpc_failure_output_does_not_expose_credentials_or_exception(monkeypatch, capsys):
    secret = "SENTINEL_RPC_CREDENTIAL"
    url = f"https://user:{secret}@rpc.example/{secret}?key={secret}#{secret}"

    def fail_request(*args, **kwargs):
        raise OSError(f"failed for {url}")

    monkeypatch.setattr(preflight.urllib.request, "urlopen", fail_request)

    assert preflight._check_rpc(url) == 1
    output = capsys.readouterr().out
    assert "[MISSING] RPC not reachable:" in output
    assert output.count("[MISSING]") == 1
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
    """IPFS check must run even when there is no RPC URL in env or cwd/.env."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_RPC_URL", raising=False)
    checked = []
    monkeypatch.setattr(preflight, "_check_ipfs_config", lambda: checked.append(True) or 0)

    assert preflight._network_checks("local") == 1

    assert checked == [True]
    output = capsys.readouterr().out
    assert "[MISSING] No RPC URL found for local" in output
    assert output.count("[MISSING]") == 1


def test_env_read_from_cwd_not_repo_root(monkeypatch, tmp_path, capsys):
    """RPC URL must be read from .env in the current working directory, not the
    repository root (which may differ when dincli is installed from a wheel)."""
    env_file = tmp_path / ".env"
    env_file.write_text("LOCAL_RPC_URL=https://rpc.example/cwd-sentinel\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_RPC_URL", raising=False)

    rpc_calls: list[str] = []
    monkeypatch.setattr(preflight, "_check_rpc", lambda url, **kw: rpc_calls.append(url) or 0)
    monkeypatch.setattr(preflight, "_check_ipfs_config", lambda: 0)

    preflight._network_checks("local")

    assert rpc_calls == ["https://rpc.example/cwd-sentinel"], (
        "_network_checks must read .env from cwd, not from the repository root"
    )


def test_env_read_failure_still_runs_ipfs_check(monkeypatch, tmp_path, capsys):
    """.env decode errors must produce a warning and not abort the IPFS check."""
    env_file = tmp_path / ".env"
    env_file.write_bytes(b"\xff\xfe invalid utf-8 \xff")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_RPC_URL", raising=False)

    checked: list[bool] = []
    monkeypatch.setattr(preflight, "_check_ipfs_config", lambda: checked.append(True) or 0)

    assert preflight._network_checks("local") == 1

    assert checked == [True], "IPFS check must run even when .env read fails"
    output = capsys.readouterr().out
    assert "[WARN]   .env lookup failed — skipping .env lookup" in output
    assert output.count("[WARN]") == 1
    assert "[MISSING] No RPC URL found for local" in output
    assert output.count("[MISSING]") == 1


def test_unknown_ipfs_provider_fails(ipfs_resolver, capsys):
    """An unrecognised IPFS provider is a required-check failure."""
    ipfs_resolver.return_value = types.SimpleNamespace(
        provider="SENTINEL_PROVIDER_SECRET\nINJECTED_PROVIDER_LINE",
    )
    result = preflight._check_ipfs_config()
    output = capsys.readouterr().out
    assert "[MISSING] IPFS unknown provider — IPFS operations will fail" in output
    assert output.count("[MISSING]") == 1
    assert "[WARN]" not in output
    assert "SENTINEL_PROVIDER_SECRET" not in output
    assert "INJECTED_PROVIDER_LINE" not in output
    assert "[OK]" not in output
    assert result == 1


def test_run_annotations_are_postponed_for_python_39_compatibility():
    assert isinstance(preflight.run.__annotations__["network"], str)


@pytest.fixture
def rpc_response(monkeypatch):
    reply = Mock()
    reply.__enter__ = Mock(return_value=reply)
    reply.__exit__ = Mock(return_value=None)
    transport = Mock(return_value=reply)
    monkeypatch.setattr(preflight.urllib.request, "urlopen", transport)
    return reply, transport


@pytest.mark.parametrize("response", [
    pytest.param(b"not json", id="malformed-json"),
    pytest.param(b"null", id="null-object"),
    pytest.param(b"[]", id="array-object"),
    pytest.param(b'"0x1"', id="string-object"),
    pytest.param(b"1", id="number-object"),
    pytest.param(b"true", id="boolean-object"),
    pytest.param(b"{}", id="missing-result"),
    pytest.param(b'{"error":{"code":-32000}}', id="rpc-error"),
    pytest.param(b'{"error":null,"result":"0x1"}', id="error-and-result"),
    pytest.param(b'{"result":null}', id="null-result"),
    pytest.param(b'{"result":1337}', id="number-result"),
    pytest.param(b'{"result":true}', id="boolean-result"),
    *[
        pytest.param(json.dumps({"result": value}).encode(), id=label)
        for label, value in (
            ("invalid-string", "invalid"),
            ("missing-prefix", "1337"),
            ("negative", "-0x1"),
            ("positive-sign", "+0x1"),
            ("leading-space", " 0x1"),
            ("trailing-space", "0x1 "),
            ("trailing-newline", "0x1\n"),
            ("underscore", "0x1_0"),
            ("empty-hex", "0x"),
            ("leading-zero", "0x01"),
            ("multiple-zeroes", "0x00"),
        )
    ],
])
def test_invalid_rpc_response_fails(rpc_response, capsys, response):
    reply, _ = rpc_response
    reply.read.return_value = response
    assert preflight._check_rpc("https://rpc.example") == 1
    output = capsys.readouterr().out
    assert "[MISSING] RPC not reachable:" in output
    assert output.count("[MISSING]") == 1


@pytest.mark.parametrize("quantity", ["0x0", "0x1", "0xAbCdEf", "0x539"])
def test_canonical_rpc_quantities_succeed(rpc_response, capsys, quantity):
    reply, _ = rpc_response
    reply.read.return_value = json.dumps({"result": quantity}).encode()
    assert preflight._check_rpc("https://rpc.example") == 0
    assert f"chainId {int(quantity, 16)}" in capsys.readouterr().out


def test_chain_id_mismatch_remains_advisory(rpc_response, capsys):
    reply, _ = rpc_response
    reply.read.return_value = b'{"result":"0x1"}'
    assert preflight._check_rpc("https://rpc.example", "local") == 0
    output = capsys.readouterr().out
    assert "[WARN]   RPC reachable:" in output
    assert "expected 1337" in output
    assert "[MISSING]" not in output


@pytest.fixture
def ipfs_resolver(monkeypatch):
    resolver = Mock()
    fake_ipfs = types.ModuleType("dincli.services.ipfs")
    fake_ipfs.resolve_ipfs_config = resolver
    fake_utils = types.ModuleType("dincli.cli.utils")
    fake_utils.IPFSConfig = types.SimpleNamespace
    for name in ("dincli", "dincli.services", "dincli.cli"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "dincli.services.ipfs", fake_ipfs)
    monkeypatch.setitem(sys.modules, "dincli.cli.utils", fake_utils)
    return resolver


@pytest.mark.parametrize(("provider", "fields", "expected"), [
    ("env", {}, 1),
    ("env", {"api_url_add": "https://ipfs.example/add"}, 1),
    ("env", {"api_url_retrieve": "https://ipfs.example/get"}, 1),
    ("env", {"api_url_add": "https://ipfs.example/add",
             "api_url_retrieve": "https://ipfs.example/get"}, 0),
    ("filebase", {}, 1),
    ("filebase", {"api_key": "SENTINEL_IPFS_SECRET"}, 0),
    ("custom", {}, 1),
    ("custom", {"service_path": "/fixtures/provider.py"}, 0),
    ("unknown", {}, 1),
])
def test_ipfs_provider_required_fields(
        ipfs_resolver, capsys, provider, fields, expected):
    values = dict(api_url_add="", api_url_retrieve="", api_key="", service_path="")
    values.update(fields)
    ipfs_resolver.return_value = types.SimpleNamespace(provider=provider, **values)
    assert preflight._check_ipfs_config() == expected
    output = capsys.readouterr().out
    if expected:
        assert f"[MISSING] IPFS {provider} provider" in output
        assert output.count("[MISSING]") == 1
    else:
        assert f"[OK]     IPFS config resolved ({provider} provider)" in output
        assert "[MISSING]" not in output
    assert "[WARN]" not in output
    assert "SENTINEL_IPFS_SECRET" not in output


@pytest.mark.parametrize("error", [ImportError, OSError, ValueError])
def test_unresolved_ipfs_fails_without_exposing_exception(
        ipfs_resolver, capsys, error):
    ipfs_resolver.side_effect = error("SENTINEL_IPFS_SECRET")
    assert preflight._check_ipfs_config() == 1
    output = capsys.readouterr().out
    message = (
        "dincli not importable — IPFS configuration cannot be checked"
        if error is ImportError else "IPFS config not resolved"
    )
    assert f"[MISSING] {message}" in output
    assert output.count("[MISSING]") == 1
    assert "[WARN]" not in output
    assert "SENTINEL_IPFS_SECRET" not in output


def test_unimportable_dincli_fails_ipfs(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "dincli.services.ipfs", None)
    assert preflight._check_ipfs_config() == 1
    output = capsys.readouterr().out
    assert "[MISSING] dincli not importable — IPFS configuration cannot be checked" in output
    assert output.count("[MISSING]") == 1
    assert "[WARN]" not in output


@pytest.mark.parametrize(("rpc_failure", "ipfs_failure", "expected"), [
    (0, 0, 0), (1, 0, 1), (0, 1, 1), (1, 1, 2),
])
def test_network_results_reach_main(
        local_checks, monkeypatch, capsys, rpc_failure, ipfs_failure, expected):
    monkeypatch.setenv("LOCAL_RPC_URL", "https://rpc.example")
    monkeypatch.setattr(preflight, "_check_rpc", lambda *a, **kw: rpc_failure)
    monkeypatch.setattr(preflight, "_check_ipfs_config", lambda: ipfs_failure)
    monkeypatch.setattr(sys, "argv", [str(PREFLIGHT), "--network", "local"])
    if expected:
        with pytest.raises(SystemExit) as exc:
            preflight.main()
        assert exc.value.code == 1
        assert f"{expected} required check(s) failed" in capsys.readouterr().out
    else:
        preflight.main()
        assert "All required checks passed" in capsys.readouterr().out


@pytest.mark.parametrize("operation", ["cwd", "exists", "read"])
def test_env_lookup_exception_is_sanitized_and_still_checks_ipfs(
        monkeypatch, tmp_path, capsys, operation):
    (tmp_path / ".env").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LOCAL_RPC_URL", raising=False)
    ipfs = Mock(return_value=0)
    monkeypatch.setattr(preflight, "_check_ipfs_config", ipfs)
    rpc = Mock(side_effect=AssertionError("RPC must not run without a URL"))
    monkeypatch.setattr(preflight, "_check_rpc", rpc)
    failure = Mock(side_effect=OSError("SENTINEL_ENV_SECRET\nINJECTED_ENV_LINE"))
    # Restore pathlib before pytest or its reporting can use the patched method.
    with monkeypatch.context() as lookup_patch:
        if operation == "read":
            lookup_patch.setattr(preflight, "_read_env_value", failure)
        else:
            lookup_patch.setattr(preflight.Path, operation, failure)
        assert preflight._network_checks("local") == 1
    failure.assert_called_once()
    rpc.assert_not_called()
    ipfs.assert_called_once_with()
    output = capsys.readouterr().out
    assert "[WARN]   .env lookup failed — skipping .env lookup" in output
    assert output.count("[WARN]") == 1
    assert "[MISSING] No RPC URL found for local" in output
    assert output.count("[MISSING]") == 1
    assert "SENTINEL_ENV_SECRET" not in output
    assert "INJECTED_ENV_LINE" not in output


@pytest.mark.parametrize(("scenario", "expected"), [
    ("missing-rpc", 1),
    ("unreachable-rpc", 1),
    ("invalid-rpc", 1),
    ("incomplete-ipfs", 1),
    ("unresolved-ipfs", 1),
    ("unknown-ipfs", 1),
    ("rpc-and-ipfs", 2),
])
def test_real_network_failures_reach_main_and_continue_ipfs(
        local_checks, monkeypatch, tmp_path, capsys, rpc_response,
        ipfs_resolver, scenario, expected):
    """Exercise validation and aggregation with only I/O dependencies mocked."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCAL_RPC_URL", "https://rpc.example")
    monkeypatch.setattr(sys, "argv", [str(PREFLIGHT), "--network", "local"])
    reply, transport = rpc_response
    reply.read.return_value = b'{"result":"0x539"}'
    ipfs_resolver.return_value = types.SimpleNamespace(
        provider="env", api_url_add="https://ipfs.example/add",
        api_url_retrieve="https://ipfs.example/get",
    )
    if scenario == "missing-rpc":
        monkeypatch.delenv("LOCAL_RPC_URL")
    elif scenario in ("unreachable-rpc", "rpc-and-ipfs"):
        transport.side_effect = OSError("SENTINEL_NETWORK_SECRET")
    elif scenario == "invalid-rpc":
        reply.read.return_value = b'{"result":"0x01"}'
    if scenario in ("incomplete-ipfs", "rpc-and-ipfs"):
        ipfs_resolver.return_value.api_url_retrieve = ""
    elif scenario == "unresolved-ipfs":
        ipfs_resolver.side_effect = ValueError("SENTINEL_NETWORK_SECRET")
    elif scenario == "unknown-ipfs":
        ipfs_resolver.return_value.provider = "SENTINEL_NETWORK_SECRET"

    with pytest.raises(SystemExit) as exc:
        preflight.main()
    assert exc.value.code == 1
    # Includes real request and validation failures, not a stubbed _check_rpc.
    ipfs_resolver.assert_called_once_with()
    if scenario == "missing-rpc":
        transport.assert_not_called()
    else:
        transport.assert_called_once()
    output = capsys.readouterr().out
    assert f"{expected} required check(s) failed" in output
    assert output.count("[MISSING]") == expected
    assert "All required checks passed" not in output
    assert "SENTINEL_NETWORK_SECRET" not in output


def test_failed_core_import_still_runs_requested_network_checks(
        local_checks, monkeypatch, capsys):
    def import_module(name):
        if name == "eth_account":
            raise OSError("SENTINEL_IMPORT_SECRET")

    monkeypatch.setattr(preflight.importlib, "import_module", import_module)
    network = Mock(return_value=0)
    monkeypatch.setattr(preflight, "_network_checks", network)
    assert preflight.run(network="local") == 1
    network.assert_called_once_with("local")
    output = capsys.readouterr().out
    assert "[MISSING] eth-account not importable" in output
    assert output.count("[MISSING]") == 1
    assert "[OK]     web3 importable" in output
    assert "SENTINEL_IMPORT_SECRET" not in output
