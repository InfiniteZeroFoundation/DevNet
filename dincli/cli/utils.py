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

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.log import logger
from dincli.services.cid_utils import get_cid_from_bytes32

console = Console()

CONFIG_DIR = Path(user_config_dir("dincli"))
CACHE_DIR = Path(user_cache_dir("dincli"))

# Sibling cache used for docker-only artifacts (e.g. pip-installed client
# packages). Kept separate from CACHE_DIR so containers never need read/write
# access to the manifest/service/wallet cache that dincli itself manages.
WORKER_CACHE_DIR = Path(user_cache_dir("dincli-worker"))

CONFIG_FILE = CONFIG_DIR / "config.json"
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


ALLOWED_NETWORKS = ["local", "sepolia_devnet", "sepolia_op_devnet", "mainnet"] # "sepolia_testnet"
SUPPORTED_IPFS_PROVIDERS = ("env", "filebase", "lighthouse", "custom")

LEGACY_IPFS_PROVIDER_ALIASES = {
    "": "env",
    "default": "env",
    "env": "env",
    "ipfs node": "env",
    "ipfs-node": "env",
    "node": "env",
}

FILEBASE_IPFS_ADD_URL = "https://rpc.filebase.io/api/v0/add"
FILEBASE_IPFS_CAT_URL = "https://rpc.filebase.io/api/v0/cat"
FILEBASE_IPFS_PIN_URL = "https://rpc.filebase.io/api/v0/pin/add"


# Optional: only import dotenv if needed
try:
    from dotenv import dotenv_values
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


@dataclass(frozen=True)
class IPFSConfig:
    provider: str = "env"
    api_url_add: Optional[str] = None
    api_url_retrieve: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    service_path: Optional[Path] = None


def save_config(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)
    logger.debug(f"Config saved to {CONFIG_FILE}")


def load_config():
    if CONFIG_FILE.exists():
        logger.debug(f"Loading config from {CONFIG_FILE}")
        with open(CONFIG_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Error decoding config file at {CONFIG_FILE}. Returning empty config.")
                return {}
    else:
        logger.warning(f"No config found at {CONFIG_FILE}")
    return {}


def get_config(key, default=None):
    config = load_config()
    return config.get(key, default)


def _clean_optional_string(value: Optional[str]) -> Optional[str]:
    if not isinstance(value, str):
        return None

    stripped = value.strip()
    return stripped or None


def normalize_ipfs_provider(provider: Optional[str]) -> str:
    if provider is None:
        return "env"

    normalized = provider.strip().lower()
    return LEGACY_IPFS_PROVIDER_ALIASES.get(normalized, normalized)
    
def resolve_network(cli_network: str | None = None, default: str = "local") -> str:
    """
    Resolve network: use CLI arg if provided, else config, else default.
    """
    # 1. CLI takes highest precedence
    if cli_network is not None:
        if cli_network not in ALLOWED_NETWORKS:
            raise ValueError(f"Invalid network: {cli_network}. Must be one of: {ALLOWED_NETWORKS}")
        return cli_network

    # 3. Check global config
    from_config = get_config("network")
    if from_config and isinstance(from_config, str) and from_config.strip():
        return from_config.strip()

    # 4. Fallback
    return default

def resolve_ipfs_config():
    """
    Resolve the effective IPFS runtime configuration.
    """
    config = load_config()
    configured_provider = config.get("ipfs_provider")
    provider = normalize_ipfs_provider(configured_provider) if configured_provider else normalize_ipfs_provider(get_env_key("IPFS_PROVIDER", verbose=False))
    raw_service_path = _clean_optional_string(config.get("ipfs_service_path"))

    api_key = _clean_optional_string(config.get(f"ipfs_api_key_{provider}"))
    if not api_key and provider == "filebase":
        api_key = _clean_optional_string(config.get("ipfs_api_key"))
    if not api_key and provider == "lighthouse":
        api_key = _clean_optional_string(get_env_key("LIGHTHOUSE_API_KEY", verbose=False))

    return IPFSConfig(
        provider=provider,
        api_url_add=_clean_optional_string(get_env_key("IPFS_API_URL_ADD", verbose=False)),
        api_url_retrieve=_clean_optional_string(get_env_key("IPFS_API_URL_RETRIEVE", verbose=False)),
        api_key=api_key,
        api_secret=_clean_optional_string(config.get("ipfs_api_secret")),
        service_path=Path(raw_service_path).expanduser().resolve() if raw_service_path else None,
    )


def get_env_key(key: str, default: Optional[str] = None, verbose: bool = True) -> Optional[str]:
    """
    Get a key from:
    1. Current environment (e.g., SEPOLIA_RPC_URL)
    2. ./ .env file
    3. Default fallback
    """
    # 1. Already in environment? (e.g., from shell or parent process)
    if key in os.environ:
        return os.environ[key]

    # 2. Load from .env in current directory (if available)
    env_path = Path(os.getcwd()) / ".env"
    if HAS_DOTENV and env_path.exists():
        # Load .env into a dict (doesn't pollute os.environ)
        values = dotenv_values(dotenv_path=env_path)
        if key not in values and default is None:
            if verbose:
                console.print(f"[bold red] ❌ {key} not found in {os.getcwd()}/.env file[/bold red]")
        return values.get(key, default)

    if not HAS_DOTENV and verbose:  
        console.print("[yellow]Warning: python-dotenv not installed. Cannot save to .env[/yellow]")

    return default


def set_env_key(key: str, value: str):
    """
    Set a key in the .env file.
    """
    if not HAS_DOTENV:
        console.print("[yellow]Warning: python-dotenv not installed. Cannot save to .env[/yellow]")
        return

    env_path = Path(os.getcwd()) / ".env"
    
    try:
        from dotenv import set_key

        # Create file if it doesn't exist
        if not env_path.exists():
            env_path.touch()
        set_key(env_path, key, value)
    except Exception as e:
        console.print(f"[red]Error saving to .env: {e}[/red]")


def resolve_network_value(
    network: str,
    key: str,
    default: Optional[str] = None
) -> str:
    """
    Resolve a network-specific config value with priority:
    1. .env in current directory (e.g., SEPOLIA_RPC_URL)
    2. Global user config (~/.din/config.json → config["networks"][network][key])
    3. Fallback default (if provided)

    Example:
        resolve_network_value("sepolia", "rpc_url")
        → checks SEPOLIA_RPC_URL in .env, then config
    """
    if not network or not key:
        raise ValueError("network and key must be non-empty strings")
    
    # Normalize key to uppercase for .env (e.g., "rpc_url" → "RPC_URL")
    env_key_suffix = key.upper()
    env_var_name = f"{network.upper()}_{env_key_suffix}"
    
    
    # ✅ 1. Check .env in current working directory
    resolved_env_var_name = get_env_key(env_var_name)
    if resolved_env_var_name:
        return resolved_env_var_name
    
    
    # ✅ 2. Check global user config: ~/.din/config.json
    config = load_config()
    user_networks = config.get("networks", {})
    if network in user_networks and key in user_networks[network]:
        return user_networks[network][key]
    
    # ✅ 3. Fallback to provided default or raise error
    if default is not None:
        return default

    raise KeyError(
        f"Could not resolve '{key}' for network '{network}'.\n"
        f"→ Checked .env for '{env_var_name}'\n"
        f"→ Checked config.json → networks.{network}.{key}\n"
        f"→ No fallback provided."
    )
    
        
def get_w3(effective_network): 
    rpc_url = resolve_network_value(effective_network,"rpc_url") 
    try:  
        
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        if not w3.is_connected():
            raise ConnectionError(f"Could not connect to Ethereum node at {rpc_url}")
        return w3
    except Exception as e:
        raise ConnectionError(f"Could not connect to Ethereum node for network '{effective_network}': {e}") from e
    

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
            f"Run `dincli system connect-wallet --name {name}` first."
        )

    with open(wallet_path) as f:
        data = json.load(f)

    if data.get("demo_mode") is True:
        private_key = data["private_key"]
        return Account.from_key(private_key)

    keystore_data = _extract_keystore(data)

    password = _get_password(name)
    try:
        private_key = Account.decrypt(keystore_data, password)
        _cache_password_in_memory(name, password)
        _cleanup_stale_session()
        return Account.from_key(private_key)
    except ValueError:
        if _clear_memory_cache(name):
            console.print("[yellow]Cached password failed, prompting...[/yellow]")
            password = getpass("Enter wallet password: ")
            try:
                private_key = Account.decrypt(keystore_data, password)
                _cache_password_in_memory(name, password)
                _cleanup_stale_session()
                return Account.from_key(private_key)
            except ValueError:
                pass
        raise ValueError("Invalid password or corrupted keystore.")


def _get_password(name: str = "default", prompt: bool = True) -> str:
    """
    Get password from:
    1. DIN_WALLET_PASSWORD env var
    2. In-memory cache (keyed by name)
    3. Interactive prompt
    """
    _cleanup_stale_session()

    env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        return env_pass

    now = time.time()
    entry = _PASSWORD_CACHE.get(name)
    if entry is not None:
        cached_pw, expiry = entry
        if now < expiry:
            return cached_pw
        del _PASSWORD_CACHE[name]

    if prompt:
        return getpass("Enter wallet password: ")
    return ""


def _cache_password_in_memory(name: str, password: str) -> None:
    if get_env_key("DIN_WALLET_PASSWORD"):
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
    
    
def load_din_info() -> dict:
    path = files("dincli").joinpath("config", "din_info.json")
    with open(path) as f:
        return json.load(f)

def load_cid_services() -> dict:
    path = files("dincli").joinpath("config", "cid_services.json")
    with open(path) as f:
        return json.load(f)

def save_din_info(data: dict):
    path = files("dincli").joinpath("config", "din_info.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

stateDescription = [
        "Awaiting DINTaskAuditor to be set",
        "Awaiting DINTaskCoordinator to be set as slasher",
        "Awaiting DINTaskAuditor to be set as slasher",
        "Awaiting Genesis Model",
        "Genesis Model Created",
        "GI started",
        "DIN aggregators registration started",
        "DIN aggregators registration closed",
        "DIN auditors registration started",
        "DIN auditors registration closed",
        "LM submissions started",
        "LM submissions closed",
        "Auditors batches created",
        "LM submissions evaluation started",
        "LM submissions evaluation closed",
        "T1nT2B created",
        "T1B aggregation started",
        "T1B aggregation done",
        "T2B aggregation started",
        "T2B aggregation done",
        "Auditors slashed",
        "Validators slashed",
        "GI ended"
    ]

states = [
        "AwaitingDINTaskAuditorToBeSet",
        "AwaitingDINTaskCoordinatorAsSlasher",
        "AwaitingDINTaskAuditorAsSlasher",
        "AwaitingGenesisModel",
        "GenesisModelCreated",
        "GIstarted",
        "DINaggregatorsRegistrationStarted",
        "DINaggregatorsRegistrationClosed",
        "DINauditorsRegistrationStarted",
        "DINauditorsRegistrationClosed",
        "LMSstarted",
        "LMSclosed",
        "AuditorsBatchesCreated",
        "LMSevaluationStarted",
        "LMSevaluationClosed",
        "T1nT2Bcreated",
        "T1AggregationStarted",
        "T1AggregationDone",
        "T2AggregationStarted",
        "T2AggregationDone",
        "AuditorsSlashed",
        "AggregatorsSlashed",
        "GIended"
    ]
    

GIstate_to_index = {state: idx for idx, state in enumerate(states)}  


def GIstateToDes(GIstate: int) -> str:

    if 0 <= GIstate < len(stateDescription):
        return stateDescription[GIstate]
    else:
        return f"UnknownState({GIstate})"
    

def GIstateToStr(GIstate: int) -> str:
    """
    Convert GIstate integer (from Solidity enum) to its string representation.
    Safe against errors by returning 'Unknown' for invalid states.
    """
    
    
    if 0 <= GIstate < len(states):
        return states[GIstate]
    else:
        return f"UnknownState({GIstate})"
    
def GIstatestrToIndex(GIstateStr: str) -> int:    
    return GIstate_to_index[GIstateStr]


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
    if int(model_id) < 0:
        console.print("[red]Error:[/red] Model ID must be non-negative")
        raise typer.Exit(1)

    manifest_dir = CACHE_DIR / network / f"model_{model_id}"
    os.makedirs(manifest_dir, exist_ok=True)
    manifest_path = manifest_dir / "manifest.json"
    cid_path = manifest_dir / "manifest.json.cid"
    
    if not manifest_path.exists() or info or update:

        din_info = load_din_info()
        din_registry_address = din_info[network]["registry"]
        din_registry_abi = files("dincli").joinpath("abis", "DINModelRegistry.json")

        din_registry_contract = get_contract_instance(din_registry_abi, network, din_registry_address)
     

        model_info = din_registry_contract.functions.getModel(model_id).call()

        if info:
            console.print("[bold green]Model Info :[/bold green]")
            console.print("Model Owner :", model_info[0])
            console.print("Is Open Source :", model_info[1])
            # console.print("Manifest CID (Bytes32) :", model_info[2])
            # console.print("Manifest CID (Bytes32) hex:", model_info[2].hex())
            console.print("Manifest CID :", get_cid_from_bytes32(model_info[2].hex()))
            console.print("Created At (Unix Timestamp) :", model_info[3])
            console.print("Created At :", datetime.fromtimestamp(model_info[3]).strftime("%Y-%m-%d %H:%M:%S %p"))  # am/pm
            console.print("Task Coordinator Address :", model_info[4])
            console.print("Task Auditor Address :", model_info[5])
            if genesis_model_info:
                din_task_coordinator_abi = files("dincli").joinpath("abis", "DINTaskCoordinator.json")
                taskCoordinator_contract = get_contract_instance(din_task_coordinator_abi, network, model_info[4])
                genesis_model_ipfs_hash_raw = taskCoordinator_contract.functions.genesisModelIpfsHash().call()
                genesis_model_ipfs_hash = get_cid_from_bytes32(genesis_model_ipfs_hash_raw.hex())
                console.print("Genesis Model IPFS Hash :", genesis_model_ipfs_hash)

        if  update or not manifest_path.exists():

            from dincli.services.ipfs import retrieve_from_ipfs
            retrieve_from_ipfs(get_cid_from_bytes32(model_info[2].hex()), manifest_path)
            
            # Save CID sidecar
            with open(cid_path, "w") as f:
                f.write(get_cid_from_bytes32(model_info[2].hex()))


def get_manifest_path(network: str, model_id: int = None, task_coordinator_address: str = None) -> Path:
    # Ensure exactly one identifier is provided
    has_model_id = model_id is not None
    has_coordinator_address = task_coordinator_address is not None

    if not has_model_id and not has_coordinator_address:
        raise ValueError("Either model_id or task_coordinator_address must be provided")

    if has_model_id and has_coordinator_address:
        raise ValueError("Only one of model_id or task_coordinator_address can be provided")

    if has_model_id:
        return CACHE_DIR / network / f"model_{model_id}" / "manifest.json"

    return Path(os.getcwd()) / "tasks" / network.lower() / task_coordinator_address / "manifest.json"


def get_manifest(network: str, model_id: int = None, task_coordinator_address: str = None) -> dict:
    manifest_path = get_manifest_path(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )

    if model_id is not None:
        cid_path = manifest_path.with_suffix(".json.cid")

        # Check freshness against the on-chain manifest CID.
        needs_update = True

        try:
            din_info = load_din_info()
            din_registry_address = din_info[network]["registry"]
            din_registry_abi = files("dincli").joinpath("abis", "DINModelRegistry.json")
            din_registry_contract = get_contract_instance(din_registry_abi, network, din_registry_address)
            model_info = din_registry_contract.functions.getModel(int(model_id)).call()
            on_chain_cid = get_cid_from_bytes32(model_info[2].hex())

            if manifest_path.exists() and cid_path.exists():
                with open(cid_path, "r") as f:
                    local_cid = f.read().strip()
                if local_cid == on_chain_cid:
                    needs_update = False
        except Exception as e:
            console.print(f"[yellow]Warning: Could not verify manifest freshness: {e}[/yellow]")
            needs_update = True

        if needs_update:
            cache_manifest(int(model_id), network, update=True)
    elif not manifest_path.exists():
        raise FileNotFoundError(
            f"Manifest not found for task coordinator {task_coordinator_address} at {manifest_path}"
        )

    with open(manifest_path, "r") as f:
        return json.load(f)


def get_manifest_key(network: str, key: str, model_id: int = None, task_coordinator_address: str = None):
    manifest = get_manifest(
        network,
        model_id=model_id,
        task_coordinator_address=task_coordinator_address,
    )
    return manifest[key]


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


def is_ethereum_address(s: str) -> bool:
    """Check if string looks like a valid Ethereum address (case-insensitive, 42 chars, starts with 0x)."""
    return bool(re.fullmatch(r'0x[a-fA-F0-9]{40}', s))


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