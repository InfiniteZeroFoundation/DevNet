import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from platformdirs import user_cache_dir, user_config_dir

logger = logging.getLogger("dincli")

CONFIG_DIR = Path(user_config_dir("dincli"))
CACHE_DIR = Path(user_cache_dir("dincli"))

# Sibling cache used for docker-only artifacts (e.g. pip-installed client
# packages). Kept separate from CACHE_DIR so containers never need read/write
# access to the manifest/service/wallet cache that dincli itself manages.
WORKER_CACHE_DIR = Path(user_cache_dir("dincli-worker"))

CONFIG_FILE = CONFIG_DIR / "config.json"

ALLOWED_NETWORKS = ["local", "sepolia_devnet", "sepolia_op_devnet", "mainnet"]  # "sepolia_testnet"
SUPPORTED_IPFS_PROVIDERS = ("env", "filebase", "custom")

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
    config = load_config()
    configured_provider = config.get("ipfs_provider")
    provider = normalize_ipfs_provider(configured_provider) if configured_provider else normalize_ipfs_provider(get_env_key("IPFS_PROVIDER", verbose=False))
    raw_service_path = _clean_optional_string(config.get("ipfs_service_path"))

    api_key = _clean_optional_string(config.get(f"ipfs_api_key_{provider}"))
    if not api_key and provider == "filebase":
        api_key = _clean_optional_string(config.get("ipfs_api_key"))

    return IPFSConfig(
        provider=provider,
        api_url_add=_clean_optional_string(get_env_key("IPFS_API_URL_ADD", verbose=False)),
        api_url_retrieve=_clean_optional_string(get_env_key("IPFS_API_URL_RETRIEVE", verbose=False)),
        api_key=api_key,
        api_secret=_clean_optional_string(config.get("ipfs_api_secret")),
        service_path=Path(raw_service_path).expanduser().resolve() if raw_service_path else None,
    )


def get_env_key(key: str, default: Optional[str] = None, verbose: bool = True) -> Optional[str]:
    # 1. Already in environment? (e.g., from shell or parent process)
    if key in os.environ:
        return os.environ[key]

    # 2. Load from .env in current directory (if available)
    env_path = Path(os.getcwd()) / ".env"
    if HAS_DOTENV and env_path.exists():
        values = dotenv_values(dotenv_path=env_path)
        if key not in values and default is None:
            if verbose:
                logger.warning(f" ❌ {key} not found in {os.getcwd()}/.env file")
        return values.get(key, default)

    if not HAS_DOTENV and verbose:
        logger.warning("Warning: python-dotenv not installed. Cannot save to .env")

    return default


def set_env_key(key: str, value: str):
    if not HAS_DOTENV:
        logger.warning("Warning: python-dotenv not installed. Cannot save to .env")
        return

    env_path = Path(os.getcwd()) / ".env"

    try:
        from dotenv import set_key

        if not env_path.exists():
            env_path.touch()
        set_key(env_path, key, value)
    except Exception as e:
        logger.warning(f"Error saving to .env: {e}")


def resolve_network_value(
    network: str,
    key: str,
    default: Optional[str] = None
) -> str:
    if not network or not key:
        raise ValueError("network and key must be non-empty strings")

    env_key_suffix = key.upper()
    env_var_name = f"{network.upper()}_{env_key_suffix}"

    resolved_env_var_name = get_env_key(env_var_name)
    if resolved_env_var_name:
        return resolved_env_var_name

    config = load_config()
    user_networks = config.get("networks", {})
    if network in user_networks and key in user_networks[network]:
        return user_networks[network][key]

    if default is not None:
        return default

    raise KeyError(
        f"Could not resolve '{key}' for network '{network}'.\n"
        f"→ Checked .env for '{env_var_name}'\n"
        f"→ Checked config.json → networks.{network}.{key}\n"
        f"→ No fallback provided."
    )
