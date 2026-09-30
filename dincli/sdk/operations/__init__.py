"""Curated public surface for ``dincli.sdk.operations`` (task_110926_15, BL-9).

Each operation pairs a typed, ``to_envelope()``-serializable dataclass with a
function taking a ``DinSession`` and returning that dataclass. Operations
raise ``DinError`` subclasses only — no stdlib or web3 exceptions escape —
so both the daemon's job layer and the CLI can key retries/exit codes off a
stable ``error.code``.

The proposal's §8 layout groups operations into seven role-scoped modules.
``platform.py`` reads platform-level state every role needs (contract
addresses, validator stake) and isn't role-scoped, so it's an *addition* to
that layout rather than one of its listed entries.
"""
from dincli.sdk.operations.platform import (
    PlatformAddresses,
    StakeInfo,
    get_platform_addresses,
    get_stake,
    get_stake_contract_address,
)

__all__ = [
    "PlatformAddresses",
    "StakeInfo",
    "get_platform_addresses",
    "get_stake",
    "get_stake_contract_address",
]
