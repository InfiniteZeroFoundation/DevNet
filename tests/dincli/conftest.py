"""
Integration test harness for dincli — runs against a local Hardhat node or
local Anvil node (chain backend picked by PLATFORM_DEPLOY_TOOLCHAIN, see
tests/dincli/constants.py).

The conftest automatically handles all prerequisites:
  1. Compiles Solidity contracts via  npx hardhat compile  (task-level
     contract deploys and dump-abi tests always need hardhat's ABIs/bytecode,
     regardless of which toolchain deploys the platform contracts); also runs
     `forge build` when PLATFORM_DEPLOY_TOOLCHAIN is "foundry"
  2. Kills any running chain node and starts a fresh one (clean EVM state) —
     Hardhat node for the "hardhat" toolchain, Anvil for "foundry" (both
     listen on HARDHAT_RPC / chain-id 1337, so the rest of the harness is
     unaffected by which one is running)
  3. Ensures the IPFS daemon is running (starts it if not already up)
  4. Docker daemon must be running externally (required for client train-lms /
     aggregation / auditor evaluate). Docker is not started automatically.

Run (fail-fast — recommended, because every test depends on the previous one):
  pytest tests/dincli/ -v -x -m integration --tb=short 2>&1 | tee ~/tempdir/dincli/results/last_run.txt

All test output / logs are written to ~/tempdir/dincli/ (override with
DIN_TEST_TMPDIR; see tests/dincli/constants.py for all env overrides).
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

from tests.dincli.constants import (
    HARDHAT_RPC,
    ARTIFACT_BASE,
    DIN_INFO_PATH,
    PYDIN_PYTHON,
    TORCHENV_PYTHON,
    DEVNET_ROOT,
    HARDHAT_DIR,
    FOUNDRY_DIR,
    FORGE_BIN,
    PLATFORM_DEPLOY_TOOLCHAIN,
    DIN_TEMP,
    NPX_BIN,
    IPFS_BIN,
)


# ---------------------------------------------------------------------------
# Service helpers
# ---------------------------------------------------------------------------


def _hardhat_is_running() -> bool:
    try:
        # "jsonrpc": "2.0": Specifies the version of the JSON-RPC protocol 
        # "method": "eth_chainId": The name of the API method you are invoking on the Hardhat node. eth_chainId requests the current chain ID (network identifier) of the node (for example, it returns 0x539 which is hex for 1337).
        # "params": []: An array of arguments passed to the method. Since eth_chainId does not require any parameters, it is sent as an empty list.
        # "id": 1: A request identifier. Since JSON-RPC can be asynchronous or batched, the node will include this same ID in its response so the client knows exactly which request the response belongs to.

        resp = requests.post(
            HARDHAT_RPC,
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
            timeout=3,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _anvil_is_running() -> bool:
    """Same liveness probe as _hardhat_is_running — anvil answers the same
    eth_chainId JSON-RPC call on the same port."""
    try:
        resp = requests.post(
            HARDHAT_RPC,
            json={"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1},
            timeout=3,
        )
        return resp.status_code == 200
    except Exception:
        return False


def _ipfs_is_running() -> bool:
    try:
        resp = requests.post("http://127.0.0.1:5001/api/v0/version", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


def _compile_contracts(results_dir: Path) -> None:
    """Run npx hardhat compile. Aborts the session on failure."""
    print("\n[setup] Compiling Solidity contracts...")
    log_path = results_dir / "hardhat_compile.log"
    result = subprocess.run(
        [NPX_BIN, "hardhat", "compile"],
        cwd=str(HARDHAT_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        pytest.exit(
            f"[setup] Contract compilation failed (see {log_path}):\n{result.stderr[-2000:]}"
        )
    print("[setup] Contracts compiled successfully.")


def _build_foundry_contracts(results_dir: Path) -> None:
    """Run forge build. Aborts the session on failure.

    Needed only when PLATFORM_DEPLOY_TOOLCHAIN is "foundry" — DeployPlatform.s.sol
    reads compiled artifacts under foundry/out/, separate from hardhat/artifacts/.
    """
    print("\n[setup] Building Foundry contracts...")
    log_path = results_dir / "forge_build.log"
    result = subprocess.run(
        [FORGE_BIN, "build"],
        cwd=str(FOUNDRY_DIR),
        capture_output=True,
        text=True,
        timeout=180,
    )
    log_path.write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        pytest.exit(
            f"[setup] Foundry contract build failed (see {log_path}):\n{result.stderr[-2000:]}"
        )
    print("[setup] Foundry contracts built successfully.")


def _start_fresh_hardhat_node(results_dir: Path) -> subprocess.Popen:
    """
    Kill any running Hardhat node, start a fresh one, and wait until it is ready.
    Returns the Popen handle so it can be killed at session teardown.
    """
    # Kill every existing hardhat node process
    subprocess.run(["pkill", "-f", "hardhat node"], capture_output=True)
    # Also kill any node processes holding port 8545
    subprocess.run(["fuser", "-k", "8545/tcp"], capture_output=True)
    time.sleep(3)  # give port time to release

    log_path = results_dir / "hardhat_node.log"
    log_fh = open(log_path, "w", encoding="utf-8")

    # Inherit PATH so npx can find hardhat
    env = os.environ.copy()
    proc = subprocess.Popen(
        [NPX_BIN, "hardhat", "node"],
        cwd=str(HARDHAT_DIR),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )

    print("[setup] Waiting for Hardhat node to start...", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        if _hardhat_is_running():
            print(" ready.")
            return proc

    log_fh.flush()
    pytest.exit(
        f"[setup] Hardhat node did not start after 40 s "
        f"(see {log_path} for details)"
    )


def _start_fresh_anvil_node(results_dir: Path) -> subprocess.Popen:
    """
    Kill any running Anvil node, start a fresh one via foundry/anvil.sh, and
    wait until it is ready. Returns the Popen handle so it can be killed at
    session teardown.

    foundry/anvil.sh pins --chain-id 1337, matching hardhat.config.ts's
    "localhost" network, so deployments/localhost.json naming and dincli's
    "local" -> "localhost" network mapping stay valid under either toolchain.
    """
    # Kill every existing anvil process
    subprocess.run(["pkill", "-f", "anvil"], capture_output=True)
    # Also kill any process holding port 8545
    subprocess.run(["fuser", "-k", "8545/tcp"], capture_output=True)
    time.sleep(3)  # give port time to release

    log_path = results_dir / "anvil_node.log"
    log_fh = open(log_path, "w", encoding="utf-8")

    # Inherit PATH so the script can find the anvil binary
    env = os.environ.copy()
    proc = subprocess.Popen(
        ["bash", str(FOUNDRY_DIR / "anvil.sh")],
        cwd=str(FOUNDRY_DIR),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        env=env,
    )

    print("[setup] Waiting for Anvil node to start...", end="", flush=True)
    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        if _anvil_is_running():
            print(" ready.")
            return proc

    log_fh.flush()
    pytest.exit(
        f"[setup] Anvil node did not start after 40 s "
        f"(see {log_path} for details)"
    )


def _ensure_ipfs_running(results_dir: Path):
    """
    Start the IPFS daemon if it is not already running.
    Returns the Popen handle if we started it, else None.
    """
    if _ipfs_is_running():
        print("[setup] IPFS daemon already running.")
        return None

    print("[setup] Starting IPFS daemon...", end="", flush=True)
    log_path = results_dir / "ipfs_daemon.log"
    log_fh = open(log_path, "w", encoding="utf-8")

    proc = subprocess.Popen(
        [IPFS_BIN, "daemon"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    for _ in range(15):
        time.sleep(1)
        print(".", end="", flush=True)
        if _ipfs_is_running():
            print(" ready.")
            return proc

    print(f"\n[WARNING] IPFS daemon did not respond after 30 s (see {log_path}).")
    return proc


# ---------------------------------------------------------------------------
# Temp directory
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def din_tmp():
    """
    Fixed temp directory for config/cache isolation and test artefacts.

    config/ and cache/ are wiped at session start; results/ accumulates runs.
    """
    DIN_TEMP.mkdir(parents=True, exist_ok=True)
    for subdir in ("config", "cache"):
        d = DIN_TEMP / subdir
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    (DIN_TEMP / "results").mkdir(exist_ok=True)
    return DIN_TEMP


# ---------------------------------------------------------------------------
# Managed services — compile, chain node, IPFS
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def managed_services(din_tmp):
    """
    Compile contracts, start a fresh chain node, and ensure IPFS is running.

    The chain node is Anvil when PLATFORM_DEPLOY_TOOLCHAIN is "foundry", else
    the Hardhat node — either way it ends up listening on HARDHAT_RPC / chain-id
    1337, so nothing downstream (task-contract deploys, dincli itself) needs to
    know which one is running.

    This is the first session fixture that runs (all other autouse fixtures
    depend on it transitively via bootstrap). On teardown, any processes we
    started are terminated.
    """
    results_dir = din_tmp / "results"
    chain_proc = None
    ipfs_proc = None

    # 1. Compile contracts — task-level contract deploys and dump-abi tests
    #    always need hardhat's ABIs/bytecode, regardless of deploy toolchain.
    _compile_contracts(results_dir)
    if PLATFORM_DEPLOY_TOOLCHAIN == "foundry":
        _build_foundry_contracts(results_dir)

    # 2. Fresh chain node (kill and restart for clean EVM state)
    if PLATFORM_DEPLOY_TOOLCHAIN == "foundry":
        chain_proc = _start_fresh_anvil_node(results_dir)
    else:
        chain_proc = _start_fresh_hardhat_node(results_dir)

    # 3. IPFS daemon (start if not already up)
    ipfs_proc = _ensure_ipfs_running(results_dir)

    yield

    # Teardown — stop the processes we started
    print("\n[teardown] Stopping managed services...")
    if chain_proc and chain_proc.poll() is None:
        chain_proc.terminate()
        try:
            chain_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chain_proc.kill()
    if ipfs_proc and ipfs_proc.poll() is None:
        ipfs_proc.terminate()
        try:
            ipfs_proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            ipfs_proc.kill()
    shutil.rmtree(str(DIN_TEMP), ignore_errors=True)


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def din_env(din_tmp):
    """
    Subprocess environment with isolated config/cache dirs and local network RPC.

    - XDG_CONFIG_HOME + XDG_CACHE_HOME point to din_tmp so tests never touch
      the real ~/.config/dincli wallet.
    - PYTHONPATH is set to the repo root so `python -m dincli.main` finds the
      local dincli/ package without a pip install into the venv.
    - LOCAL_RPC_URL points at the Hardhat node.
    """
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(din_tmp / "config")
    env["XDG_CACHE_HOME"]  = str(din_tmp / "cache")
    env["LOCAL_RPC_URL"]   = HARDHAT_RPC
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(DEVNET_ROOT) + (":" + existing if existing else "")
    env["NO_COLOR"] = "1"
    env["TERM"]     = "dumb"
    return env


@pytest.fixture(scope="session")
def workdir():
    """
    Working directory for all subprocess calls — always the repo root.

    dincli resolves task dirs and .env relative to os.getcwd(), and the local
    dincli/ package is found via PYTHONPATH from here.
    """

    shutil.copy(str(DEVNET_ROOT / ".env"), str(DIN_TEMP / ".env"))
    return DIN_TEMP


@pytest.fixture(scope="session")
def din_info_backup():
    """Back up din_info.json before deploys overwrite it; restore after session."""
    original = DIN_INFO_PATH.read_text(encoding="utf-8")
    yield
    DIN_INFO_PATH.write_text(original, encoding="utf-8")


@pytest.fixture(scope="session")
def state():
    """
    Shared mutable dict passed across phases.

    Keys populated during the run:
      coordinator_address, token_address, stake_address, registry_address,
      task_coordinator_address, task_auditor_address, model_id (int)
    """
    return {}


# ---------------------------------------------------------------------------
# Command runner
# ---------------------------------------------------------------------------


def run_cmd(
    args: list[str],
    env: dict,
    cwd: Path,
    *,
    python: str = PYDIN_PYTHON,
    check: bool = True,
    input_text: str | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess:
    """
    Run  `python -m dincli.main <args>`  in a subprocess.

    When check=True and the process exits non-zero, calls pytest.fail() with
    the full command, exit code, stdout, and stderr — immediately pointing to
    the failing command without cascading further (use -x for fail-fast).
    """
    cmd = [python, "-m", "dincli.main"] + args
    result = subprocess.run(
        cmd,
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        input=input_text,
        timeout=timeout,
    )
    print(f"\n$ dincli {' '.join(args)}  (exit {result.returncode})")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if check and result.returncode != 0:
        pytest.fail(
            f"\nCommand failed: {' '.join(args)}\n"
            f"Exit code: {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    return result


@pytest.fixture(scope="session")
def run(din_env, workdir):
    """
    Bound version of run_cmd with the session env and workdir pre-filled.

    Usage:
        run(["system", "where"])
        run(["model-owner", "model", "create-genesis-model"],
            input_text="y\\ny\\ny\\ny\\ny\\ny\\n", timeout=300)
    """

    def _run(
        args: list[str],
        *,
        python: str = PYDIN_PYTHON,
        check: bool = True,
        input_text: str | None = None,
        timeout: int = 120,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess:
        return run_cmd(
            args,
            din_env,
            cwd=cwd or workdir,
            python=python,
            check=check,
            input_text=input_text,
            timeout=timeout,
        )

    return _run


# ---------------------------------------------------------------------------
# Phase bootstrap — runs once before any test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def bootstrap(managed_services, din_info_backup, run):
    """
    Configure demo mode and local network, and register the named role
    wallets (account 0 = dindao / DIN-Representative, account 1 = modelowner).
    Tests switch between them with `system connect-wallet <name>`; dynamic
    per-account roles in test_04 self-register via
    `register-wallet --account N --name acctN --yes --connect`.
    Depends on managed_services so the Hardhat node is guaranteed to be
    running before the first command.
    """
    run(["system", "init"])
    run(["system", "configure-demo"])
    run(["system", "configure-network", "--network", "local"])
    run(["system", "register-wallet", "--account", "0", "--name", "dindao", "--yes"])
    run(["system", "register-wallet", "--account", "1", "--name", "modelowner", "--yes"])


# ---------------------------------------------------------------------------
# pytest markers
# ---------------------------------------------------------------------------


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests that require a live Hardhat node, IPFS daemon, and Docker",
    )


# Every test in this directory needs a live chain, an IPFS daemon and Docker.
# Marking happens here rather than per-file so a new module cannot silently
# opt out and get itself run in CI. The path test is essential, not cosmetic:
# this hook receives every collected item in the session, not just ours, so
# without it the whole suite is marked integration and CI passes running
# nothing. See plan 2.6.
_INTEGRATION_DIR = Path(__file__).parent


def pytest_collection_modifyitems(config, items):
    for item in items:
        path = Path(str(item.fspath))
        if path == _INTEGRATION_DIR or _INTEGRATION_DIR in path.parents:
            item.add_marker(pytest.mark.integration)
