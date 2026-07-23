import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from importlib.resources import files
from pathlib import Path
from typing import Optional

import typer
from eth_account import Account
from platformdirs import user_cache_dir, user_config_dir
from rich.console import Console
from web3 import Web3

_ACCOUNT_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PASSWORD_TTL_DEFAULT = 900
_PASSWORD_CACHE: dict[str, tuple[str, float]] = {}

# Sentinel so callers can inject an already-fetched DIN_WALLET_PASSWORD value
# (fetched once per unlock) while callers that omit it self-fetch as before.
_UNSET = object()

from dincli.cli.log import logger

console = Console()

from dincli.sdk.config import (
    CONFIG_DIR, CACHE_DIR, WORKER_CACHE_DIR, CONFIG_FILE,
    ALLOWED_NETWORKS, SUPPORTED_IPFS_PROVIDERS, LEGACY_IPFS_PROVIDER_ALIASES,
    FILEBASE_IPFS_ADD_URL, FILEBASE_IPFS_CAT_URL, FILEBASE_IPFS_PIN_URL,
    IPFSConfig, save_config, load_config, get_config, _clean_optional_string,
    normalize_ipfs_provider, resolve_network, resolve_ipfs_config,
    get_env_key, set_env_key, resolve_network_value,
)
from dincli.sdk.web3 import get_w3
from dincli.sdk.manifest import (
    load_din_info, save_din_info, load_cid_services,
    get_manifest, get_manifest_path, get_manifest_key,
    is_ethereum_address, download_manifest, get_model_info,
)
WALLET_FILE = CONFIG_DIR / "wallet.json"
WALLETS_DIR = CONFIG_DIR / "wallets"

LEGACY_WALLET_FILE = WALLET_FILE

MIN_STAKE = 10*10**18

def validate_account_name(name: str) -> str:
    name = name.strip()
    if not _ACCOUNT_NAME_RE.match(name):
        raise ValueError(
            f"Invalid account name '{name}'. Must be 1-64 chars of A-Z, a-z, 0-9, '-', '_'."
        )
    return name


def wallet_path_for_name(name: str) -> Path:
    resolved = validate_account_name(name)
    return WALLETS_DIR / f"wallet_{resolved}.json"


def resolve_wallet_path(name: str) -> tuple[Path, bool]:
    named_path = wallet_path_for_name(name)
    if named_path.exists():
        return named_path, True
    if name == "default" and LEGACY_WALLET_FILE.exists():
        return LEGACY_WALLET_FILE, True
    return named_path, False


def ensure_wallets_dir() -> None:
    WALLETS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(WALLETS_DIR, 0o700)
    except OSError:
        pass


def atomic_write_wallet(path: Path, data: dict) -> None:
    ensure_wallets_dir()
    tmp_path = path.with_suffix(".json.tmp")
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _extract_keystore(data: dict) -> dict:
    if isinstance(data, dict) and "keystore" in data:
        inner = data["keystore"]
        if isinstance(inner, dict) and "crypto" in inner:
            return inner
    if isinstance(data, dict) and "crypto" in data:
        return data
    raise ValueError("Data is not a recognised keystore (wrapper, bare, or demo).")


def _cleanup_stale_session() -> None:
    session_file = CONFIG_DIR / ".session"
    if session_file.exists():
        try:
            session_file.unlink()
            console.print("[dim]Removed stale .session cache from previous dincli version.[/dim]")
        except OSError:
            pass


def get_demo_private_key(account_index: int) -> str:
    """Load private key for Hardhat dev account by index."""
    # Path to accounts.json (relative to dincli package)
    accounts_file = files("dincli").joinpath("config", "accounts.json")
    
    if not accounts_file.exists():
        raise FileNotFoundError(
            f"Demo accounts file not found: {accounts_file}\n"
            "Run `npx hardhat export-accounts` to generate it."
        )
    
    with open(accounts_file) as f:
        data = json.load(f)
    
    accounts = data.get("hardhat", [])
    if account_index < 0 or account_index >= len(accounts):
        raise IndexError(
            f"Account index {account_index} out of range. "
            f"Available: 0–{len(accounts) - 1}"
        )
    
    return accounts[account_index]["private_key"]


def get_demo_account_index(address: str) -> int:
    """Find index of Hardhat dev account by address."""
    # Path to accounts.json (relative to dincli package)
    accounts_file = Path(__file__).parent / "config" / "accounts.json"

    if not accounts_file.exists():
        raise FileNotFoundError(
            f"Demo accounts file not found: {accounts_file}\n"
            "Run `npx hardhat export-accounts` to generate it."
        )

    with open(accounts_file) as f:
        data = json.load(f)

    accounts = data.get("hardhat", [])
    
    # Normalize input address
    target_address = address.lower()
    
    for idx, account in enumerate(accounts):
        if account["address"].lower() == target_address:
            return idx
            
    raise ValueError(f"Address {address} not found in demo accounts.")


def load_account(name: str = "default") -> Account:
    """Load a named wallet, falling back to legacy wallet.json for 'default'."""

    wallet_path, exists = resolve_wallet_path(name)
    if not exists:
        raise FileNotFoundError(
            f"No wallet found for name '{name}' at {wallet_path}. "
            f"Run `dincli system register-wallet --name {name}` first."
        )

    with open(wallet_path) as f:
        data = json.load(f)

    # Demo mode: plaintext private key
    if data.get("demo_mode") is True:
        private_key = data["private_key"]
        return Account.from_key(private_key)

    keystore_data = _extract_keystore(data)

    # Fetch DIN_WALLET_PASSWORD once and thread it through the password helpers so a
    # single unlock parses .env once rather than twice (get_env_key has no memoization).
    env_pass = get_env_key("DIN_WALLET_PASSWORD")

    password = _get_password(name, env_pass=env_pass)
    try:
        private_key = Account.decrypt(keystore_data, password)
        _cache_password_in_memory(name, password, env_pass=env_pass)
        _cleanup_stale_session()
        return Account.from_key(private_key)
    except ValueError:
        if _clear_memory_cache(name):
            console.print("[yellow]Cached password failed, prompting...[/yellow]")
            password = getpass("Enter wallet password: ")
            try:
                private_key = Account.decrypt(keystore_data, password)
                _cache_password_in_memory(name, password, env_pass=env_pass)
                _cleanup_stale_session()
                return Account.from_key(private_key)
            except ValueError:
                pass
        raise ValueError("Invalid password or corrupted keystore.")


def _get_password(name: str = "default", prompt: bool = True,
                  is_new_wallet: bool = False, env_pass=_UNSET) -> str:
    """
    Get password from:
    1. DIN_WALLET_PASSWORD env var
    2. In-memory cache (keyed by name)
    3. Interactive prompt
    is_new_wallet: when True, the in-memory cache is skipped entirely so a freshly
        created/overwritten wallet is never silently encrypted with a stale cached
        password. The DIN_WALLET_PASSWORD env var is still honored (deliberate
        automation path).
    env_pass: an already-fetched DIN_WALLET_PASSWORD value, to avoid re-parsing .env
        (see load_account). Omit (_UNSET) to self-fetch.
    """
    _cleanup_stale_session()

    # 1. Environment variable
    if env_pass is _UNSET:
        env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        return env_pass

    # 2. Session cache
    if not is_new_wallet:
        now = time.time()
        entry = _PASSWORD_CACHE.get(name)
        if entry is not None:
            cached_pw, expiry = entry
            if now < expiry:
                return cached_pw
            del _PASSWORD_CACHE[name]

    # 3. Prompt
    if prompt:
        return getpass("Enter wallet password: ")
    
    return ""


def _cache_password_in_memory(name: str, password: str, env_pass=_UNSET) -> None:
    if env_pass is _UNSET:
        env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        return
    ttl = int(os.environ.get("DIN_PASSWORD_TTL", _PASSWORD_TTL_DEFAULT))
    _PASSWORD_CACHE[name] = (password, time.time() + ttl)


def _clear_memory_cache(name: str | None = None) -> bool:
    if name is not None:
        return _PASSWORD_CACHE.pop(name, None) is not None
    _PASSWORD_CACHE.clear()
    return True


def list_accounts(active_name: str = "default") -> list[dict]:
    entries: list[dict] = []
    seen_names: set[str] = set()
    has_named_default = False

    if WALLETS_DIR.exists():
        for f in sorted(WALLETS_DIR.iterdir()):
            if not f.suffix == ".json":
                continue
            stem = f.stem
            if stem.startswith("wallet_"):
                name = stem[len("wallet_"):]
                if not name:
                    continue
                try:
                    with open(f) as fh:
                        data = json.load(fh)
                except (json.JSONDecodeError, OSError):
                    continue
                if name == "default":
                    has_named_default = True
                entries.append({
                    "name": name,
                    "address": data.get("address", "unknown"),
                    "source": data.get("source", "unknown"),
                    "active": name == active_name,
                })
                seen_names.add(name)

    if not has_named_default and "default" not in seen_names and LEGACY_WALLET_FILE.exists():
        try:
            with open(LEGACY_WALLET_FILE) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        label = "default (legacy)"
        entries.append({
            "name": label,
            "address": data.get("address", "unknown"),
            "source": data.get("demo_mode") and "demo" or "legacy",
            "active": active_name == "default",
        })

    return entries


def get_active_account_name(ctx_obj=None) -> str:
    if ctx_obj is not None and hasattr(ctx_obj, "wallet_name") and ctx_obj.wallet_name:
        return validate_account_name(ctx_obj.wallet_name)
    env_name = os.environ.get("DIN_WALLET_NAME", "").strip()
    if env_name:
        return validate_account_name(env_name)
    config_name = get_config("wallet_name", "")
    if config_name:
        return validate_account_name(config_name.strip())
    return "default"

# GI-state enums/converters moved to dincli.sdk.state (issue #20). Re-exported so
# existing `from dincli.cli.utils import GIstateToDes, ...` call sites keep
# working. New code: import from dincli.sdk.state.
from dincli.sdk.state import (  # noqa: F401,E402
    GIState, GIstateToDes, GIstateToStr, GIstatestrToIndex,
    stateDescription, states, GIstate_to_index,
)


def save_tasks(data: dict):
    path = CONFIG_DIR / "tasks.json"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    logger.debug(f"Tasks saved to {path}")

def load_tasks() -> dict:
    path = CONFIG_DIR / "tasks.json"
    if not path.exists():
        logger.warning(f"Tasks file not found: {path}")
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tasks: {e}")
        return {}


def cache_manifest(model_id: int, network: str, info: bool = False, update: bool = False, genesis_model_info: bool = False):
    from dincli.sdk.errors import ValidationError

    try:
        download_manifest(network, model_id, force=update)
    except ValidationError:
        console.print("[red]Error:[/red] Model ID must be non-negative")
        raise typer.Exit(1)

    if info:
        model_data = get_model_info(network, model_id, include_genesis=genesis_model_info)
        console.print("[bold green]Model Info :[/bold green]")
        console.print("Model Owner :", model_data["model_owner"])
        console.print("Is Open Source :", model_data["is_open_source"])
        console.print("Manifest CID :", model_data["manifest_cid"])
        console.print("Created At (Unix Timestamp) :", model_data["created_at"])
        console.print("Created At :", datetime.fromtimestamp(model_data["created_at"]).strftime("%Y-%m-%d %H:%M:%S %p"))
        console.print("Task Coordinator Address :", model_data["task_coordinator_address"])
        console.print("Task Auditor Address :", model_data["task_auditor_address"])
        if genesis_model_info:
            console.print("Genesis Model IPFS Hash :", model_data["genesis_model_ipfs_hash"])


def require_custom_manifest_service(manifest: dict, key: str) -> None:
    if manifest.get("type") == "custom":
        return

    manifest_type = manifest.get("type", "<missing>")
    console.print(
        f"[bold red]Type of service function '{key}' in manifest must be custom; got '{manifest_type}'.[/bold red]"
    )
    console.print(
        "[yellow]Built-in dincli service fallbacks are obsolete. "
        "Add a custom service function with type custom and its ipfs entry to the model manifest.[/yellow]"
    )   
    raise typer.Exit(1)


def resolve_task_coordinator_address(
    effective_network: str,
    address: Optional[str],
    console,
    verbose: bool = True,
    exit_on_failure: bool = True,
) -> Optional[str]:
    """Resolve a DINTaskCoordinator contract address.

    Resolution order:
    1. ``address`` argument (e.g. from ``--taskCoordinator`` CLI option).
    2. Environment variable ``{NETWORK_UPPER}_DINTaskCoordinator_Contract_Address``
       (read from the current directory's ``.env`` or the process environment).

    Args:
        effective_network: The active network name (e.g. ``"local"``).
        address: Explicitly provided address, or ``None`` to trigger env-var lookup.
        console: Rich ``Console`` instance used for status messages.
        verbose: When *True* (default), print where the address came from.
        exit_on_failure: When *True* (default), call ``raise typer.Exit(1)`` if
            the address cannot be resolved instead of returning ``None``.

    Returns:
        The resolved checksum-able address string, or ``None`` when
        ``exit_on_failure=False`` and the address could not be found.
    """
    env_key = effective_network.upper() + "_DINTaskCoordinator_Contract_Address"

    if address:
        if verbose:
            console.print(
                f"[bold green] ✓ Using DIN Task Coordinator Address: {address} "
                f"(from argument)[/bold green]"
            )
        return address

    # Try env / .env file
    address = get_env_key(env_key, verbose=False)
    if address:
        if verbose:
            console.print(
                f"[bold green] ✓ Using DIN Task Coordinator Address: {address} "
                f"(from {os.getcwd()}/.env → {env_key})[/bold green]"
            )
        return address

    # Not found
    console.print(
        f"[bold red]✗ Task Coordinator Address not found.[/bold red]\n"
        f"  Provide it via [cyan]--taskCoordinator <address>[/cyan], or set "
        f"[cyan]{env_key}[/cyan] in [cyan]{os.getcwd()}/.env[/cyan]."
    )
    if exit_on_failure:
        raise typer.Exit(1)
    return None


def build_and_send_tx(
    ctx,
    contract_function,
    action_msg: str,
    success_msg: str,
    error_msg: str,
    tx_params: Optional[dict] = None,
    exit_on_failure: bool = True,
    show_tx_hash: bool = True,
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    base_tx_params = ctx.obj.get_tx_params()
    if tx_params:
        base_tx_params.update(tx_params)

    try:
        base_tx_params["gas"] = int(w3.eth.estimate_gas(contract_function.build_transaction(base_tx_params)) * 1.1)
    except Exception as e:
        console.print(f"[bold red] X Transaction estimation failed: {e}[/bold red]")
        if exit_on_failure:
            raise typer.Exit(1)
        return None

    try:
        tx = contract_function.build_transaction(base_tx_params)
        signed_tx = account.sign_transaction(tx)
        console.print(f"[bold green]{action_msg}...[/bold green]")
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        if show_tx_hash:
            print_tx_info(tx_hash, effective_network)
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            console.print(f"[bold green] ✓ {success_msg}[/bold green]")
            return tx_receipt
        console.print(f"[bold red] X {error_msg}[/bold red]")
        if exit_on_failure:
            raise typer.Exit(1)
        return None
    except Exception as e:
        console.print(
            f"[bold red]✗ {error_msg}[/bold red]"
        )
        console.print(
            f"[bold red]Exception: {e}[/bold red]"
        )

        if exit_on_failure:
            raise typer.Exit(1)

        return None
    
def print_tx_info(tx_hash, network=None, print_url = True):
    #ensure tx_hash is hex string
    if isinstance(tx_hash, bytes):
        tx_hash_hex = tx_hash.hex()
    else:
        tx_hash_hex = tx_hash

    #print tx url
    console.print(f"[bold green]Transaction hash:[/bold green] {tx_hash_hex}")
    if print_url:
        din_info = load_din_info()
        console.print(f"[bold green]Transaction url:[/bold green] [cyan]{din_info[network]['explorer']}/tx/{tx_hash_hex}[/cyan]")
    
def _confirm_or_exit(question: str, instruction: str, console):
    answer = console.input(f"[bold yellow]{question} (y/n):[/bold yellow] ").strip().lower()

    if answer in ("y", "yes"):
        return

    if answer in ("n", "no"):
        console.print(f"[bold red]Error: {instruction}[/bold red]")
        raise typer.Exit(1)

    console.print("[bold red]Error: Please answer yes/y or no/n.[/bold red]")
    raise typer.Exit(1)