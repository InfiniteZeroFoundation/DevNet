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
  FORGE_BIN          forge binary used for the foundry deploy/upgrade scripts
                     (default: `forge` on PATH)
  IPFS_BIN           ipfs binary (default: `ipfs` on PATH, else /usr/local/bin/ipfs)
  DIN_TEST_TMPDIR    scratch dir for config/cache isolation and logs
                     (default: ~/tempdir/dincli)
  PLATFORM_DEPLOY_TOOLCHAIN   "foundry" or "hardhat" — which platform deploy
                     script test_deploy_platform_via_script runs (default:
                     "foundry", matching `dincli system import-deployments`'s
                     own default)
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
FORGE_BIN = _env("FORGE_BIN") or shutil.which("forge") or "forge"
IPFS_BIN = _env("IPFS_BIN") or shutil.which("ipfs") or "/usr/local/bin/ipfs"

DIN_TEMP = Path(_env("DIN_TEST_TMPDIR") or str(Path.home() / "tempdir" / "dincli"))


# Platform deployment (PR 13: transparent proxies; PR 35: foundry parity).
# The four platform contracts are deployed + wired by a canonical script, NOT
# by dincli — dincli only imports the resulting addresses via
# `system import-deployments`. Both toolchains write the same
# deployments/<network>.json address schema, so import-deployments accepts
# either one unmodified.
HARDHAT_DIR = DEVNET_ROOT / "hardhat"
FOUNDRY_DIR = DEVNET_ROOT / "foundry"

_VALID_DEPLOY_TOOLCHAINS = ("foundry", "hardhat")
PLATFORM_DEPLOY_TOOLCHAIN = (_env("PLATFORM_DEPLOY_TOOLCHAIN") or "foundry").lower()
if PLATFORM_DEPLOY_TOOLCHAIN not in _VALID_DEPLOY_TOOLCHAINS:
    raise ValueError(
        f"PLATFORM_DEPLOY_TOOLCHAIN must be one of {_VALID_DEPLOY_TOOLCHAINS}, "
        f"got {PLATFORM_DEPLOY_TOOLCHAIN!r}"
    )

_DEPLOY_TOOLCHAIN_DIR = {"hardhat": HARDHAT_DIR, "foundry": FOUNDRY_DIR}[PLATFORM_DEPLOY_TOOLCHAIN]
# dincli network "local" maps to "localhost" for both scripts' output filename.
# conftest.py's managed_services fixture starts the matching chain backend for
# PLATFORM_DEPLOY_TOOLCHAIN (Anvil for "foundry", Hardhat node for "hardhat"),
# both on HARDHAT_RPC / chain-id 1337 (hardhat.config.ts's "localhost" network
# is pinned to 1337 to match foundry/anvil.sh).
DEPLOYMENTS_FILE = _DEPLOY_TOOLCHAIN_DIR / "deployments" / "localhost.json"

# Standard dev-mnemonic account 0 (hardhat node and anvil both derive the same
# address from "test test test ... junk"). Registered as the "dindao" wallet
# by the bootstrap fixture; used as --sender for the foundry script, which
# broadcasts via --unlocked rather than signing with a local private key.
HARDHAT_DEV_ACCOUNT_0 = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
