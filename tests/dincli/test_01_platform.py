"""
Phase 1 — Deploy platform-level contracts (PR 13: transparent proxies).

The four platform contracts (DinToken, DinCoordinator, DinValidatorStake,
DINModelRegistry) are upgradeable transparent proxies. They are deployed and
wired by the canonical hardhat script — token → coordinator →
dinToken.setCoordinator → stake → dinCoordinator.updateValidatorStakeContract
→ registry — which runs through the OpenZeppelin upgrades plugin
(storage-layout validation + .openzeppelin/ manifest used by later upgrades):

    cd hardhat && npx hardhat run scripts/deploy-platform.ts --network localhost

dincli then imports the script's output (hardhat/deployments/localhost.json)
into din_info.json via `dincli system import-deployments`.

INTERIM SCAFFOLDING — this script+import flow is the *rejected* Option A of
the committed decision record
Documentation/technical/upgradable-contracts/proxy-deployment-architecture.md,
kept here only to unblock the harness. The chosen target (its Option C) is
native web3.py proxy deployment inside `dindao deploy`
(backlog: Developer/issues/dincli-native-proxy-deployment.md); when that
lands, restore per-contract `dindao deploy ...` tests here and demote
import-deployments to a sync-utility test.

Foundry migration: foundry/ carries the same contracts but has no deploy
script yet. If the script flow is still in use by then, only
test_deploy_platform_via_script changes (forge script ... --broadcast); the
import/verification tests stay as long as the forge script writes the same
deployments JSON shape (preferred) or `system import-deployments` learns to
parse foundry's broadcast/<Script>.s.sol/<chainid>/run-latest.json.

SDK candidates:
  deploy_platform(network) → addresses dict   (wraps the deploy script)
  import_deployments(network, file) → dict    (body of `system import-deployments`)
  dump_abi(artifact_path, official=True)
"""

import json
import subprocess
import pytest
from pathlib import Path

from tests.dincli.constants import (
    ARTIFACT_BASE,
    DIN_INFO_PATH,
    HARDHAT_DIR,
    NPX_BIN,
    DEPLOYMENTS_FILE,
)

pytestmark = pytest.mark.integration

ARTIFACTS = {
    "coordinator":     ARTIFACT_BASE / "DinCoordinator.sol/DinCoordinator.json",
    "validator_stake": ARTIFACT_BASE / "DinValidatorStake.sol/DinValidatorStake.json",
    "registry":        ARTIFACT_BASE / "DINModelRegistry.sol/DINModelRegistry.json",
    "token":           ARTIFACT_BASE / "DinToken.sol/DinToken.json",
}

# deployments/localhost.json keys → the state/din_info keys used by later phases
DEPLOYMENT_KEYS = {
    "dinCoordinator": ("coordinator", "coordinator_address"),
    "dinToken": ("token", "token_address"),
    "dinValidatorStake": ("stake", "stake_address"),
    "dinModelRegistry": ("registry", "registry_address"),
}


def _assert_artifacts_exist():
    missing = [name for name, path in ARTIFACTS.items() if not path.exists()]
    if missing:
        pytest.skip(
            f"Hardhat artifacts missing for: {missing}. "
            "Run:  cd hardhat && npx hardhat compile"
        )


@pytest.fixture(scope="module", autouse=True)
def ensure_artifacts():
    _assert_artifacts_exist()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_connect_wallet_dindao(run, state):
    """Switch to the dindao wallet (account 0, DIN-Representative)."""
    result = run(["system", "connect-wallet", "dindao"])
    assert result.returncode == 0
    state["representative_connected"] = True


def test_deploy_platform_via_script(state):
    """Deploy the four platform proxies + wiring via the canonical script.

    The deployer is hardhat signer 0 — the same key as the dindao wallet.
    SDK candidate: deploy_platform(network) — a thin wrapper around this
    subprocess (or, post-foundry-migration, around `forge script`).
    """
    result = subprocess.run(
        [NPX_BIN, "hardhat", "run", "scripts/deploy-platform.ts", "--network", "localhost"],
        cwd=str(HARDHAT_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr)
    assert result.returncode == 0, f"deploy-platform.ts failed:\n{result.stderr}"

    deployments = json.loads(DEPLOYMENTS_FILE.read_text())
    for key in (*DEPLOYMENT_KEYS, "proxyAdmin"):
        assert deployments.get(key, "").startswith("0x"), f"missing {key} in {DEPLOYMENTS_FILE}"
    state["proxy_admin_address"] = deployments["proxyAdmin"]


def test_import_deployments_into_din_info(run, state):
    """Point dincli at the deployed proxies.

    SDK candidate: import_deployments(network, file) — body of
    `dincli system import-deployments`.
    """
    result = run([
        "system", "import-deployments",
        "--file", str(DEPLOYMENTS_FILE),
    ])
    assert result.returncode == 0

    din_info = json.loads(DIN_INFO_PATH.read_text())["local"]
    deployments = json.loads(DEPLOYMENTS_FILE.read_text())
    for dep_key, (info_key, state_key) in DEPLOYMENT_KEYS.items():
        assert din_info[info_key] == deployments[dep_key], (
            f"din_info['{info_key}'] not updated from deployments['{dep_key}']"
        )
        state[state_key] = din_info[info_key]
    assert din_info.get("proxy_admin") == deployments["proxyAdmin"]


def test_dump_abi_coordinator(run):
    """Dump coordinator ABI into bundled abis/."""
    result = run([
        "system", "dump-abi", "--official",
        "--artifact", str(ARTIFACTS["coordinator"]),
    ])
    assert result.returncode == 0


def test_dump_abi_token(run):
    result = run([
        "system", "dump-abi", "--official",
        "--artifact", str(ARTIFACTS["token"]),
    ])
    assert result.returncode == 0


def test_dump_abi_validator_stake(run):
    result = run([
        "system", "dump-abi", "--official",
        "--artifact", str(ARTIFACTS["validator_stake"]),
    ])
    assert result.returncode == 0


def test_dump_abi_registry(run):
    result = run([
        "system", "dump-abi", "--official",
        "--artifact", str(ARTIFACTS["registry"]),
    ])
    assert result.returncode == 0


def test_system_din_info_shows_all_addresses(run, state):
    """Sanity check: 'system din-info' reports all four platform contract addresses."""
    result = run(["system", "din-info"])
    assert result.returncode == 0
    for key in ("coordinator_address", "token_address", "stake_address", "registry_address"):
        addr = state.get(key, "")
        if addr:
            assert addr.lower() in result.stdout.lower(), (
                f"{key} ({addr}) not found in 'system din-info' output"
            )
