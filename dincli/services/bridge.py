"""Bridge ETH from Ethereum Sepolia L1 to OP Sepolia L2 via the
OP Stack L1StandardBridge proxy.

Deposits only — withdrawals are L2→L1, take ~7 days, and need
separate prove and finalize steps.
"""

from __future__ import annotations

import math
import time
from decimal import Decimal, InvalidOperation
from typing import Optional

from eth_account import Account
from web3 import Web3

try:
    import requests
except ImportError:  # pragma: no cover - requests is a project dependency
    requests = None


# ------------------------------------------------------------------ #
#  Constants (cited from superchain-registry for chain 11155420)     #
# ------------------------------------------------------------------ #

# Proxy address from the superchain-registry entry for op-sepolia.
# Do NOT call OTHER_BRIDGE() — it returns the same 0x4200…0010
# predeploy on every OP-Stack chain and proves nothing.
L1_STANDARD_BRIDGE_SEPOLIA = Web3.to_checksum_address(
    "0xFBb0621E0B23b5478B630BD55a5f21f67730B0F1"
)

L1_CHAIN_ID = 11155111   # Ethereum Sepolia
L2_CHAIN_ID = 11155420   # OP Sepolia

# L1 receipt wait (seconds) — explicit, never infinite (§3.2)
L1_RECEIPT_TIMEOUT = 120

# ------------------------------------------------------------------ #
#  L1StandardBridge.paused() ABI fragment                             #
# ------------------------------------------------------------------ #

_BRIDGE_ABI_PAUSED = [
    {
        "inputs": [],
        "name": "paused",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    }
]

# ------------------------------------------------------------------ #
#  BridgeError hierarchy                                              #
# ------------------------------------------------------------------ #


class BridgeError(Exception):
    """Base for all bridge-specific failures."""

    def __init__(self, message: str, outcome: str) -> None:
        super().__init__(message)
        self.outcome = outcome


class PreflightRejected(BridgeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "PREFLIGHT_REJECTED")


class SubmissionUnknown(BridgeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "SUBMISSION_UNKNOWN")


class SubmissionRejected(BridgeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "SUBMISSION_REJECTED")


class Reverted(BridgeError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "REVERTED")


# ------------------------------------------------------------------ #
#  Input parsing                                                      #
# ------------------------------------------------------------------ #

def parse_amount(amount) -> int:
    """Validate a user-supplied ETH amount and return exact integer wei.

    Accepts str, int, float, or Decimal. Rejects NaN, infinity, zero,
    negative, and any value below 1 wei.
    """
    try:
        if isinstance(amount, bool):
            raise InvalidOperation
        dec = Decimal(str(amount))
        if not dec.is_finite() or dec <= 0:
            raise InvalidOperation
        wei = int(dec * Decimal(10**18))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PreflightRejected(
            "amount must be a finite, positive number ≥ 1 wei"
        ) from exc

    if wei < 1:
        raise PreflightRejected("amount must be ≥ 1 wei")

    return wei


def connect_l1_rpc(url: str) -> Web3:
    """Build and validate an L1 Web3 instance.

    Connection failures raise PreflightRejected with a sanitized
    message — no RPC URL and no provider exception in user-facing output.
    """
    try:
        w3 = Web3(Web3.HTTPProvider(url))
        if not w3.is_connected():
            raise ConnectionError("not connected")
        return w3
    except Exception as exc:
        # A ConnectionError here is a *preflight* failure, not a
        # SUBMISSION_UNKNOWN ambiguity: nothing has been signed or sent.
        raise PreflightRejected("could not connect to the L1 RPC endpoint") from exc


def classify_broadcast_error(exc: Exception, tx_hash: str) -> BridgeError:
    """Map a broadcast/waits exception to its §3.8 outcome.

    Transport failures are ambiguous (the signed tx may have reached the
    node) → SUBMISSION_UNKNOWN. A deterministic JSON-RPC rejection is a
    clear no-send → SUBMISSION_REJECTED. Never auto-retry either way.
    """
    from web3.exceptions import (
        MultipleFailedRequests,
        ProviderConnectionError,
        TimeExhausted,
        Web3RPCError,
    )

    if isinstance(exc, (ProviderConnectionError, TimeExhausted, MultipleFailedRequests)):
        return SubmissionUnknown(
            f"broadcast transport failure — submission status unknown, "
            f"check this hash before retrying: {tx_hash}"
        )

    if requests is not None and isinstance(
        exc, (requests.ConnectionError, requests.Timeout, ConnectionError, TimeoutError)
    ):
        return SubmissionUnknown(
            f"broadcast transport failure — submission status unknown, "
            f"check this hash before retrying: {tx_hash}"
        )

    if isinstance(exc, Web3RPCError):
        return SubmissionRejected(
            f"node rejected the transaction — hash: {tx_hash}"
        )

    # Unknown failure mode: treat as ambiguous, never auto-retry.
    return SubmissionUnknown(
        f"broadcast outcome unknown — submission status unknown, "
        f"check this hash before retrying: {tx_hash}"
    )


# ------------------------------------------------------------------ #
#  Resolve L1 RPC                                                     #
# ------------------------------------------------------------------ #

def resolve_l1_rpc(
    cli_url: Optional[str],
    get_env_key,
) -> str:
    """Resolve the L1 RPC URL.

    Order: --l1-rpc-url flag → SEPOLIA_L1_RPC_URL env var → error
    naming both routes.
    """
    if cli_url and cli_url.strip():
        url = cli_url.strip()
    else:
        url = get_env_key("SEPOLIA_L1_RPC_URL", verbose=False)
        if not url or not url.strip():
            raise PreflightRejected(
                "L1 RPC URL not configured — pass --l1-rpc-url or "
                "set SEPOLIA_L1_RPC_URL in .env"
            )
    return url


# ------------------------------------------------------------------ #
#  Preflight — four explicit stages                                   #
# ------------------------------------------------------------------ #

def _check_code(w3: Web3, address: str, chain_label: str) -> None:
    code = w3.eth.get_code(address)
    if code != b"" and code != "0x":
        raise PreflightRejected(
            f"{chain_label} address {address} is a contract, not an EOA — "
            f"ETH sent to a contract can be locked"
        )


def static_preflight(
    *,
    network: str,
    l1_w3: Web3,
    l2_w3: Web3,
    sender: str,
) -> None:
    """Stage 1 — validate env, chain ids, bridge, and sender/recipient codes.

    No fee or gas work yet.
    """
    if network != "sepolia_op_devnet":
        raise PreflightRejected(
            f"bridge-eth requires network 'sepolia_op_devnet', "
            f"got '{network}'"
        )

    if l1_w3.eth.chain_id != L1_CHAIN_ID:
        raise PreflightRejected(
            f"L1 chain ID mismatch: expected {L1_CHAIN_ID}, "
            f"got {l1_w3.eth.chain_id}"
        )

    if l2_w3.eth.chain_id != L2_CHAIN_ID:
        raise PreflightRejected(
            f"L2 chain ID mismatch: expected {L2_CHAIN_ID}, "
            f"got {l2_w3.eth.chain_id}"
        )

    l1_code = l1_w3.eth.get_code(L1_STANDARD_BRIDGE_SEPOLIA)
    if l1_code in (b"", "0x"):
        raise PreflightRejected(
            "bridge proxy has no bytecode on L1 — wrong chain or address?"
        )

    bridge_contract = l1_w3.eth.contract(
        address=L1_STANDARD_BRIDGE_SEPOLIA,
        abi=_BRIDGE_ABI_PAUSED,
    )
    if bridge_contract.functions.paused().call():
        raise PreflightRejected("L1StandardBridge is paused — deposits blocked")

    _check_code(l1_w3, sender, "Sender (L1)")

    _check_code(l2_w3, sender, "Recipient (L2)")


def prepare_transaction(
    *,
    l1_w3: Web3,
    sender: str,
    amount_wei: int,
) -> tuple[dict, int]:
    """Stage 2 — fee caps, pending nonce, gas estimate, ceiling buffer.

    Returns (tx_params, estimated_gas) so the caller can print the raw
    estimate and the buffered signed limit separately (§3.4).
    """
    base_fee = l1_w3.eth.get_block("latest")["baseFeePerGas"]
    priority_fee = int(l1_w3.eth.max_priority_fee)
    max_fee_per_gas = 2 * base_fee + priority_fee

    assert max_fee_per_gas >= priority_fee, "maxFeePerGas < maxPriorityFeePerGas"

    nonce = l1_w3.eth.get_transaction_count(sender, "pending")

    tx = {
        "from": sender,
        "to": L1_STANDARD_BRIDGE_SEPOLIA,
        "value": amount_wei,
        "data": b"",
        "chainId": L1_CHAIN_ID,
        "nonce": nonce,
        "maxFeePerGas": max_fee_per_gas,
        "maxPriorityFeePerGas": priority_fee,
    }

    # Gas estimation is the first call that touches the sender's balance, so an
    # unfunded L1 account fails here — before affordability_check, which is where
    # the readable message lives. Uncaught, the node's JSON-RPC error surfaced as
    # a raw traceback on what is the single most likely first run: attempting a
    # deposit before funding L1. Classify it as a preflight rejection so the CLI's
    # existing BridgeError handler renders one actionable line.
    try:
        estimated = l1_w3.eth.estimate_gas(tx)
    except Exception as exc:
        detail = str(exc)
        if "insufficient funds" in detail.lower():
            have = l1_w3.eth.get_balance(sender)
            raise PreflightRejected(
                f"insufficient L1 funds: the sender holds "
                f"{Web3.from_wei(have, 'ether')} ETH on Ethereum Sepolia, which "
                f"does not cover {Web3.from_wei(amount_wei, 'ether')} ETH plus "
                f"the L1 fee. Fund {sender} on L1 first."
            ) from None
        raise PreflightRejected(
            f"could not estimate gas for the deposit: {type(exc).__name__}"
        ) from None

    # Integer ceiling: ceil(estimate * 1.20)
    gas_limit = int(math.ceil(estimated * 1.20))

    tx["gas"] = gas_limit

    return tx, estimated


def affordability_check(
    *,
    l1_w3: Web3,
    sender: str,
    value: int,
    gas_limit: int,
    max_fee_per_gas: int,
) -> None:
    """Stage 3 — balance >= value + gas_limit * max_fee_per_gas."""
    balance = l1_w3.eth.get_balance(sender)
    maximum_cost = value + gas_limit * max_fee_per_gas
    if balance < maximum_cost:
        raise PreflightRejected(
            f"insufficient L1 balance — need at least "
            f"{l1_w3.from_wei(maximum_cost, 'ether')} ETH "
            f"(have {l1_w3.from_wei(balance, 'ether')})"
        )


def _hex0x(value) -> str:
    """Render HexBytes as a 0x-prefixed string, across hexbytes versions.

    hexbytes >= 1.0 returns .hex() without the prefix; earlier releases
    included it. pyproject allows web3 >= 6.0.0, which spans both, and a
    double-prefixed hash would be uncopyable into an explorer at exactly
    the moment the operator needs it.
    """
    rendered = value.hex()
    return rendered if rendered.startswith("0x") else "0x" + rendered


def sign_deposit(
    *,
    sender_account,
    tx: dict,
) -> tuple:
    """Sign locally and return (signed_tx, tx_hash_hex).

    The hash is computed from the signed raw transaction before any
    broadcast, so it exists even if the node never responds.
    """
    signed = Account.sign_transaction(tx, sender_account.key)
    return signed, _hex0x(signed.hash)


def broadcast_and_wait(
    *,
    l1_w3: Web3,
    signed,
    tx_hash: str,
    l1_timeout: int = 120,
) -> tuple[str, int]:
    """Broadcast a signed deposit and wait for L1 inclusion.

    Returns (tx_hash, block_number). Never auto-retries — a signed value
    transfer is broadcast exactly once.
    """
    try:
        l1_w3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception as exc:
        raise classify_broadcast_error(exc, tx_hash)

    try:
        receipt = l1_w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=l1_timeout
        )
    except Exception as exc:
        # TimeExhausted and transport failures both mean the broadcast may
        # have succeeded but we couldn't observe it — ambiguous, no retry.
        raise SubmissionUnknown(
            f"L1 receipt wait failed — submission status unknown, "
            f"check this hash before retrying: {tx_hash}"
        ) from exc

    if receipt is None:
        raise SubmissionUnknown(
            f"no receipt received — submission status unknown, "
            f"check this hash before retrying: {tx_hash}"
        )

    if _hex0x(receipt.transactionHash) != tx_hash:
        raise SubmissionUnknown(
            f"receipt hash mismatch — submission status unknown, "
            f"check this hash before retrying: {tx_hash}"
        )

    if receipt.status == 0:
        raise Reverted(
            f"transaction reverted — included in block {receipt.blockNumber}, "
            f"hash: {tx_hash}"
        )

    return tx_hash, receipt.blockNumber


# ------------------------------------------------------------------ #
#  L2 balance polling — visibility heuristic, not verification        #
# ------------------------------------------------------------------ #

def poll_l2_balance(
    *,
    l2_w3: Web3,
    address: str,
    baseline_wei: int,
    timeout: int = 360,
    poll_interval: int = 5,
) -> bool:
    """Poll L2 until the balance rises above baseline or timeout expires.

    Returns True if a balance increase was observed, False on timeout.
    This is a heuristic — it never proves *this* deposit caused the change.
    """
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            current = l2_w3.eth.get_balance(address)
        except Exception:
            time.sleep(poll_interval)
            continue

        if current > baseline_wei:
            return True

        time.sleep(poll_interval)

    return False