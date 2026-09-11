"""Platform-level read operations: configured addresses and validator stake.

Pure module: no imports from ``dincli.cli``, ``typer``, or ``rich``, same rule
as the rest of ``dincli.sdk``. Both operations are read-only and take a
``DinSession`` rather than resolving their own network/web3, so a daemon
holding one session for its whole run never builds a second one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files

from web3 import Web3

from dincli.sdk.contracts import get_contract_instance
from dincli.sdk.errors import ConfigError, ContractError, DinError, ValidationError
from dincli.sdk.manifest import load_din_info
from dincli.sdk.session import DinSession

_ADDRESS_KEYS = ("coordinator", "token", "stake", "representative", "registry")
_STAKE_ABI_NAME = "DinValidatorStake.json"


@dataclass
class PlatformAddresses:
    """The platform contract addresses configured for one network.

    Fields carry NO ``{"json": "address"}`` encoder metadata, deliberately.
    The shipped ``dincli/config/din_info.json`` sets every ``mainnet`` address
    to the literal placeholder ``"0x..."``, and
    ``Web3.to_checksum_address("0x...")`` raises ``ValueError`` — the encoder
    applies ``"address"`` metadata unconditionally to any non-``None`` value,
    so tagging these fields would make ``to_envelope()`` crash on config that
    ships in this repo today. Addresses are therefore emitted as-configured;
    ``StakeInfo`` below keeps the ``"address"`` metadata because its addresses
    come from the session and the chain and are always well-formed.

    ``present`` records which of the five keys existed in ``din_info.json`` at
    all, so the CLI can distinguish "key absent" (renders "N/A") from "key
    present and null" (renders "None") the way ``data.get(key, 'N/A')`` does
    today. It is tagged ``{"json": "omit"}`` and never reaches the envelope.
    """

    network: str
    coordinator: str | None = None
    token: str | None = None
    stake: str | None = None
    representative: str | None = None
    registry: str | None = None
    present: frozenset[str] = field(default_factory=frozenset, metadata={"json": "omit"})


@dataclass
class StakeInfo:
    """One address's staked DIN balance, plus the contract it was read from."""

    network: str
    address: str = field(metadata={"json": "address"})
    stake_wei: int = field(metadata={"json": "uint256_string"})
    stake_contract: str = field(metadata={"json": "address"})


def _load_din_info_entry(network: str) -> dict:
    """Load the ``network`` entry from ``din_info.json``.

    Maps every infrastructure failure onto ``ConfigError`` instead of letting
    the underlying stdlib exception escape: a missing/unreadable file
    (``FileNotFoundError``/``OSError``), invalid JSON (``JSONDecodeError``),
    a network absent from the file (``KeyError`` today), or a network entry
    that parses but isn't a JSON object (``null``, a string, a list, ...).
    That last case matters even though it validates only shape, not content:
    without it, ``{"local": null}`` (or a string/list) passes this loader —
    JSON is valid, the key exists — and then ``get_platform_addresses()``
    hits ``None.get(...)`` (``TypeError``) or ``get_stake()`` hits
    ``None.get("stake")`` (``AttributeError``), both raw stdlib exceptions
    escaping the ``DinError`` taxonomy every other malformed-config shape in
    this function already raises through.
    """
    try:
        din_info = load_din_info()
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"din_info.json is not valid JSON: {e}",
            details={"key": "din_info.json"},
        ) from e
    except OSError as e:
        raise ConfigError(
            f"din_info.json could not be read: {e}",
            details={"key": "din_info.json"},
        ) from e

    if network not in din_info:
        raise ConfigError(
            f"Network '{network}' is not configured in din_info.json.",
            details={"key": network},
        )
    entry = din_info[network]
    if not isinstance(entry, dict):
        raise ConfigError(
            f"Network '{network}' entry in din_info.json is malformed: "
            f"expected an object, got {type(entry).__name__}.",
            details={"key": network},
        )
    return entry


def get_platform_addresses(session: DinSession) -> PlatformAddresses:
    """Read the configured platform contract addresses for ``session.network``.

    Reproduces today's ``data.get(key, 'N/A')`` CLI behavior exactly for every
    shape a hand-edited ``din_info.json`` entry can take (key absent, ``null``,
    empty string, malformed/placeholder, valid) — see the class docstring.
    """
    network = session.network
    entry = _load_din_info_entry(network)
    present = frozenset(key for key in _ADDRESS_KEYS if key in entry)
    return PlatformAddresses(
        network=network,
        coordinator=entry.get("coordinator"),
        token=entry.get("token"),
        stake=entry.get("stake"),
        representative=entry.get("representative"),
        registry=entry.get("registry"),
        present=present,
    )


def get_stake_contract_address(network: str) -> str:
    """Resolve and validate the staking contract address configured for
    ``network``, returned exactly as it appears in ``din_info.json`` — no
    checksumming.

    Split out of ``get_stake()`` so a caller (the CLI's
    ``read_dintoken_stake()``) can render the address before attempting the
    contract call, the same way ``get_deployed_din_stake_contract()`` used to
    print it as an unconditional side effect strictly before ``getStake()``
    could fail. Returning the address as-configured, rather than
    checksummed, matters too: a hand-edited lowercase address must print
    lowercase, matching what the CLI showed before this operations layer
    existed.
    """
    entry = _load_din_info_entry(network)
    stake_address = entry.get("stake")
    if not stake_address or not Web3.is_address(stake_address):
        raise ConfigError(
            f"Network '{network}' has no valid staking contract address configured.",
            details={"key": "stake"},
        )
    return stake_address


def get_stake(session: DinSession, address: str | None = None) -> StakeInfo:
    """Read ``address``'s (or the session's signer's) staked DIN balance.

    When ``address`` is omitted, falls back to ``session.address`` — which
    raises ``SignerUnavailable`` when no non-interactive password source is
    available. That is designed behavior (§3.3): it is propagated unchanged,
    never re-wrapped, so the job layer sees the same stable code the signing
    path already produces.
    """
    network = session.network
    stake_address = Web3.to_checksum_address(get_stake_contract_address(network))

    if address is not None:
        if not Web3.is_address(address):
            raise ValidationError(
                f"'{address}' is not a valid Ethereum address.",
                details={
                    "field": "address",
                    "expected": "0x-prefixed 40-hex-char address",
                    "actual": str(address),
                },
            )
        holder = Web3.to_checksum_address(address)
    else:
        # May raise SignerUnavailable — propagated unchanged (§3.3).
        holder = Web3.to_checksum_address(session.address)

    artifact_path = files("dincli").joinpath("abis", _STAKE_ABI_NAME)

    try:
        contract = get_contract_instance(str(artifact_path), network, stake_address, w3=session.w3)
    except DinError:
        raise
    except Exception as e:
        raise ContractError(
            f"Could not construct the DinValidatorStake contract on network '{network}': {e}",
            details={"contract": "DinValidatorStake"},
        ) from e

    try:
        stake_wei = contract.functions.getStake(holder).call()
    except DinError:
        raise
    except Exception as e:
        raise ContractError(
            f"getStake call failed for {holder} on network '{network}': {e}",
            details={"contract": "DinValidatorStake", "function": "getStake"},
        ) from e

    return StakeInfo(
        network=network,
        address=holder,
        stake_wei=stake_wei,
        stake_contract=stake_address,
    )
