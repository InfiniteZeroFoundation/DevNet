import json
import os
import re
import time
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

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.log import logger
from dincli.services.cid_utils import get_cid_from_bytes32

console = Console()

CONFIG_DIR = Path(user_config_dir("dincli"))
CACHE_DIR = Path(user_cache_dir("dincli"))

CONFIG_FILE = CONFIG_DIR / "config.json"
WALLET_FILE = CONFIG_DIR / "wallet.json"

MIN_STAKE = 10*10**18 

ALLOWED_NETWORKS = ["local", "sepolia_devnet", "sepolia_op_devnet", "mainnet"] # "sepolia_testnet"


# Optional: only import dotenv if needed
try:
    from dotenv import dotenv_values
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False


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
    Resolve ipfs config
    """
    default = "local"

    ipfs_api_url_add = "None"
    ipfs_api_url_retrieve = "None"

    # 2. Check .env (ignore empty strings)
    from_env = get_env_key("ipfs_api_url_add".upper())
    if from_env and isinstance(from_env, str) and from_env.strip():
        ipfs_api_url_add = from_env.strip()

    from_env = get_env_key("ipfs_api_url_retrieve".upper())
    if from_env and isinstance(from_env, str) and from_env.strip():
        ipfs_api_url_retrieve = from_env.strip()

    return ipfs_api_url_add, ipfs_api_url_retrieve


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
    try:  
        rpc_url = resolve_network_value(effective_network,"rpc_url")
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


def load_account() -> Account:
    """Load wallet from ~/.din/wallet.json (handles demo + encrypted modes)."""


    if not WALLET_FILE.exists():
        raise FileNotFoundError(f"No wallet found at {WALLET_FILE}. Run `dincli system connect-wallet` first.")

    with open(WALLET_FILE) as f:
        data = json.load(f)

    # Demo mode: plaintext private key
    if data.get("demo_mode") is True:
        private_key = data["private_key"]
        return Account.from_key(private_key)

    # Encrypted mode: check for cached password or env var
    password = _get_password()
    try:
        private_key = Account.decrypt(data, password)
        # Verify strict permissions and save to cache if successful and not from env
        _cache_password_if_needed(password)
        return Account.from_key(private_key)
    except ValueError:
        # If decryption fails, clear cache and retry once if it was a cached/env password
        if _clear_session_cache():
             print("[yellow]Cached password failed, prompting...[/yellow]")
             password = getpass("Enter wallet password: ")
             try:
                private_key = Account.decrypt(data, password)
                _cache_password_if_needed(password)
                return Account.from_key(private_key)
             except ValueError:
                 pass
        raise ValueError("Invalid password or corrupted keystore.")

def _get_password(prompt: bool = True) -> str:
    """
    Get password from:
    1. DIN_WALLET_PASSWORD env var
    2. Session cache file (~/.dincli/.session)
    3. Interactive prompt
    """


    # 1. Environment variable
    env_pass = get_env_key("DIN_WALLET_PASSWORD")
    if env_pass:
        console.print(f"[green]Got Wallet Password DIN_WALLET_PASSWORD from {os.getcwd()}/.env[/green]")
        return env_pass

    # 2. Session cache
    session_file = CONFIG_DIR / ".session"
    if session_file.exists():
        try:
            # Check file permissions (must be 600)
            st = session_file.stat()
            if st.st_mode & 0o777 != 0o600:
                print("[yellow]Session file permissions unsafe (should be 600). Ignoring.[/yellow]")
            # Check timeout (default 15 mins)
            elif (time.time() - st.st_mtime) < (15 * 60):
                with open(session_file, "r") as f:
                    console.print(f"[green]Got Wallet Password from session cache {session_file}[/green]")
                    return f.read().strip()
        except Exception:
            pass # ignore errors, fall back to prompt

    # 3. Prompt
    if prompt:
        return getpass("Enter wallet password: ")
    else:
        return ""

def _cache_password_if_needed(password: str):
    """Save password to session cache if not from env var."""
    if get_env_key("DIN_WALLET_PASSWORD"):
        return

    session_file = CONFIG_DIR / ".session"
    try:
        # Create with strict permissions
        # Remove if exists to ensure permissions are reset
        if session_file.exists():
            session_file.unlink()
        
        fd = os.open(session_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(password)
            console.print("[green]Password cached successfully.[/green]")
    except Exception as e:
        console.print(f"[yellow]Failed to cache password: {e}[/yellow]")

def _clear_session_cache() -> bool:
    """Remove session cache file. Returns True if a file was removed."""
    session_file = CONFIG_DIR / ".session"
    if session_file.exists():
        session_file.unlink()
        return True
    return False 
    
    
def load_din_info() -> dict:
    path = files("dincli").joinpath("config", "din_info.json")
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
            console.print("Manifest CID (Bytes32) :", model_info[2])
            console.print("Manifest CID (Bytes32) hex:", model_info[2].hex())
            console.print("Manifest CID (Decoded) :", get_cid_from_bytes32(model_info[2].hex()))
            console.print("Created At :", model_info[3])
            console.print("Created At Human Readable :", datetime.fromtimestamp(model_info[3]).strftime("%Y-%m-%d %H:%M:%S %p"))  # am/pm
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
        

def get_manifest_key( network: str, key: str, model_id: int = None, task_coordinator_address: str = None):
    # Ensure exactly one identifier is provided
    has_model_id = model_id is not None
    has_coordinator_address = task_coordinator_address is not None

    if not has_model_id and not has_coordinator_address:
        raise ValueError("Either model_id or task_coordinator_address must be provided")

    if has_model_id and has_coordinator_address:
        raise ValueError("Only one of model_id or task_coordinator_address can be provided")

    if has_model_id:
        manifest_dir = CACHE_DIR / network / f"model_{model_id}"
        manifest_path = manifest_dir / "manifest.json"
        cid_path = manifest_dir / "manifest.json.cid"
        
        # Check freshness
        needs_update = True
        
        # 1. Fetch on-chain CID
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
            pass

        if needs_update:
            cache_manifest(int(model_id), network, update=True)
    
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        
        return manifest[key]
    
    if has_coordinator_address:

        manifest_path = Path(os.getcwd()) / "tasks" / network.lower() / task_coordinator_address / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest not found for task coordinator {task_coordinator_address} at {manifest_path}")
        
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
        return manifest[key]
    

def is_ethereum_address(s: str) -> bool:
    """Check if string looks like a valid Ethereum address (case-insensitive, 42 chars, starts with 0x)."""
    return bool(re.fullmatch(r'0x[a-fA-F0-9]{40}', s))






    
    
