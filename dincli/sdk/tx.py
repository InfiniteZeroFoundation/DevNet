"""Transaction building, signing, and submission with nonce management.

Pure module: no imports from ``dincli.cli``, ``typer``, or ``rich``. The CLI's
``build_and_send_tx`` wraps ``send()`` and adds console output; the daemon calls
``send()`` directly.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from web3 import Web3
from web3.contract.contract import ContractEvent, ContractFunction
from web3.types import TxReceipt

from dincli.sdk.errors import TransactionError
from dincli.sdk.errors import (
    TX_ESTIMATION_FAILED,
    TX_NONCE_CONFLICT,
    TX_REPLACEMENT_UNDERPRICED,
    TX_REVERTED,
    TX_TIMEOUT,
    RECEIPT_MISSING,
)
from dincli.sdk.session import DinSession

_NONCE_TOO_LOW = "nonce too low"
_ALREADY_KNOWN = "already known"
_REPLACEMENT_UNDERPRICED = "replacement transaction underpriced"
_RESERVATION_TTL_S = 90.0


# ---------------------------------------------------------------------------
# TxReceiptInfo — normalized, JSON-serializable receipt wrapper
# ---------------------------------------------------------------------------


def _normalize_log(log_entry) -> dict:
    """Recursively normalize web3 AttributeDict / HexBytes → standard Python types."""
    if isinstance(log_entry, (bytes, bytearray)):
        return "0x" + log_entry.hex()
    if isinstance(log_entry, dict):
        return {k: _normalize_log(v) for k, v in log_entry.items()}
    if isinstance(log_entry, (list, tuple)):
        return [_normalize_log(v) for v in log_entry]
    if hasattr(log_entry, "items"):
        return {k: _normalize_log(v) for k, v in log_entry.items()}
    if hasattr(log_entry, "__dict__"):
        return {k: _normalize_log(v) for k, v in vars(log_entry).items()}
    return log_entry


def _to_checksum(w3: Web3 | None, addr: str | None) -> str | None:
    if addr is None or w3 is None:
        return addr
    return w3.to_checksum_address(addr)


@dataclass
class TxReceiptInfo:
    tx_hash: str
    status: int
    block_number: int
    gas_used: int
    nonce: int
    contract_address: str | None
    logs: list[dict]
    _raw: TxReceipt = field(repr=False, metadata={"json": "omit"})

    @classmethod
    def from_receipt(cls, receipt: TxReceipt, w3: Web3 | None = None) -> "TxReceiptInfo":
        tx_hash = receipt.transactionHash
        if isinstance(tx_hash, bytes):
            tx_hash = "0x" + tx_hash.hex()

        logs = [_normalize_log(log) for log in (receipt.logs or [])]

        return cls(
            tx_hash=tx_hash,
            status=receipt.status,
            block_number=receipt.blockNumber,
            gas_used=receipt.gasUsed,
            nonce=0,  # filled in by send() after tx build
            contract_address=_to_checksum(w3, receipt.contractAddress),
            logs=logs,
            _raw=receipt,
        )


# ---------------------------------------------------------------------------
# NonceManager — per-(chain_id, address) state machine
# ---------------------------------------------------------------------------


class NonceManager:
    """Per-(chain_id, address) nonce allocation with an explicit state machine.

    Three states, all mutated under one per-account mutex:
      reserved  : dict[int, float]  — allocated, NOT yet broadcast (nonce -> reserved_at)
      inflight  : set[int]          — broadcast, not yet confirmed
      confirmed : implicit          — anything < get_transaction_count(addr, "pending")

    reserve(w3, addr):
        n = get_transaction_count(addr, "pending")
        while n in reserved or n in inflight:
            n += 1
        reserved[n] = monotonic()
        return n

    prune(w3, addr):
        base = get_transaction_count(addr, "pending")
        drop every reserved/inflight entry < base
        drop every reserved entry older than RESERVATION_TTL_S

    mark_broadcast(nonce): reserved.pop(nonce); inflight.add(nonce)
    release(nonce):        reserved.pop(nonce, None)
    resync(w3, addr):      reserved.clear(); inflight.clear()
    """

    _instances: dict[tuple[int, str], "NonceManager"] = {}
    _lock = threading.Lock()

    def __init__(self, chain_id: int, address: str):
        self._chain_id = chain_id
        self._address = address
        self._mutex = threading.Lock()
        self._reserved: dict[int, float] = {}
        self._inflight: set[int] = set()

    @classmethod
    def for_session(cls, session: DinSession) -> "NonceManager":
        chain_id: int = session.w3.eth.chain_id
        address: str = session.address
        key = (chain_id, address)
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(chain_id, address)
            return cls._instances[key]

    def _get_pending_nonce(self, w3) -> int:
        return w3.eth.get_transaction_count(self._address, "pending")

    def _now(self) -> float:
        return time.monotonic()

    def prune(self, w3) -> None:
        base = self._get_pending_nonce(w3)
        now = self._now()
        drop_reserved: list[int] = []
        for n, reserved_at in list(self._reserved.items()):
            if n < base or (now - reserved_at) > _RESERVATION_TTL_S:
                drop_reserved.append(n)
        for n in drop_reserved:
            del self._reserved[n]
        drop_inflight: list[int] = [n for n in self._inflight if n < base]
        for n in drop_inflight:
            self._inflight.discard(n)

    def reserve(self, w3) -> int:
        with self._mutex:
            self.prune(w3)
            n = self._get_pending_nonce(w3)
            while n in self._reserved or n in self._inflight:
                n += 1
            self._reserved[n] = self._now()
            return n

    def mark_broadcast(self, nonce: int) -> None:
        with self._mutex:
            self._reserved.pop(nonce, None)
            self._inflight.add(nonce)

    def release(self, nonce: int) -> None:
        self._reserved.pop(nonce, None)

    def resync(self, w3) -> None:
        with self._mutex:
            self._reserved.clear()
            self._inflight.clear()


# ---------------------------------------------------------------------------
# build_tx_params
# ---------------------------------------------------------------------------


def build_tx_params(
    session: DinSession,
    overrides: dict | None = None,
) -> dict:
    """Build base tx params from session. Nonce comes from NonceManager
    (BL-1: ``block_identifier="pending"`` instead of bare ``"latest"``).

    If ``overrides`` supplies a ``nonce``, it takes precedence (for replacement
    transactions — §3g).
    """
    nonce_mgr = NonceManager.for_session(session)
    w3 = session.w3

    params: dict[str, Any] = {
        "from": session.address,
        "maxFeePerGas": w3.eth.gas_price * 2,
        "maxPriorityFeePerGas": w3.eth.max_priority_fee,
        "chainId": w3.eth.chain_id,
    }

    if overrides:
        # Caller-supplied nonce bypasses allocation (replacement txs)
        params.update(overrides)
        if "nonce" not in params:
            params["nonce"] = nonce_mgr.reserve(w3)
    else:
        params["nonce"] = nonce_mgr.reserve(w3)

    return params


# ---------------------------------------------------------------------------
# on_event vocabulary (§5b Q2)
# ---------------------------------------------------------------------------

_EventName = str
_EventPayload = dict[str, Any]
_OnEvent = Callable[[_EventName, _EventPayload], None]


def _emit(on_event: _OnEvent | None, name: str, payload: dict) -> None:
    if on_event is None:
        return
    try:
        on_event(name, payload)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# send — the main tx execution path
# ---------------------------------------------------------------------------


def send(
    session: DinSession,
    contract_function: ContractFunction,
    *,
    tx_params: dict | None = None,
    on_event: _OnEvent | None = None,
    timeout_s: float = 120.0,
    poll_interval_s: float = 0.1,
) -> TxReceiptInfo:
    """Sign, broadcast, and wait for a contract transaction.

    The caller receives a ``TxReceiptInfo`` on success; exceptions are raised as
    ``TransactionError`` with the subcode from §3d.

    Replacing a stuck tx: make another ``send()`` call with
    ``tx_params={"nonce": n, "maxFeePerGas": ...}`` — the ``NonceManager``
    honours caller-supplied nonce overrides (§3g).
    """
    w3 = session.w3
    account = session.account
    nonce_mgr = NonceManager.for_session(session)
    network = session.network

    base_params = build_tx_params(session, overrides=tx_params)
    nonce: int = base_params["nonce"]

    # --- estimate gas ---
    try:
        estimated = int(
            w3.eth.estimate_gas(
                contract_function.build_transaction(base_params)
            )
            * 1.1
        )
    except Exception as e:
        nonce_mgr.release(nonce)
        _emit(on_event, "estimation_failed", {"reason": str(e)[:256]})
        raise TransactionError(
            str(e), code=TX_ESTIMATION_FAILED,
            details={"reason": str(e)[:256], "broadcast": False},
        ) from e

    base_params["gas"] = estimated

    # --- build + sign ---
    tx = contract_function.build_transaction(base_params)
    signed = account.sign_transaction(tx)
    tx_hash = signed.hash.hex()

    _emit(on_event, "broadcasting", {"tx_hash": tx_hash, "nonce": nonce})

    # --- broadcast ---
    try:
        tx_hash_raw = w3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception as e:
        msg_lower = str(e).lower()
        is_already_known = _ALREADY_KNOWN in msg_lower or "nonce too low" in msg_lower and _NONCE_TOO_LOW in msg_lower

        if _NONCE_TOO_LOW in msg_lower and _ALREADY_KNOWN not in msg_lower:
            nonce_mgr.resync(w3)
            _emit(on_event, "submitted", {"tx_hash": tx_hash, "nonce": nonce})
            raise TransactionError(
                "Nonce too low — transaction rejected.",
                code=TX_NONCE_CONFLICT,
                details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": False},
            ) from e
        if _ALREADY_KNOWN in msg_lower:
            nonce_mgr.mark_broadcast(nonce)
            _emit(on_event, "submitted", {"tx_hash": tx_hash, "nonce": nonce})
            raise TransactionError(
                "Transaction already known — may be in flight.",
                code=TX_NONCE_CONFLICT,
                details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True},
            ) from e
        if _REPLACEMENT_UNDERPRICED in msg_lower:
            nonce_mgr.release(nonce)
            raise TransactionError(
                str(e),
                code=TX_REPLACEMENT_UNDERPRICED,
                details={"nonce": nonce, "broadcast": False},
            ) from e

        nonce_mgr.release(nonce)
        raise TransactionError(
            str(e),
            code=TX_ESTIMATION_FAILED,  # best-effort fallback
            details={"reason": str(e)[:256], "broadcast": False},
        ) from e

    nonce_mgr.mark_broadcast(nonce)
    _emit(on_event, "submitted", {"tx_hash": tx_hash, "nonce": nonce})

    # --- wait for receipt ---
    start = time.monotonic()
    while True:
        receipt = w3.eth.get_transaction_receipt(tx_hash)
        if receipt is not None:
            break
        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            _emit(on_event, "timeout", {"tx_hash": tx_hash, "nonce": nonce})
            raise TransactionError(
                f"Transaction {tx_hash} not confirmed within {timeout_s}s.",
                code=TX_TIMEOUT,
                details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True},
            )
        time.sleep(poll_interval_s)

    # --- returned from wait with a receipt ---
    info = TxReceiptInfo.from_receipt(receipt, w3)
    info.nonce = nonce  # patch in the nonce we know

    if receipt.status == 0:
        _emit(on_event, "reverted", {"tx_hash": tx_hash,
                                     "nonce": nonce,
                                     "block_number": receipt.blockNumber})
        raise TransactionError(
            f"Transaction {tx_hash} reverted.",
            code=TX_REVERTED,
            details={
                "tx_hash": tx_hash,
                "nonce": nonce,
                "block_number": receipt.blockNumber,
                "broadcast": True,
            },
        )

    _emit(on_event, "confirmed", {
        "tx_hash": tx_hash,
        "nonce": nonce,
        "block_number": receipt.blockNumber,
        "gas_used": receipt.gasUsed,
        "status": receipt.status,
    })

    return info


# ---------------------------------------------------------------------------
# decode_events
# ---------------------------------------------------------------------------


def decode_events(receipt_info: TxReceiptInfo,
                  contract_event: ContractEvent) -> list[dict]:
    """Wrap ``contract_event.process_receipt(receipt._raw)``."""
    return contract_event.process_receipt(receipt_info._raw)
