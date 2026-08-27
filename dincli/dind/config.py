"""Shared resolver for dind lifecycle commands.

Precedence: --flag > env > config.json > default.

Used by start, stop, and status so a lifecycle command can never target the
wrong daemon.
"""

import os
from pathlib import Path

from dincli.sdk.config import CACHE_DIR, load_config

HEALTH_HOST_DEFAULT = "127.0.0.1"
HEALTH_PORT_DEFAULT = 8787
DEFAULT_STATE_DIR = CACHE_DIR / "dind"


def resolve_state_dir(flag: str | None = None) -> Path:
    if flag:
        return Path(flag).expanduser().resolve()

    env_val = os.environ.get("DIN_DIND_STATE_DIR")
    if env_val:
        return Path(env_val).expanduser().resolve()

    config = load_config()
    config_val = config.get("dind_state_dir")
    if config_val:
        return Path(config_val).expanduser().resolve()

    return DEFAULT_STATE_DIR


def resolve_health_host(flag: str | None = None) -> str:
    if flag:
        return flag

    env_val = os.environ.get("DIN_DIND_HEALTH_HOST")
    if env_val:
        return env_val

    config = load_config()
    config_val = config.get("dind_health_host")
    if config_val:
        return config_val

    return HEALTH_HOST_DEFAULT


def resolve_health_port(flag: int | None = None) -> int:
    if flag is not None:
        return flag

    env_val = os.environ.get("DIN_DIND_HEALTH_PORT")
    if env_val and env_val.strip():
        return int(env_val)

    config = load_config()
    config_val = config.get("dind_health_port")
    if config_val is not None:
        return int(config_val)

    return HEALTH_PORT_DEFAULT


def validate_health_port(port: int) -> None:
    if not (1 <= port <= 65535):
        raise ValueError(f"Health port must be 1-65535, got {port}")
