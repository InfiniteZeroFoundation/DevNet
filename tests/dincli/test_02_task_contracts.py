"""
Phase 2 — Deploy task-level contracts and authorise slashers.

Account 1 (model owner) deploys DINTaskCoordinator and DINTaskAuditor.
Account 0 (DIN-Representative) then authorises both as slashers via dinrep.
Account 1 registers the slashers on the task contracts.

SDK candidates:
  deploy_task_contracts(network, account, coordinator_artifact, auditor_artifact)
    → {task_coordinator: addr, task_auditor: addr}
  authorize_slashers(network, din_rep_account, task_coordinator, task_auditor)
  register_slashers_on_task_contracts(network, model_owner_account)
"""

import json
import re

import pytest
from pathlib import Path

from tests.dincli.constants import ARTIFACT_BASE, DIN_INFO_PATH, DUMP_ABI_DIR

ARTIFACTS = {
    "task_coordinator": ARTIFACT_BASE / "DINTaskCoordinator.sol/DINTaskCoordinator.json",
    "task_auditor":     ARTIFACT_BASE / "DINTaskAuditor.sol/DINTaskAuditor.json",
}


@pytest.fixture(scope="module", autouse=True)
def ensure_artifacts():
    missing = [name for name, path in ARTIFACTS.items() if not path.exists()]
    if missing:
        pytest.skip(f"Foundry artifacts missing for: {missing} (run forge build).")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_connect_wallet_model_owner(run, state):
    """Switch to account 1 — model owner."""
    result = run(["system", "connect-demo-wallet", "modelowner"])
    assert result.returncode == 0


def test_eth_balance_model_owner(run):
    """Confirm model owner has ETH (sanity check against fresh Hardhat node)."""
    result = run(["system", "--eth-balance"])
    assert result.returncode == 0
    assert "ETH" in result.stdout or "eth" in result.stdout.lower()


def _deployed_address(stdout: str, contract: str) -> str:
    """The address in the CLI's "✓ <contract> contract deployed at: 0x…" line."""
    match = re.search(rf"{contract} contract deployed at:\s*(0x[a-fA-F0-9]{{40}})", stdout)
    assert match, f"No deployed {contract} address in output:\n{stdout}"
    return match.group(1)


def test_deploy_task_coordinator(run, state):
    """Deploy DINTaskCoordinator as model owner.

    --model-id is left to its default (DINModelRegistry.totalModels() = 0),
    and the deploy sets DinToken on the new coordinator.

    SDK candidate: deploy_task_coordinator(network, account, artifact_path)
    """
    result = run([
        "model-owner", "deploy", "task-coordinator",
        "--artifact", str(ARTIFACTS["task_coordinator"]),
    ], timeout=180)
    assert result.returncode == 0
    assert "totalModels() = 0" in result.stdout
    assert "DinToken set on DINTaskCoordinator" in result.stdout
    state["task_coordinator_address"] = _deployed_address(result.stdout, "DINTaskCoordinator")


def test_dump_abi_task_coordinator(run):
    result = run([
        "system", "dump-abi", "--output", str(DUMP_ABI_DIR),
        "--artifact", str(ARTIFACTS["task_coordinator"]),
    ])
    assert result.returncode == 0


def test_deploy_task_auditor(run, state):
    """Deploy DINTaskAuditor as model owner.

    --model-id defaults to the coordinator's modelId(); the deploy sets
    DinToken on the new auditor (rewards deposit needs it) before linking
    it to the coordinator.

    SDK candidate: deploy_task_auditor(network, account, artifact_path)
    """
    result = run([
        "model-owner", "deploy", "task-auditor",
        "--artifact", str(ARTIFACTS["task_auditor"]),
    ], timeout=180)
    assert result.returncode == 0
    assert "DinToken set on DINTaskAuditor" in result.stdout
    state["task_auditor_address"] = _deployed_address(result.stdout, "DINTaskAuditor")


def test_dump_abi_task_auditor(run):
    result = run([
        "system", "dump-abi", "--output", str(DUMP_ABI_DIR),
        "--artifact", str(ARTIFACTS["task_auditor"]),
    ])
    assert result.returncode == 0


def test_din_rep_authorizes_task_coordinator_as_slasher(run, state):
    """DIN-Representative (account 0) authorises TaskCoordinator as slasher.

    SDK candidate: dinrep_add_slasher(network, account, task_coordinator=addr)
    """
    run(["system", "connect-demo-wallet", "dinrep"])
    result = run(["dinrep", "add-slasher", "--taskCoordinator"])
    assert result.returncode == 0


def test_din_rep_authorizes_task_auditor_as_slasher(run):
    """DIN-Representative (account 0) authorises TaskAuditor as slasher."""
    result = run(["dinrep", "add-slasher", "--taskAuditor"])
    assert result.returncode == 0


def test_model_owner_registers_task_coordinator_slasher(run):
    """Model owner (account 1) registers TaskCoordinator slasher on-contract.

    SDK candidate: model_owner_add_slasher(network, account, task_coordinator=addr)
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "add-slasher", "--taskCoordinator"])
    assert result.returncode == 0


def test_model_owner_registers_task_auditor_slasher(run):
    """Model owner (account 1) registers TaskAuditor slasher on-contract."""
    result = run(["model-owner", "add-slasher", "--taskAuditor"])
    assert result.returncode == 0
