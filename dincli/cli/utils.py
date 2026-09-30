import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from getpass import getpass
from importlib.resources import files
from pathlib import Path
from typing import NamedTuple, Optional

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
from dincli.sdk.errors import ChainIdMismatchError, DinError, SignerUnavailable, WalletError  # noqa: F401 — re-exported for CLI/test compatibility

MIN_STAKE = 10*10**18


def reraise_din_error_cause(error: DinError) -> None:
    """Compatibility adapter for `din-info`/`read-stake` (task_110926_14/15
    review finding 5, `Plans/task-14-15-remediation-plan.md` §7 fallback
    route).

    Pre-refactor, `get_deployed_din_stake_contract()` and direct contract
    calls let the underlying exception (contract construction, `getStake()`,
    file/JSON errors reading din_info.json) propagate unhandled: no extra
    printed line, and the original exception type reached the CLI's caller
    (`Plans/task-14-15-review-evidence/cli-before.json`). The SDK's
    operations layer (`dincli.sdk.operations.platform`) now wraps those into
    typed `DinError` subclasses — task 15's taxonomy requirement — chaining
    `raise ... from e`. That means `error.__cause__` IS the original
    exception object for every one of those cases, still holding its own
    traceback, so re-raising it here exactly reproduces the old observable
    behavior: nothing extra printed on the way out, original exception type
    seen by `CliRunner`/callers.

    Some `DinError`s the SDK raises with NO wrapped cause at all — chiefly a
    missing/malformed network entry or malformed root in din_info.json
    (`ConfigError` raised directly in `_load_din_info_entry()`/
    `get_stake_contract_address()`), and an invalid explicit `--address`
    (`ValidationError` in `get_stake()`). Pre-refactor, the network cases
    were a bare `KeyError`/`TypeError` from unchecked dict indexing — not an
    `Exception` instance the old code ever constructed or could hand back —
    and the address case did not exist as a validated path at all. There is
    no real prior exception object to re-raise for these, and fabricating
    one (e.g. a synthetic `KeyError`) would assert a traceback path that
    never executed, which is worse than an honestly-labeled behavior change.
    This is the one declared, accepted exception (see
    `test_din_info_missing_network_fails_clean_not_with_a_traceback` in
    `tests/test_cli_platform_operations_golden.py`): for those cases this
    function returns normally, and the caller keeps its own existing
    "print message, exit 1" handling exactly as before this adapter existed
    — deliberately not centralized here, since `din-info` and `read-stake`
    use slightly different message styles pre-dating this adapter and
    neither is being changed as part of this fix.
    """
    if error.__cause__ is not None:
        raise error.__cause__


class ReadResult(NamedTuple):
    value: int       # last successfully observed value; the baseline if every read raised
    settled: bool    # True iff a read showed value > baseline
    observed: bool   # False iff every read raised


def read_after_write(read_fn, *, baseline, attempts=5, delay=2.0) -> ReadResult:
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    last_value = baseline
    # Tracked across attempts, not inferred from the final one: a read that
    # succeeds and is then followed by a failing final attempt has still been
    # observed, and its value is more useful than the stale baseline.
    observed = False
    for i in range(attempts):
        try:
            value = read_fn()
        except Exception:
            if i < attempts - 1:
                time.sleep(delay)
            continue
        observed = True
        last_value = value
        if value > baseline:
            return ReadResult(value=value, settled=True, observed=True)
        if i < attempts - 1:
            time.sleep(delay)
    return ReadResult(value=last_value, settled=False, observed=observed)


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

    # Fetch DIN_WALLET_PASSWORD once and thread it through the password helpers so a
    # single unlock parses .env once rather than twice (get_env_key has no memoization).
    env_pass = get_env_key("DIN_WALLET_PASSWORD", verbose=False)

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
        env_pass = get_env_key("DIN_WALLET_PASSWORD", verbose=False)
    if env_pass:
        return env_pass

    # 1b. Yellow fallback line — only here, not at the call site
    console.print(
        "[yellow]DIN_WALLET_PASSWORD not found in environment; "
        "checking session cache or prompting...[/yellow]"
    )

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
    
def ensure_batch_seed_locked(
    ctx,
    task_coordinator_contract,
    gi: int,
    seed_getter: str,
    seed_block_getter: str,
    lock_fn: str,
    label: str,
    poll_interval: float = 2.0,
):
    """issue #156 H-2: autoCreateTier1AndTier2 / createAuditorsBatches both
    require their batch-assignment seed to already be locked -- an
    ungrindable value anchored to a future block at the preceding GIstate
    transition (closeLMsubmissionsEvaluation / closeLMsubmissions). Waits
    for that block to be mined, then locks the seed. The lock is
    permissionless: if someone else locks it first (or the seed block
    re-anchors while we're waiting, e.g. because we were offline past the
    256-block window), this just skips or re-polls rather than erroring.

    seed_getter / seed_block_getter / lock_fn are the DINTaskCoordinator
    function names for either seed pair -- aggSeed/aggSeedBlock/lockAggSeed
    (T1/T2 batches) or auditSeed/auditSeedBlock/lockAuditSeed (auditor
    batches). Same helper, different seed pair per caller.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    def _current_seed():
        return getattr(task_coordinator_contract.functions, seed_getter)(gi).call()

    if _current_seed() != b"\x00" * 32:
        console.print(f"[dim]{label} seed already locked for GI {gi}[/dim]")
        return

    seed_block = getattr(task_coordinator_contract.functions, seed_block_getter)(gi).call()
    console.print(
        f"[cyan]Waiting for block {seed_block} to lock the {label} seed "
        f"(current: {w3.eth.block_number})...[/cyan]"
    )
    while w3.eth.block_number <= seed_block:
        time.sleep(poll_interval)

    # A re-anchor (>256 blocks passed while we waited) or someone else's
    # lock may have happened -- re-check rather than assume.
    if _current_seed() != b"\x00" * 32:
        console.print(f"[dim]{label} seed was locked by someone else while waiting[/dim]")
        return

    # exit_on_failure=False: if someone else locks between our re-check
    # above and this tx landing, this call reverts with
    # TC_...SeedAlreadyLocked -- exiting on that would abort the whole
    # create command even though the seed is now locked and create would
    # succeed (PR #191 review, finding No. 5). Re-check below covers it.
    build_and_send_tx(
        ctx,
        getattr(task_coordinator_contract.functions, lock_fn)(gi),
        f"Locking {label} seed",
        f"{label.capitalize()} seed locked",
        f"Failed to lock {label} seed",
        exit_on_failure=False,
    )

    if _current_seed() != b"\x00" * 32:
        return

    # Seed is still unset. The only recoverable case is a re-anchor: the lock
    # call moved the seed block forward (>256 blocks elapsed since the last
    # anchor) instead of setting the seed -- recurse to wait for the new
    # block. Any other outcome (no gas funds, RPC down, a non-race revert)
    # would fail the same way again immediately, since the seed block is
    # already mined, so exit rather than retry (PR #191 review, No. 6).
    new_seed_block = getattr(task_coordinator_contract.functions, seed_block_getter)(gi).call()
    if new_seed_block != seed_block:
        ensure_batch_seed_locked(
            ctx, task_coordinator_contract, gi,
            seed_getter, seed_block_getter, lock_fn, label, poll_interval,
        )
        return

    console.print(
        f"[bold red]{label.capitalize()} seed for GI {gi} is still unlocked after "
        f"the lock attempt (seed block {seed_block} unchanged); not retrying.[/bold red]"
    )
    raise typer.Exit(1)


# Per batch-seed pair: (seed getter, seed-block getter, lock fn, label, the
# GIstate in which the seed is anchored but batches aren't created yet).
BATCH_SEED_PAIRS = {
    "agg": ("aggSeed", "aggSeedBlock", "lockAggSeed", "T1/T2 batch", "LMSevaluationClosed"),
    "audit": ("auditSeed", "auditSeedBlock", "lockAuditSeed", "auditor-batch", "LMSclosed"),
}


def lock_batch_seed_if_pending(ctx, task_coordinator_contract, gi: int, curr_gi: int, curr_GIstate: int, kind: str) -> bool:
    """Validator-side lock for a batch-assignment seed (BL-26).

    The seed's blockhash is public as soon as the seed block is mined, so if
    only the model owner ever locks it, they can decline to lock a draw they
    dislike and wait out the ~256-block window for a re-anchor (a fresh
    draw). Aggregators/auditors call this from their own commands so the
    first validator online after the seed block locks it instead.

    No-op (returns False) unless `gi` is the current GI and the GI is in the
    state where the seed is anchored but batches aren't created yet;
    otherwise waits for the seed block and locks (returns True).
    """
    seed_getter, seed_block_getter, lock_fn, label, pending_state = BATCH_SEED_PAIRS[kind]
    if gi != curr_gi or GIstateToStr(curr_GIstate) != pending_state:
        return False
    ensure_batch_seed_locked(
        ctx, task_coordinator_contract, gi,
        seed_getter, seed_block_getter, lock_fn, label,
    )
    return True


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