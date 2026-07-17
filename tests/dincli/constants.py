"""Shared constants for the dincli integration test harness.

Every machine-specific path is derived from the repo checkout, the user's
home directory, or the environment — overridable via env vars (real
environment first, then `.env` at the repo root):

  PYDIN_PYTHON       interpreter used to run dincli commands
                     (default: ~/my_venvs/pyDIN/bin/python, else sys.executable)
  TORCHENV_PYTHON    interpreter with torch installed, used for train/evaluate
                     (default: ~/my_venvs/torchenv/bin/python, else sys.executable)
  NPX_BIN            npx binary used for hardhat compile/node/deploy
                     (default: newest ~/.nvm/versions/node/*/bin/npx, else `npx` on PATH)
  IPFS_BIN           ipfs binary (default: `ipfs` on PATH, else /usr/local/bin/ipfs)
  DIN_TEST_TMPDIR    scratch dir for config/cache isolation and logs
                     (default: ~/tempdir/dincli)
"""

import os
import shutil
import sys
from pathlib import Path

HARDHAT_RPC = "http://127.0.0.1:8545"

DEVNET_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_dotenv_values(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values
    except ImportError:
        return {}
    return {k: v for k, v in dotenv_values(dotenv_path=path).items() if v is not None}


_DOTENV = _load_dotenv_values(DEVNET_ROOT / ".env")


def _env(name: str) -> "str | None":
    """Real environment first, then the repo-root .env file."""
    return os.environ.get(name) or _DOTENV.get(name)
ARTIFACT_BASE = DEVNET_ROOT / "hardhat" / "artifacts" / "contracts"
# din_info.json lives inside the *imported* dincli package (files("dincli")).
# PYTHONPATH points the tests at the live devnet checkout, so deploys write there.
DIN_INFO_PATH = DEVNET_ROOT / "dincli" / "config" / "din_info.json"


def _resolve_python(env_var: str, default_venv: str) -> str:
    """Env override → conventional ~/my_venvs/<name> venv → current interpreter."""
    override = _env(env_var)
    if override:
        return override
    candidate = Path.home() / "my_venvs" / default_venv / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _resolve_npx() -> str:
    override = _env("NPX_BIN")
    if override:
        return override
    nvm_candidates = sorted(Path.home().glob(".nvm/versions/node/*/bin/npx"))
    if nvm_candidates:
        return str(nvm_candidates[-1])
    return shutil.which("npx") or "npx"


def _venv_site_packages(python_bin: str) -> str:
    """lib/pythonX.Y/site-packages of the venv that python_bin belongs to.

    Deliberately does NOT resolve symlinks: a venv's bin/python links to the
    base interpreter, whose site-packages is not the venv's.
    """
    venv_root = Path(python_bin).parent.parent
    matches = sorted(venv_root.glob("lib/python*/site-packages"))
    if matches:
        return str(matches[-1])
    return str(venv_root / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages")


PYDIN_PYTHON = _resolve_python("PYDIN_PYTHON", "pyDIN")
TORCHENV_PYTHON = _resolve_python("TORCHENV_PYTHON", "torchenv")
# Passed as --packages-dir so containerised services reuse the torchenv packages.
TORCHENV_SITE_PACKAGES = _env("TORCHENV_SITE_PACKAGES") or _venv_site_packages(TORCHENV_PYTHON)

NPX_BIN = _resolve_npx()
IPFS_BIN = _env("IPFS_BIN") or shutil.which("ipfs") or "/usr/local/bin/ipfs"

DIN_TEMP = Path(_env("DIN_TEST_TMPDIR") or str(Path.home() / "tempdir" / "dincli"))


# Platform deployment (PR 13: transparent proxies).
# The four platform contracts are deployed + wired by the canonical hardhat
# script (OZ upgrades plugin), NOT by dincli — dincli only imports the
# resulting addresses via `system import-deployments`.
# Foundry migration: when foundry/ gains an equivalent forge deploy script,
# point HARDHAT_DIR/DEPLOY_CMD at it and keep DEPLOYMENTS_FILE as the handoff
# (the forge script should write the same JSON shape, or import-deployments
# grows a broadcast/run-latest.json parser).
HARDHAT_DIR = DEVNET_ROOT / "hardhat"
# dincli network "local" is hardhat's "localhost" (standalone `npx hardhat node`)
DEPLOYMENTS_FILE = HARDHAT_DIR / "deployments" / "localhost.json"
