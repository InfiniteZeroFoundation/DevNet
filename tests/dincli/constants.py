"""Shared constants for the dincli integration test harness."""

from pathlib import Path

HARDHAT_RPC = "http://127.0.0.1:8545"
ARTIFACT_BASE = Path("/home/azureuser/projects/devnet/hardhat/artifacts/contracts")
DIN_INFO_PATH = Path(__file__).parent.parent.parent / "dincli" / "config" / "din_info.json"
PYDIN_PYTHON = "/home/azureuser/my_venvs/pyDIN/bin/python"
TORCHENV_PYTHON = "/home/azureuser/my_venvs/torchenv/bin/python"
