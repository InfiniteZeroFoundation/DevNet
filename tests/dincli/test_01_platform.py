"""
Phase 1 — Deploy platform-level contracts.

Deploys the four platform contracts as account 0 (DIN-Representative):
  DinCoordinator  (also deploys DinToken internally)
  DinValidatorStake
  DINModelRegistry

SDK candidates:
  deploy_platform_contracts(network, account) → addresses dict
  dump_abi(artifact_path, official=True)
"""

import json
import pytest
from pathlib import Path

from tests.dincli.constants import ARTIFACT_BASE, DIN_INFO_PATH

pytestmark = pytest.mark.integration

ARTIFACTS = {
    "coordinator":     ARTIFACT_BASE / "DinCoordinator.sol/DinCoordinator.json",
    "validator_stake": ARTIFACT_BASE / "DinValidatorStake.sol/DinValidatorStake.json",
    "registry":        ARTIFACT_BASE / "DINModelRegistry.sol/DINModelRegistry.json",
    "token":           ARTIFACT_BASE / "DinToken.sol/DinToken.json",
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


def test_connect_wallet_account0(run, state):
    """Switch to account 0 (DIN-Representative)."""
    result = run(["system", "connect-wallet", "--account", "0"])
    assert result.returncode == 0
    state["representative_connected"] = True


def test_deploy_din_coordinator(run, state):
    """Deploy DinCoordinator (also bootstraps DinToken).

    SDK candidate: deploy_din_coordinator(network, account, artifact_path)
    """
    result = run([
        "dindao", "deploy", "din-coordinator",
        "--artifact", str(ARTIFACTS["coordinator"]),
    ], timeout=180)
    assert result.returncode == 0

    din_info = json.loads(DIN_INFO_PATH.read_text())
    state["coordinator_address"] = din_info["local"]["coordinator"]
    state["token_address"] = din_info["local"]["token"]
    assert state["coordinator_address"].startswith("0x")
    assert state["token_address"].startswith("0x")


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


def test_deploy_din_validator_stake(run, state):
    """Deploy DinValidatorStake.

    SDK candidate: deploy_din_validator_stake(network, account, artifact_path)
    """
    result = run([
        "dindao", "deploy", "din-validator-stake",
        "--artifact", str(ARTIFACTS["validator_stake"]),
    ], timeout=180)
    assert result.returncode == 0

    din_info = json.loads(DIN_INFO_PATH.read_text())
    state["stake_address"] = din_info["local"]["stake"]
    assert state["stake_address"].startswith("0x")


def test_dump_abi_validator_stake(run):
    result = run([
        "system", "dump-abi", "--official",
        "--artifact", str(ARTIFACTS["validator_stake"]),
    ])
    assert result.returncode == 0


def test_deploy_din_model_registry(run, state):
    """Deploy DINModelRegistry.

    SDK candidate: deploy_din_model_registry(network, account, artifact_path)
    """
    result = run([
        "dindao", "deploy", "din-model-registry",
        "--artifact", str(ARTIFACTS["registry"]),
    ], timeout=180)
    assert result.returncode == 0

    din_info = json.loads(DIN_INFO_PATH.read_text())
    state["registry_address"] = din_info["local"]["registry"]
    assert state["registry_address"].startswith("0x")


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
