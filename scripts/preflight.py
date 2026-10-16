#!/usr/bin/env python3
"""
scripts/preflight.py — environment preflight check for DevNet contributors.

Stdlib-only for the core checks (Python, forge, anvil, node_modules, package
importability).  Pass --network <name> to also verify .env.<name>, the
configured RPC endpoint, and the IPFS config (requires a working dincli install).

Exit 0  — all required checks passed (warnings may still be printed).
Exit 1  — at least one required check failed.
"""
import argparse
import importlib
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ── output helpers ────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"[OK]     {msg}")


def _warn(msg: str, fix: str = "") -> None:
    print(f"[WARN]   {msg}")
    if fix:
        print(f"          → {fix}")


def _missing(msg: str, fix: str = "") -> None:
    print(f"[MISSING] {msg}")
    if fix:
        print(f"          → {fix}")


# ── individual checks ─────────────────────────────────────────────────────────

def _check_python() -> int:
    vi = sys.version_info
    label = f"Python {vi.major}.{vi.minor}.{vi.micro}"
    if (vi.major, vi.minor) >= (3, 12):
        _ok(f"{label}  (>= 3.12 required)")
        return 0
    _missing(f"{label} is below 3.12", fix="Install Python 3.12+: https://www.python.org/downloads/")
    return 1


def _check_binary(name: str, install_hint: str) -> int:
    path = shutil.which(name)
    if path:
        _ok(f"{name} found: {path}")
        return 0
    _missing(f"{name} not found on PATH", fix=install_hint)
    return 1


def _check_node_modules() -> None:
    node_modules = _REPO_ROOT / "foundry" / "node_modules"
    if node_modules.is_dir():
        _ok("foundry/node_modules present")
    else:
        _warn(
            "foundry/node_modules not found — forge test will race fetching @openzeppelin/upgrades-core",
            fix="cd foundry && npm ci",
        )


def _check_importable(module: str, package: str, optional: bool = False) -> None:
    try:
        importlib.import_module(module)
        _ok(f"{package} importable")
    except ImportError:
        if optional:
            _warn(
                f"{package} not importable (optional — pytest skips torch-dependent tests without it)",
                fix="pip install -e .[test]",
            )
        else:
            _warn(
                f"{package} not importable",
                fix="pip install -e .",
            )


# ── network checks (require --network, may use dincli) ────────────────────────

def _network_checks(network: str) -> int:
    failures = 0
    env_file = _REPO_ROOT / f".env.{network}"

    if not env_file.exists():
        _warn(
            f".env.{network} not found",
            fix=f"Copy .env.{network}.example and fill in your RPC URL and private keys",
        )
        return failures  # can't proceed without the env file

    _ok(f".env.{network} found")

    rpc_url = _read_env_value(env_file, f"{network.upper()}_RPC_URL")
    if not rpc_url:
        _warn(
            f"No RPC URL in .env.{network}",
            fix=f"Set {network.upper()}_RPC_URL=<url> in .env.{network}",
        )
    else:
        failures += _check_rpc(rpc_url)

    try:
        from dincli.services.ipfs import resolve_ipfs_config
        resolve_ipfs_config()
        _ok("resolve_ipfs_config() succeeded")
    except ImportError:
        _warn("dincli not importable — skipping IPFS config check", fix="pip install -e .")
    except Exception as exc:
        _warn(f"IPFS config not resolved: {exc}", fix="Configure IPFS_NODE_URL or Filebase credentials in .env")

    return failures


def _read_env_value(env_file: Path, key: str) -> str:
    prefix = key + "="
    with open(env_file) as fh:
        for line in fh:
            stripped = line.strip()
            if stripped.startswith(prefix):
                return stripped[len(prefix):].strip()
    return ""


def _check_rpc(url: str) -> int:
    payload = json.dumps({"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}).encode()
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        chain_id = int(result["result"], 16)
        _ok(f"RPC reachable: {url}  (chainId {chain_id})")
        return 0
    except Exception as exc:
        _warn(f"RPC not reachable ({url}): {exc}", fix="Check your RPC URL and internet connection")
        return 0  # network connectivity is always a warning, not a hard failure


# ── main ──────────────────────────────────────────────────────────────────────

_FOUNDRY_INSTALL = (
    "curl -L https://foundry.paradigm.xyz | bash && foundryup"
    "  (then restart your shell)"
)


def run(network: str | None = None) -> int:
    failures = 0

    failures += _check_python()
    failures += _check_binary("forge", _FOUNDRY_INSTALL)
    failures += _check_binary("anvil", _FOUNDRY_INSTALL)

    _check_node_modules()

    _check_importable("eth_account",  "eth-account")
    _check_importable("multibase",    "py-multibase")
    _check_importable("web3",         "web3")
    _check_importable("torch",        "torch", optional=True)

    if network:
        failures += _network_checks(network)

    return failures


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preflight check for DevNet contributor environment.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/preflight.py\n"
            "  python scripts/preflight.py --network sepolia_op_devnet\n"
            "  python scripts/preflight.py --network local\n"
        ),
    )
    parser.add_argument(
        "--network", metavar="NAME",
        help=(
            "Also check .env.<NAME>, the configured RPC endpoint, and the IPFS config. "
            "Requires a working dincli install for the IPFS check. "
            "Example values: local, sepolia_op_devnet."
        ),
    )
    args = parser.parse_args()
    failures = run(network=args.network)
    if failures:
        print(f"\n{failures} required check(s) failed.  Fix the issues above before continuing.")
        sys.exit(1)
    print("\nAll required checks passed.")


if __name__ == "__main__":
    main()
