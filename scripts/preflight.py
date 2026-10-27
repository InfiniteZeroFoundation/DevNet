#!/usr/bin/env python3
"""
scripts/preflight.py — environment preflight check for DevNet contributors.

For contributors working from a clone of this repo. Participants who installed
dincli from the wheel (per Documentation/public/setup.md) can skip this script
— forge and anvil are not in their setup requirements.

Stdlib-only for the core checks (Python, forge, anvil, node_modules, package
importability).  Pass --network <name> to also verify the configured RPC
endpoint and the IPFS config (requires a working dincli install).

Exit 0  — all required checks passed (warnings may still be printed).
Exit 1  — at least one required check failed.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Expected chain IDs per network (WARN on mismatch, not hard fail)
_EXPECTED_CHAIN_IDS: dict[str, int] = {
    "sepolia_op_devnet": 11155420,
    "local": 1337,
}

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
    except Exception:  # catches ImportError, OSError (native libs), etc.
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


def _sanitize_url(url: str) -> str:
    """Return URL with path, query, and credentials stripped — safe for logging."""
    try:
        p = urllib.parse.urlparse(url)
        netloc = p.hostname or ""
        if p.port:
            netloc += f":{p.port}"
        return urllib.parse.urlunparse((p.scheme, netloc, "***", "", "", ""))
    except Exception:
        return "<url>"


# ── network checks (require --network, may use dincli) ────────────────────────

def _read_env_value(env_file: Path, key: str) -> str:
    """Read a single env var value from a .env-style file (dotenv-compatible)."""
    with open(env_file, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            # strip optional 'export ' prefix
            if stripped.startswith("export "):
                stripped = stripped[7:].lstrip()
            if "=" not in stripped:
                continue
            k, _, v = stripped.partition("=")
            if k.strip() != key:
                continue
            v = v.strip()
            # quoted value: extract between matching quotes
            if v and v[0] in ('"', "'"):
                quote = v[0]
                end = v.find(quote, 1)
                return v[1:end] if end != -1 else v[1:]
            # unquoted: strip trailing inline comment (` #` pattern)
            comment_idx = v.find(" #")
            if comment_idx != -1:
                v = v[:comment_idx].rstrip()
            return v
    return ""


def _check_rpc(url: str, network: str | None = None) -> int:
    safe_url = _sanitize_url(url)
    payload = json.dumps(
        {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
    ).encode()
    try:
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        chain_id = int(result["result"], 16)
        expected = _EXPECTED_CHAIN_IDS.get(network or "") if network else None
        if expected is not None and chain_id != expected:
            _warn(
                f"RPC reachable: {safe_url}  (chainId {chain_id}, expected {expected} for {network})",
                fix=f"Verify {network.upper()}_RPC_URL points at the right network",
            )
        else:
            _ok(f"RPC reachable: {safe_url}  (chainId {chain_id})")
    except Exception:
        _warn(f"RPC not reachable: {safe_url}", fix="Check your RPC URL and internet connection")
    return 0  # RPC connectivity is advisory — never a hard failure


def _check_ipfs_config() -> int:
    """Check that the resolved IPFSConfig has the required fields for its provider."""
    try:
        from dincli.services.ipfs import resolve_ipfs_config  # type: ignore[import]
        from dincli.cli.utils import IPFSConfig  # type: ignore[import]
        cfg: IPFSConfig = resolve_ipfs_config()
        provider = cfg.provider
        if provider == "env":
            missing = [
                v for v, f in (
                    ("IPFS_API_URL_ADD",      cfg.api_url_add),
                    ("IPFS_API_URL_RETRIEVE", cfg.api_url_retrieve),
                ) if not f
            ]
            if missing:
                _warn(
                    f"IPFS env provider: {', '.join(missing)} not set",
                    fix=(
                        "Set IPFS_API_URL_ADD / IPFS_API_URL_RETRIEVE in .env, "
                        "or run: dincli system configure-ipfs"
                    ),
                )
            else:
                _ok("IPFS config resolved (env provider)")
        elif provider == "filebase":
            if not cfg.api_key:
                _warn(
                    "IPFS filebase provider: ipfs_api_key not configured",
                    fix="dincli system configure-ipfs --provider filebase",
                )
            else:
                _ok("IPFS config resolved (filebase provider)")
        elif provider == "custom":
            if not cfg.service_path:
                _warn(
                    "IPFS custom provider: ipfs_service_path not configured",
                    fix="dincli system configure-ipfs --provider custom --service-path <path>",
                )
            else:
                _ok("IPFS config resolved (custom provider)")
        else:
            _warn(
                f"IPFS unknown provider '{provider}' — IPFS operations will fail",
                fix="dincli system configure-ipfs",
            )
    except ImportError:
        _warn("dincli not importable — skipping IPFS config check", fix="pip install -e .")
    except Exception as exc:
        _warn(f"IPFS config not resolved: {exc}", fix="dincli system configure-ipfs")
    return 0  # IPFS config is advisory


def _network_checks(network: str) -> int:
    failures = 0
    env_key = f"{network.upper()}_RPC_URL"

    # Resolve RPC URL the same way dincli does: os.environ → .env in cwd
    rpc_url = os.environ.get(env_key, "")
    if not rpc_url:
        env_file = Path.cwd() / ".env"
        if env_file.exists():
            try:
                rpc_url = _read_env_value(env_file, env_key)
            except Exception as exc:
                _warn(f".env read failed: {exc} — skipping .env lookup")

    if not rpc_url:
        _warn(
            f"No RPC URL found for {network} (checked os.environ and .env in cwd)",
            fix=f"Set {env_key}=<url> in .env in your working directory",
        )
    else:
        failures += _check_rpc(rpc_url, network=network)

    # IPFS check is independent of the env file — always run it
    failures += _check_ipfs_config()

    return failures


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
            "Also verify the configured RPC endpoint and IPFS config for NAME. "
            "Reads <NAME_UPPER>_RPC_URL from os.environ then .env in the current "
            "working directory (same lookup dincli uses). Requires a working dincli "
            "install for the IPFS check. Example values: local, sepolia_op_devnet."
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
