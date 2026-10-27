"""Exercise isolated integration fixture ownership without starting services."""

import importlib
import json
import os
import signal
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def harness(monkeypatch, tmp_path):
    # Import with isolated settings so constants cannot read host dotenv/config.
    scratch = tmp_path / "scratch"
    results = tmp_path / "evidence"
    monkeypatch.setenv("DIN_TEST_ISOLATED", "1")
    monkeypatch.setenv("DIN_TEST_TMPDIR", str(scratch))
    monkeypatch.setenv("DIN_TEST_RESULTS_DIR", str(results))
    module = importlib.import_module("tests.dincli.conftest")
    checkout = tmp_path / "checkout"
    foundry = checkout / "foundry"
    foundry.mkdir(parents=True)
    for name, value in {
        "ISOLATED_MODE": True,
        "DEVNET_ROOT": checkout,
        "FOUNDRY_DIR": foundry,
        "HARDHAT_DIR": checkout / "hardhat",
        "DIN_TEMP": scratch,
        "RESULTS_DIR": results,
        "PLATFORM_DEPLOY_TOOLCHAIN": "foundry",
    }.items():
        monkeypatch.setattr(module, name, value)

    def forbidden(*args, **kwargs):
        raise AssertionError("No real service, compilation, or network calls allowed")

    for name in ("_compile_contracts", "_build_foundry_contracts",
                 "_start_fresh_anvil_node", "_start_fresh_hardhat_node",
                 "_ensure_ipfs_running", "start_service"):
        monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(module.subprocess, "run", forbidden)
    monkeypatch.setattr(module.requests, "post", forbidden)
    return module


def fake_services(harness, monkeypatch):
    """Return real ownership wrappers around fake processes and temporary logs."""
    from tests.dincli.services import OwnedService
    from tests.dincli import services

    harness.RESULTS_DIR.mkdir()
    handles = []
    signals = []
    monkeypatch.setattr(services.os, "killpg", lambda pid, sig: signals.append((pid, sig)))
    monkeypatch.setattr(harness, "_compile_contracts", lambda path: None)
    monkeypatch.setattr(harness, "_build_foundry_contracts", lambda path: None)

    def start(command, *, log_path, **kwargs):
        log = log_path.open("w", encoding="utf-8")
        log.write("retained service evidence\n")
        log.flush()
        process = SimpleNamespace(pid=10000 + len(handles), wait=Mock())
        handle = OwnedService(process, log, log_path)
        handles.append(handle)
        return handle

    monkeypatch.setattr(harness, "start_service", start)
    return handles, signals


def test_ipfs_init_failure_closes_owned_chain_and_retains_logs(harness, monkeypatch):
    handles, signals = fake_services(harness, monkeypatch)

    def fail_init(command, **kwargs):
        kwargs["stdout"].write("IPFS init failed\n")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(harness.subprocess, "run", fail_init)
    fixture = harness.managed_services.__wrapped__(harness.DIN_TEMP)

    with pytest.raises(subprocess.CalledProcessError):
        next(fixture)

    assert len(handles) == 1
    chain = handles[0]
    assert chain._log.closed
    assert chain.process.wait.call_count == 2
    assert signals == [(chain.process.pid, signal.SIGTERM), (chain.process.pid, signal.SIGKILL)]
    assert chain.log_path.read_text() == "retained service evidence\n"
    assert (harness.RESULTS_DIR / "ipfs_init.log").read_text() == "IPFS init failed\n"


def test_successful_service_teardown_closes_both_owned_handles(harness, monkeypatch):
    handles, signals = fake_services(harness, monkeypatch)
    init_commands = []
    monkeypatch.setattr(harness.subprocess, "run", lambda args, **kwargs: init_commands.append(args))
    fixture = harness.managed_services.__wrapped__(harness.DIN_TEMP)

    next(fixture)
    assert len(handles) == 2
    assert all(not service._log.closed for service in handles)
    assert len(init_commands) == 4
    fixture.close()

    assert all(service._log.closed for service in handles)
    assert all(service.process.wait.call_count == 2 for service in handles)
    assert [pid for pid, sig in signals if sig == signal.SIGTERM] == [
        handles[1].process.pid, handles[0].process.pid,
    ]
    assert all(service.log_path.read_text() == "retained service evidence\n" for service in handles)


def test_isolated_ipfs_starts_without_a_gateway(harness, monkeypatch):
    handles, _ = fake_services(harness, monkeypatch)
    init_commands = []
    monkeypatch.setattr(harness.subprocess, "run", lambda args, **kwargs: init_commands.append(args))
    fixture = harness.managed_services.__wrapped__(harness.DIN_TEMP)

    next(fixture)
    fixture.close()

    # Configured before the daemon starts, so an unowned process on 8080 cannot stop it.
    assert [harness.IPFS_BIN, "config", "--json", "Addresses.Gateway", "[]"] in init_commands
    assert init_commands[0] == [harness.IPFS_BIN, "init"]


def test_isolated_env_filters_credentials_and_uses_local_config(harness, monkeypatch):
    monkeypatch.setenv("PINATA_JWT", "injected-production-credential")
    monkeypatch.setenv("LOCAL_RPC_URL", "https://production.invalid")
    monkeypatch.setenv("IPFS_API_URL_ADD", "https://production.invalid/add")

    env = harness.din_env.__wrapped__(harness.DIN_TEMP)

    assert "PINATA_JWT" not in env
    assert "injected-production-credential" not in env.values()
    for name, relative in {
        "HOME": "home", "XDG_CONFIG_HOME": "config", "XDG_CACHE_HOME": "cache",
        "XDG_DATA_HOME": "data", "IPFS_PATH": "ipfs",
    }.items():
        assert env[name] == str(harness.DIN_TEMP / relative)
    assert env["PYTHONPATH"] == str(harness.DEVNET_ROOT)
    assert env["LOCAL_RPC_URL"] == "http://127.0.0.1:8545"
    assert env["IPFS_API_URL_ADD"] == "http://127.0.0.1:5001/api/v0/add"
    assert env["IPFS_API_URL_RETRIEVE"] == "http://127.0.0.1:5001/api/v0"
    assert env["IPFS_PROVIDER"] == "env"


def test_isolated_scratch_refuses_existing_data_without_deleting_it(harness):
    harness.DIN_TEMP.mkdir()
    sentinel = harness.DIN_TEMP / "user-data.txt"
    sentinel.write_text("preserve this")
    fixture = harness.din_tmp.__wrapped__()

    with pytest.raises(FileExistsError):
        next(fixture)

    assert sentinel.read_text() == "preserve this"
    assert not harness.RESULTS_DIR.exists()


def test_isolated_scratch_cleanup_retains_external_evidence(harness):
    fixture = harness.din_tmp.__wrapped__()
    assert next(fixture) == harness.DIN_TEMP
    (harness.DIN_TEMP / "temporary-wallet.json").write_text("disposable")
    evidence = harness.RESULTS_DIR / "result.log"
    evidence.write_text("retain this")

    fixture.close()

    assert not harness.DIN_TEMP.exists()
    assert evidence.read_text() == "retain this"


def test_results_creation_failure_cleans_new_scratch(harness):
    harness.RESULTS_DIR.write_text("existing file")
    fixture = harness.din_tmp.__wrapped__()
    with pytest.raises(FileExistsError):
        next(fixture)
    assert not harness.DIN_TEMP.exists()
    assert harness.RESULTS_DIR.read_text() == "existing file"


@pytest.mark.parametrize("fail_bootstrap", [False, True])
def test_isolated_bootstrap_provisions_then_cleans_demo_accounts(harness, fail_bootstrap):
    accounts_path = harness.DEVNET_ROOT / "dincli" / "config" / "accounts.json"
    commands = []

    def run(args):
        data = json.loads(accounts_path.read_text())
        assert len(data["hardhat"]) == 2
        assert data["hardhat"][0]["address"] == "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        commands.append(args)
        if fail_bootstrap:
            raise RuntimeError("bootstrap command failed")

    fixture = harness.bootstrap.__wrapped__(None, None, run)
    if fail_bootstrap:
        with pytest.raises(RuntimeError, match="bootstrap command failed"):
            next(fixture)
        assert commands == [["system", "init"]]
    else:
        next(fixture)
        assert accounts_path.exists()
        assert len(commands) == 5
        fixture.close()
    assert not accounts_path.exists()


@pytest.mark.parametrize("fail_bootstrap", [False, True])
def test_isolated_bootstrap_preserves_existing_public_accounts(harness, fail_bootstrap):
    from tests.dincli.demo import generate_demo_accounts

    accounts_path = harness.DEVNET_ROOT / "dincli/config/accounts.json"
    generate_demo_accounts(accounts_path)
    original = accounts_path.read_bytes()

    def run(args):
        if fail_bootstrap:
            raise RuntimeError("bootstrap command failed")

    fixture = harness.bootstrap.__wrapped__(None, None, run)
    if fail_bootstrap:
        with pytest.raises(RuntimeError, match="bootstrap command failed"):
            next(fixture)
    else:
        next(fixture)
        fixture.close()
    assert accounts_path.read_bytes() == original


def test_isolated_foundry_chain_starts_through_anvil_sh(harness, monkeypatch):
    # foundry/anvil.sh is the single source of the chain flags; the harness only
    # adds the loopback bind and the Anvil binary it resolved.
    fake_services(harness, monkeypatch)
    calls = []
    fake_start = harness.start_service

    def start(command, **kwargs):
        calls.append((command, kwargs))
        return fake_start(command, **kwargs)

    monkeypatch.setattr(harness, "start_service", start)
    monkeypatch.setattr(harness.subprocess, "run", lambda args, **kwargs: None)
    fixture = harness.managed_services.__wrapped__(harness.DIN_TEMP)

    next(fixture)
    command, kwargs = calls[0]
    assert command == ["bash", str(harness.FOUNDRY_DIR / "anvil.sh"), "--host", "127.0.0.1"]
    assert kwargs["cwd"] == harness.FOUNDRY_DIR
    assert kwargs["env"]["ANVIL_BIN"] == harness.ANVIL_BIN
    fixture.close()


def test_anvil_sh_carries_the_chain_flags_and_forwards_arguments(tmp_path):
    anvil_sh = Path(__file__).resolve().parents[1] / "foundry" / "anvil.sh"
    fake_anvil = tmp_path / "anvil"
    fake_anvil.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    fake_anvil.chmod(0o755)

    args = subprocess.run(
        ["bash", str(anvil_sh), "--host", "127.0.0.1"],
        env={"PATH": os.defpath, "ANVIL_BIN": str(fake_anvil)},
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    for flag, value in {"--chain-id": "1337", "--accounts": "70", "--block-time": "2",
                        "--code-size-limit": "4294967295", "--balance": "10000",
                        "--mnemonic": "test test test test test test test test test test test junk"}.items():
        assert args[args.index(flag) + 1] == value
    assert args[-2:] == ["--host", "127.0.0.1"]


def test_isolated_solc_seed_copies_compilers_without_linking(harness, monkeypatch, tmp_path):
    seed = tmp_path / "svm"
    (seed / "0.8.28").mkdir(parents=True)
    (seed / "0.8.28" / "solc-0.8.28").write_text("solc binary")
    (seed / ".global-version").write_text("0.8.28")
    monkeypatch.setattr(harness, "SVM_SEED_DIR", seed)

    harness._seed_solc(harness.DIN_TEMP)

    copied = harness.DIN_TEMP / "data" / "svm" / "0.8.28" / "solc-0.8.28"
    assert copied.read_text() == "solc binary"
    assert not copied.is_symlink() and not copied.parent.is_symlink()
    assert not (harness.DIN_TEMP / "data" / "svm" / ".global-version").exists()
    assert (seed / "0.8.28" / "solc-0.8.28").read_text() == "solc binary"


def test_isolated_solc_seed_rejects_a_directory_without_versions(harness, monkeypatch, tmp_path):
    monkeypatch.setattr(harness, "SVM_SEED_DIR", tmp_path / "empty")
    with pytest.raises(RuntimeError, match="no solc versions"):
        harness._seed_solc(harness.DIN_TEMP)


def test_isolated_foundry_build_runs_after_the_solc_seed(harness, monkeypatch):
    fake_services(harness, monkeypatch)
    order = []
    monkeypatch.setattr(harness, "_seed_solc", lambda din_tmp: order.append("seed"))
    monkeypatch.setattr(harness, "_build_foundry_contracts", lambda path: order.append("forge build"))
    monkeypatch.setattr(harness.subprocess, "run", lambda args, **kwargs: None)
    fixture = harness.managed_services.__wrapped__(harness.DIN_TEMP)

    next(fixture)
    assert order == ["seed", "forge build"]
    fixture.close()
