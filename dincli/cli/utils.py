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
from dincli.sdk.wallet import (  # moved to SDK — re-exported for CLI compatibility
    _ACCOUNT_NAME_RE,
    _PASSWORD_TTL_DEFAULT,
    _PASSWORD_CACHE,
    _UNSET,
    WALLET_FILE,
    WALLETS_DIR,
    LEGACY_WALLET_FILE,
    validate_account_name,
    wallet_path_for_name,
    resolve_wallet_path,
    ensure_wallets_dir,
    atomic_write_wallet,
    _extract_keystore,
    get_demo_private_key,
    get_demo_account_index,
    _cache_password_in_memory,
    _clear_memory_cache,
    _clean_stale_session_file,
    load_account_noninteractive,
    load_keystore,
    account_from_keystore,
    resolve_password,
    KeystoreSigner,
    PrivateKeySigner,
)
from dincli.sdk.errors import SignerUnavailable, WalletError

MIN_STAKE = 10*10**18


def _cleanup_stale_session() -> None:
    """CLI-side wrapper: removes stale session file, prints message.

    SDK's _clean_stale_session_file() does the I/O; the console message stays
    here — deliberate divergence from PR #31 review finding No. 1.
    """
    if _clean_stale_session_file():
        console.print("[dim]Removed stale .session cache from previous dincli version.[/dim]")


def load_account(name: str = "default") -> Account:
    """Load a named wallet, falling back to legacy wallet.json for 'default'.

    Fast path: non-interactive via env/TTL cache (load_account_noninteractive).
    Falls back to interactive prompt only when no non-interactive password is
    available (SignerUnavailable) or when the cached password is stale.
    """

    try:
        return load_account_noninteractive(name)
    except SignerUnavailable:
        pass
    except WalletError:
        # A missing/unreadable keystore is NOT a password problem — reporting it
        # as one tells a brand-new user their password is wrong. Re-raise it with
        # the legacy FileNotFoundError text before falling into the retry branch
        # (remediation R3).
        wallet_path, exists = resolve_wallet_path(name)
        if not exists:
            raise FileNotFoundError(
                f"No wallet found for name '{name}' at {wallet_path}. "
                f"Run `dincli system register-wallet --name {name}` first."
            )
        if not _clear_memory_cache(name):
            raise ValueError("Invalid password or corrupted keystore.")
        console.print("[yellow]Cached password failed, prompting...[/yellow]")

    wallet_path, exists = resolve_wallet_path(name)
    if not exists:
        raise FileNotFoundError(
            f"No wallet found for name '{name}' at {wallet_path}. "
            f"Run `dincli system register-wallet --name {name}` first."
        )

    with open(wallet_path) as f:
        data = json.load(f)

    if data.get("demo_mode") is True:
        private_key = data["private_key"]
        return Account.from_key(private_key)

    keystore_data = _extract_keystore(data)
    env_pass = get_env_key("DIN_WALLET_PASSWORD")

    password = getpass("Enter wallet password: ")
    try:
        private_key = Account.decrypt(keystore_data, password)
        _cache_password_in_memory(name, password, env_pass=env_pass)
        _cleanup_stale_session()
        return Account.from_key(private_key)
    except ValueError:
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
    from dincli.sdk.tx import send as sdk_send
    from dincli.sdk.tx import build_tx_params
    from dincli.sdk.errors import TransactionError, TX_ESTIMATION_FAILED, TX_REVERTED

    ctx_obj = ctx.obj
    effective_network, w3, account, console = ctx_obj.get_en_w3_account_console()
    session = ctx_obj.session

    def _on_event(name, payload):
        if name == "broadcasting":
            console.print(f"[bold green]{action_msg}...[/bold green]")
        elif name == "submitted":
            if show_tx_hash:
                print_tx_info(payload["tx_hash"], effective_network)
        # confirmed is handled in the return; reverted/timeout in the except

    try:
        info = sdk_send(session, contract_function, tx_params=tx_params,
                        on_event=_on_event)
    except TransactionError as err:
        if err.code == TX_ESTIMATION_FAILED:
            reason = err.__cause__ or err.message
            console.print(f"[bold red] X Transaction estimation failed: {reason}[/bold red]")
        elif err.code == TX_REVERTED:
            console.print(f"[bold red] X {error_msg}[/bold red]")
        else:
            reason = err.__cause__ or err.message
            console.print(f"[bold red]✗ {error_msg}[/bold red]")
            console.print(f"[bold red]Exception: {reason}[/bold red]")
        if exit_on_failure:
            raise typer.Exit(1) from err
        return None

    console.print(f"[bold green] ✓ {success_msg}[/bold green]")
    return info._raw  # unchanged return contract (D5)
    
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