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
LOG_MAX_BYTES_DEFAULT = 10 * 1024 * 1024
LOG_BACKUP_COUNT_DEFAULT = 5


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


def resolve_max_ticks(flag: int | None = None) -> int | None:
    if flag is not None:
        return flag

    env_val = os.environ.get("DIN_DIND_MAX_TICKS")
    if env_val and env_val.strip():
        return int(env_val)

    config = load_config()
    config_val = config.get("dind_max_ticks")
    if config_val is not None:
        return int(config_val)

    return None


def resolve_log_max_bytes(flag: int | None = None) -> int:
    """DIN_DIND_LOG_MAX_BYTES, > 0. Unlike the other resolvers, a *set but
    empty or malformed* env var is a configuration mistake, not "unset" —
    it raises rather than silently falling through to the default."""
    if flag is not None:
        value = flag
    else:
        env_val = os.environ.get("DIN_DIND_LOG_MAX_BYTES")
        if env_val is not None:
            try:
                value = int(env_val.strip())
            except ValueError:
                raise ValueError(
                    f"DIN_DIND_LOG_MAX_BYTES must be an integer, got {env_val!r}"
                )
        else:
            config = load_config()
            config_val = config.get("dind_log_max_bytes")
            value = (
                int(config_val) if config_val is not None else LOG_MAX_BYTES_DEFAULT
            )

    if value <= 0:
        # maxBytes=0 disables rotation entirely, silently undoing BL-21
        # while looking configured — rejected, not merely discouraged.
        raise ValueError(f"DIN_DIND_LOG_MAX_BYTES must be > 0, got {value}")
    return value


def resolve_log_backup_count(flag: int | None = None) -> int:
    """DIN_DIND_LOG_BACKUP_COUNT, >= 1. Same empty/malformed-raises shape
    as resolve_log_max_bytes."""
    if flag is not None:
        value = flag
    else:
        env_val = os.environ.get("DIN_DIND_LOG_BACKUP_COUNT")
        if env_val is not None:
            try:
                value = int(env_val.strip())
            except ValueError:
                raise ValueError(
                    f"DIN_DIND_LOG_BACKUP_COUNT must be an integer, got {env_val!r}"
                )
        else:
            config = load_config()
            config_val = config.get("dind_log_backup_count")
            value = (
                int(config_val)
                if config_val is not None
                else LOG_BACKUP_COUNT_DEFAULT
            )

    if value < 1:
        # backupCount=0 makes the handler discard the old file instead of
        # keeping it — also a silent way to undo BL-21.
        raise ValueError(f"DIN_DIND_LOG_BACKUP_COUNT must be >= 1, got {value}")
    return value


def validate_health_port(port: int) -> None:
    # 0 (ephemeral) is valid: two daemons racing a fixed port would fail on
    # bind rather than on the lock, measuring the wrong thing. health.py
    # already records the actually-bound port into daemon_meta so ephemeral
    # ports resolve correctly for `status`.
    if not (0 <= port <= 65535):
        raise ValueError(f"Health port must be 0-65535, got {port}")
