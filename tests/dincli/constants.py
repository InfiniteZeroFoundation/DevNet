"""Shared constants for the dincli integration test harness."""

from pathlib import Path

HARDHAT_RPC = "http://127.0.0.1:8545"
ARTIFACT_BASE = Path("/home/azureuser/projects/devnet/hardhat/artifacts/contracts")
# din_info.json lives inside the *imported* dincli package (files("dincli")).
# PYTHONPATH points the tests at the live devnet checkout, so deploys write there.
DIN_INFO_PATH = Path(__file__).parent.parent.parent / "dincli" / "config" / "din_info.json"
PYDIN_PYTHON = "/home/azureuser/my_venvs/pyDIN/bin/python"
TORCHENV_PYTHON = "/home/azureuser/my_venvs/torchenv/bin/python"


# Platform deployment (PR 13: transparent proxies).
# The four platform contracts are deployed + wired by the canonical hardhat
# script (OZ upgrades plugin), NOT by dincli — dincli only imports the
# resulting addresses via `system import-deployments`.
# Foundry migration: when foundry/ gains an equivalent forge deploy script,
# point HARDHAT_DIR/DEPLOY_CMD at it and keep DEPLOYMENTS_FILE as the handoff
# (the forge script should write the same JSON shape, or import-deployments
# grows a broadcast/run-latest.json parser).
HARDHAT_DIR = Path("/home/azureuser/projects/devnet/hardhat")
NPX_BIN = "/home/azureuser/.nvm/versions/node/v20.18.1/bin/npx"
# dincli network "local" is hardhat's "localhost" (standalone `npx hardhat node`)
DEPLOYMENTS_FILE = HARDHAT_DIR / "deployments" / "localhost.json"