"""Transaction building, signing, and submission with nonce management.

Pure module: no imports from ``dincli.cli``, ``typer``, or ``rich``. The CLI's
``build_and_send_tx`` wraps ``send()`` and adds console output; the daemon calls
``send()`` directly.
"""
from __future__ import annotations

import threading
import time
import weakref
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from web3 import Web3
from web3.contract.contract import ContractEvent, ContractFunction
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt

from dincli.sdk.errors import DinError, TransactionError
from dincli.sdk.errors import (
    TX_ESTIMATION_FAILED,
    TX_NONCE_CONFLICT,
    TX_REPLACEMENT_UNDERPRICED,
    TX_REVERTED,
    TX_TIMEOUT,
    RECEIPT_MISSING,
    NONCE_MANAGER_CAPACITY,
)
from dincli.sdk.session import DinSession

_NONCE_TOO_LOW = "nonce too low"
_ALREADY_KNOWN = "already known"
_REPLACEMENT_UNDERPRICED = "replacement transaction underpriced"
_RESERVATION_TTL_S = 90.0


# ---------------------------------------------------------------------------
# TxReceiptInfo — normalized, JSON-serializable receipt wrapper
# ---------------------------------------------------------------------------


def _normalize_log(log_entry) -> Any:
    """Recursively normalize web3 AttributeDict / HexBytes → standard Python types.

    Returns whatever shape it was handed (dict, list, str, int) — not always a
    dict, hence the Any (M10).
    """
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
    def from_receipt(cls, receipt: TxReceipt, w3: Web3 | None = None,
                     *, nonce: int) -> "TxReceiptInfo":
        """Build from a web3 receipt.

        ``nonce`` is required rather than defaulted: a receipt does not carry
        it, and silently returning ``nonce=0`` would put a wrong value on the
        retry surface a daemon keys off (M9).
        """
        tx_hash = receipt.transactionHash
        if isinstance(tx_hash, bytes):
            tx_hash = "0x" + tx_hash.hex()

        logs = [_normalize_log(log) for log in (receipt.logs or [])]

        return cls(
            tx_hash=tx_hash,
            status=receipt.status,
            block_number=receipt.blockNumber,
            gas_used=receipt.gasUsed,
            nonce=nonce,
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
    mark_confirmed(nonce): inflight.discard(nonce)  # terminal, success or revert
    release(nonce):        reserved.pop(nonce, None)
    resync(w3, addr):      reserved.clear(); inflight.clear()

    The process-wide ``_instances`` cache is bounded at ``_MAX_INSTANCES``. On
    insert over the cap it evicts the least-recently-used *idle* manager from
    that strong cache. A busy manager (reservation held, or mutex held
    mid-``reserve()``) is never evicted: two managers for one account would
    reserve the same pending nonce and build two different transactions
    against it. If every cached manager is busy, ``for_session()`` raises
    ``nonce_manager_capacity`` instead.

    Identity, independent of the bound above: for a given ``(chain_id,
    address)`` there must never be two live ``NonceManager`` objects, even
    when the strong cache evicts one. ``_instances`` is only the memory-bound
    LRU cache; ``_live`` is a ``WeakValueDictionary`` holding *every* manager
    any caller still references, regardless of whether it is also in
    ``_instances``. ``for_session()`` always checks ``_live`` first. An idle
    manager that a caller is holding (e.g. between ``for_session()`` and
    ``reserve()`` in ``build_tx_params()``) is therefore never duplicated by
    eviction: dropping it from ``_instances`` only drops a strong reference,
    and ``_live`` keeps returning the same object as long as anyone holds it.

    ``_live`` alone is not enough, though: it only helps while some caller
    keeps a Python reference. ``build_tx_params()`` does not — it holds its
    manager in a local variable, calls ``reserve()``, copies the resulting
    nonce into a plain ``dict``, and returns. Once that local variable goes
    out of scope, ``_live`` cannot help either, and a manager evicted from
    ``_instances`` while merely idle (before its own reservation existed)
    is garbage-collected together with the reservation it took a moment
    later — the caller's reference and the manager's *own state* are two
    different lifetimes, and only one of them was ever protected.

    Ownership therefore does not live with the caller at all: every state
    mutation (``reserve()``, ``mark_broadcast()``, ``mark_confirmed()``,
    ``release()``, ``resync()``) takes an activity *lease* first —
    ``_begin_activity()`` re-admits ``self`` into ``_instances`` if it fell
    out, and bumps an active-use counter, atomically under ``_lock``, before
    touching ``_reserved``/``_inflight`` at all. Admission and "about to
    become busy" happen as one atomic step, so eviction can never land in
    the gap between them (an idle-but-referenced manager can still be
    dropped from ``_instances`` at any time — see above — but by the time it
    is asked to mutate state, it is unconditionally back in the strong
    cache first). The lease is released after the mutation, under ``_lock``
    again, but the manager stays in ``_instances`` afterward if it still
    holds reserved/inflight state — only a manager with zero active uses
    *and* no unsettled nonce state is eligible for the next eviction scan.
    ``_lock`` is never held across an RPC call or while blocked on
    ``self._mutex``: ``_begin_activity``/``_end_activity`` each acquire and
    release it for bookkeeping only, and the actual reservation work happens
    under ``self._mutex`` with ``_lock`` already released.
    """

    _instances: "OrderedDict[tuple[int, str], NonceManager]" = OrderedDict()
    _live: "weakref.WeakValueDictionary[tuple[int, str], NonceManager]" = (
        weakref.WeakValueDictionary()
    )
    # Active-use (leased) count per key, maintained only while a mutation is
    # in flight — see _begin_activity/_end_activity. A manager with a nonzero
    # count here is never evictable regardless of its idle/busy state, which
    # closes the admission/eviction race that _reserved/_inflight alone
    # cannot: those only reflect state *after* a mutation has started.
    _active: "Dict[tuple[int, str], int]" = {}
    _MAX_INSTANCES = 64
    _lock = threading.Lock()

    def __init__(self, chain_id: int, address: str):
        self._chain_id = chain_id
        self._address = address
        self._mutex = threading.Lock()
        self._reserved: dict[int, float] = {}
        self._inflight: set[int] = set()
        # Only a manager obtained through for_session() is registry-managed
        # (see _activity_lease): a directly-constructed NonceManager — the
        # unit-test convention throughout this module — deliberately stays
        # outside `_instances`/`_live`/`_active` so low-level mutation tests
        # can exercise reserve()/mark_broadcast()/etc. in isolation without
        # side effects on the shared, process-wide cache.
        self._managed = False

    @classmethod
    def for_session(cls, session: DinSession) -> "NonceManager":
        chain_id: int = session.w3.eth.chain_id
        address: str = session.address
        key = (chain_id, address)
        with cls._lock:
            # Check the weak registry FIRST — it is the source of truth for
            # identity. A manager can be idle, evicted from ``_instances``,
            # and still alive here because a caller (e.g. build_tx_params()
            # between for_session() and reserve()) holds it.
            mgr = cls._live.get(key)
            if mgr is not None:
                if key in cls._instances:
                    cls._instances.move_to_end(key)
                else:
                    # Referenced elsewhere but fell out of the strong cache —
                    # restore it rather than creating a duplicate for `key`.
                    if len(cls._instances) >= cls._MAX_INSTANCES:
                        cls._evict_lru_idle()
                    cls._instances[key] = mgr
                return mgr
            if len(cls._instances) >= cls._MAX_INSTANCES:
                cls._evict_lru_idle()
            mgr = cls(chain_id, address)
            mgr._managed = True
            cls._instances[key] = mgr
            cls._live[key] = mgr
            return mgr

    @classmethod
    def _evict_lru_idle(cls) -> None:
        """Evict the oldest evictable manager from the strong cache; caller
        holds ``cls._lock``.

        This only removes ``key`` from ``_instances`` — the memory-bound LRU
        cache. It never removes anything from ``_live``: if some caller still
        holds the manager, ``_live`` keeps it alive and the next
        ``for_session()`` for that key returns the SAME object (see
        ``for_session()``). If nobody holds it, Python's refcounting drops it
        from ``_live`` on its own once this method's local reference to it
        goes away. Either outcome is correct — this method is purely a
        memory-bound eviction, never an identity decision.

        A key with a nonzero ``_active`` lease count is skipped outright: a
        mutation is in flight for it right now (see ``_begin_activity``), so
        it must not be evicted no matter what its ``_reserved``/``_inflight``
        state looks like at this instant. Otherwise, iterating oldest→newest
        and stopping at the first evictable entry implements LRU ordering
        while preferring idle over busy: a busy manager at the LRU end is
        skipped. ``_is_evictable_nonblocking`` must not block — a blocking
        probe here would wait on a per-account mutex that ``reserve()`` holds
        across an RPC, freezing every ``for_session()`` in the process.
        """
        for key in list(cls._instances.keys()):
            if cls._active.get(key, 0) > 0:
                continue
            if cls._instances[key]._is_evictable_nonblocking():
                del cls._instances[key]
                return
        raise TransactionError(
            f"NonceManager cache is at capacity ({cls._MAX_INSTANCES}) and every "
            "cached manager is busy; refusing to evict an in-use manager.",
            code=NONCE_MANAGER_CAPACITY,
            details={"limit": cls._MAX_INSTANCES, "busy": len(cls._instances)},
        )

    @classmethod
    def _begin_activity(cls, key: "tuple[int, str]", mgr: "NonceManager") -> None:
        """Admit ``mgr`` into the bounded strong cache (re-admitting it if it
        fell out) and mark it actively in use, atomically under ``cls._lock``.

        Called at the top of every state-mutating method, before touching
        ``self._mutex``/RPC/``_reserved``/``_inflight``. This is what closes
        the actual eviction hole: identity (``_live``) already guarantees
        ``for_session()`` returns the same object; this additionally
        guarantees that the moment a manager is about to become busy, it is
        unconditionally back in ``_instances`` — so losing every external
        reference to it afterward can no longer lose its state, because
        ``_instances`` itself now holds one.

        Raises ``NONCE_MANAGER_CAPACITY`` (via ``_evict_lru_idle``) before any
        caller mutates ``_reserved``/``_inflight`` if the cache is full of
        other active/busy managers — admission failure must always happen
        before state changes, never after.

        Releases ``cls._lock`` before returning. The caller then acquires
        ``self._mutex`` and may perform RPC without ever holding the
        registry lock at the same time.
        """
        with cls._lock:
            cls._live[key] = mgr
            if key in cls._instances:
                cls._instances.move_to_end(key)
            else:
                if len(cls._instances) >= cls._MAX_INSTANCES:
                    cls._evict_lru_idle()
                cls._instances[key] = mgr
            cls._active[key] = cls._active.get(key, 0) + 1

    @classmethod
    def _end_activity(cls, key: "tuple[int, str]") -> None:
        """Release one lease taken by ``_begin_activity`` for ``key``.

        Does not itself evict anything: a manager that still holds
        reserved/inflight state remains in ``_instances`` regardless of its
        active-use count (see ``_evict_lru_idle``'s own state check). This
        only makes the manager eligible again for the *next* eviction scan
        once both conditions hold — no active lease and no unsettled state.
        """
        with cls._lock:
            remaining = cls._active.get(key, 1) - 1
            if remaining <= 0:
                cls._active.pop(key, None)
            else:
                cls._active[key] = remaining

    @classmethod
    def reset_all(cls, *, force: bool = False) -> None:
        """Test-only: clear the process-wide instance cache.

        Refuses while any cached manager is busy so a test that leaks a
        reservation fails loudly rather than silently corrupting the next
        test — but only if the call site actually invokes it unforced.
        ``force=True`` discards known-busy state and must be passed
        explicitly at the call site where that discard is intended. This
        test suite's convention: ``setup_method`` calls ``reset_all()``
        unforced, so it doubles as a live assertion that the previous test
        cleaned up after itself; a class whose tests are meant to end busy
        instead declares a ``teardown_method`` that calls
        ``reset_all(force=True)`` to confine its own mess. Clearing a busy
        manager during live use would recreate the duplicate-manager,
        duplicate-nonce hazard the bound exists to prevent.

        Also clears ``_live``, not just ``_instances``. Without that, a
        manager kept alive past its owning test only by a traceback/frame
        reference cycle (e.g. a retained ``pytest.raises`` ExceptionInfo)
        could still answer a later test's ``for_session()`` for the same
        key, leaking state across the "clean slate" this method promises.
        Test-only, so unconditionally discarding the identity registry here
        is safe — it never runs in production.
        """
        with cls._lock:
            if not force:
                for mgr in list(cls._instances.values()):
                    if not mgr._is_idle_nonblocking():
                        raise RuntimeError(
                            "NonceManager.reset_all() refused: a cached manager "
                            "is busy; pass force=True to discard known-busy state."
                        )
            cls._instances.clear()
            cls._live.clear()
            cls._active.clear()

    def _is_idle_nonblocking(self) -> bool:
        """True when nothing is reserved/inflight and the mutex is free *now*.

        A held mutex means a ``reserve()``/``prune()`` is mid-flight, so the
        manager is treated as busy. Acquisition is non-blocking by design (see
        ``_evict_lru_idle``).
        """
        if not self._mutex.acquire(blocking=False):
            return False
        try:
            return not self._reserved and not self._inflight
        finally:
            self._mutex.release()

    def _is_evictable_nonblocking(self) -> bool:
        """True when this manager can be safely dropped from ``_instances``
        right now: no inflight (uncertain broadcast) nonce, and no *live*
        reservation, with the mutex free.

        Unlike ``_is_idle_nonblocking``, this also reclaims reservations
        older than ``_RESERVATION_TTL_S``: a caller that reserved a nonce and
        then leaked its reference without ever confirming, broadcasting, or
        releasing it would otherwise pin this manager in the bounded cache
        forever. The reclaim is wall-clock only — no RPC — so it is safe to
        do here, under a non-blocking mutex acquisition, without violating
        the "never block/RPC while scanning for eviction" rule.

        Inflight nonces are NEVER expired this way: a broadcast whose outcome
        is unknown must never be discarded just to make room (see ``send()``
        §10 on why ``broadcast=True`` is treated conservatively).
        """
        if not self._mutex.acquire(blocking=False):
            return False
        try:
            if self._inflight:
                return False
            if self._reserved:
                now = self._now()
                stale = [
                    n for n, reserved_at in self._reserved.items()
                    if (now - reserved_at) > _RESERVATION_TTL_S
                ]
                for n in stale:
                    del self._reserved[n]
            return not self._reserved
        finally:
            self._mutex.release()

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

    @property
    def _key(self) -> "tuple[int, str]":
        return (self._chain_id, self._address)

    @contextmanager
    def _activity_lease(self):
        """Hold an admission/activity lease for the duration of one state
        mutation (see ``_begin_activity``/``_end_activity``).

        A no-op for a manager that isn't registry-managed (``_managed`` is
        only set by ``for_session()``): a directly-constructed manager used
        in isolation by lower-level tests must not be pulled into the
        shared, process-wide cache as a side effect of calling ``reserve()``
        on it.
        """
        if not self._managed:
            yield
            return
        key = self._key
        NonceManager._begin_activity(key, self)
        try:
            yield
        finally:
            NonceManager._end_activity(key)

    def reserve(self, w3) -> int:
        """Allocate the next free nonce.

        Wrapped in an activity lease: this is the transition from idle to
        busy, and the one place an already-evicted, no-longer-cache-owned
        manager must be forced back into ``_instances`` before anyone can see
        or act on the nonce it is about to hand out. The lease ends before
        returning, but by then ``self`` is back in ``_instances`` with a live
        reservation, so it stays there on its own merits — via the ordinary
        idle/busy eviction check — regardless of what the lease does next.
        """
        with self._activity_lease():
            with self._mutex:
                self.prune(w3)
                n = self._get_pending_nonce(w3)
                while n in self._reserved or n in self._inflight:
                    n += 1
                self._reserved[n] = self._now()
                return n

    def mark_broadcast(self, nonce: int) -> None:
        with self._activity_lease():
            with self._mutex:
                self._reserved.pop(nonce, None)
                self._inflight.add(nonce)

    def mark_confirmed(self, nonce: int) -> None:
        """A receipt is terminal state — the nonce is consumed.

        Called for both a successful receipt and a reverted one: a revert still
        consumed the nonce. Without this, ``_inflight`` grows without bound and
        completed work reads as busy forever.
        """
        with self._activity_lease():
            with self._mutex:
                self._inflight.discard(nonce)

    def release(self, nonce: int) -> None:
        # Mutex-guarded like every other mutator (M2) — an unguarded pop could
        # race a concurrent reserve()'s free-slot scan.
        with self._activity_lease():
            with self._mutex:
                self._reserved.pop(nonce, None)

    def resync(self, w3) -> None:
        with self._activity_lease():
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
    # Sign via the SignerProvider protocol only (address/can_decrypt/
    # sign_transaction). Never touch session.account / signer.local_account —
    # those are outside the published contract, so a daemon or hardware adapter
    # written to the protocol would break here (remediation R4).
    signer = session.signer
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
    # An ABI-encoding error or a signer failure here is pre-broadcast: the
    # reservation must be released or it leaks permanently. Base tx_failed code
    # carries nonce/broadcast/reason.
    try:
        tx = contract_function.build_transaction(base_params)
        signed = signer.sign_transaction(tx)
    except DinError:
        # A signer/session failure here (e.g. SignerUnavailable) already
        # carries its own stable code and sanitized details — release the
        # reservation but re-raise unchanged rather than re-coding it as
        # tx_failed, which would erase the subcode a daemon retry policy
        # keys off.
        nonce_mgr.release(nonce)
        raise
    except Exception as e:
        nonce_mgr.release(nonce)
        raise TransactionError(
            str(e),
            details={"nonce": nonce, "broadcast": False, "reason": str(e)[:256]},
        ) from e
    # HexBytes.hex() is UNPREFIXED (hexbytes>=1.0), so prefix explicitly —
    # keeps events/details consistent with TxReceiptInfo.tx_hash (R/M5).
    raw_hash = signed.hash.hex()
    tx_hash = raw_hash if raw_hash.startswith("0x") else "0x" + raw_hash

    _emit(on_event, "broadcasting", {"tx_hash": tx_hash, "nonce": nonce})

    # --- broadcast ---
    try:
        tx_hash_raw = w3.eth.send_raw_transaction(signed.raw_transaction)
    except Exception as e:
        msg_lower = str(e).lower()

        if _NONCE_TOO_LOW in msg_lower and _ALREADY_KNOWN not in msg_lower:
            # Rejected outright — nothing was submitted. Emitting "submitted"
            # here made the CLI print a tx hash and an explorer URL for a
            # transaction that never existed (R8). broadcast=False is correct:
            # the node refused it, so the caller may safely rebuild.
            nonce_mgr.resync(w3)
            raise TransactionError(
                "Nonce too low — transaction rejected.",
                code=TX_NONCE_CONFLICT,
                details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": False},
            ) from e
        if _ALREADY_KNOWN in msg_lower:
            # The node already holds this exact raw tx — it IS in flight.
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

        # Unclassified broadcast failure — estimation already succeeded, so
        # tx_estimation_failed was simply the wrong code (R6). Use the base
        # tx_failed subcode.
        #
        # broadcast=True is deliberate and conservative. A socket timeout or
        # dropped connection during send_raw_transaction may well have reached
        # the node, and §10 uses this flag to choose between "safe to rebuild"
        # (False) and "must confirm the existing tx, do not resend" (True).
        # On an unknown outcome, claiming False risks a double-send; claiming
        # True costs only a confirmation lookup. The tx_hash is known from
        # signing (§3c), so the consumer has what it needs to check.
        nonce_mgr.mark_broadcast(nonce)
        raise TransactionError(
            str(e),
            details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True,
                     "reason": str(e)[:256]},
        ) from e

    nonce_mgr.mark_broadcast(nonce)
    _emit(on_event, "submitted", {"tx_hash": tx_hash, "nonce": nonce})

    # --- wait for receipt ---
    # NOTE: w3.eth.get_transaction_receipt RAISES TransactionNotFound for an
    # unmined tx — it never returns None. Use web3's own waiter, which handles
    # that polling correctly (remediation R1).
    try:
        receipt = w3.eth.wait_for_transaction_receipt(
            tx_hash, timeout=timeout_s, poll_latency=poll_interval_s
        )
    except TimeExhausted as e:
        # Distinguish "still pending" from "dropped out of the mempool" — a
        # daemon retries those differently.
        try:
            w3.eth.get_transaction(tx_hash)
        except TransactionNotFound:
            _emit(on_event, "receipt_missing", {"tx_hash": tx_hash, "nonce": nonce})
            raise TransactionError(
                f"Transaction {tx_hash} was broadcast but is no longer known to the node.",
                code=RECEIPT_MISSING,
                details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True},
            ) from e
        _emit(on_event, "timeout", {"tx_hash": tx_hash, "nonce": nonce})
        raise TransactionError(
            f"Transaction {tx_hash} not confirmed within {timeout_s}s.",
            code=TX_TIMEOUT,
            details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True},
        ) from e

    if receipt is None:
        _emit(on_event, "receipt_missing", {"tx_hash": tx_hash, "nonce": nonce})
        raise TransactionError(
            f"No receipt returned for {tx_hash}.",
            code=RECEIPT_MISSING,
            details={"tx_hash": tx_hash, "nonce": nonce, "broadcast": True},
        )

    # --- returned from wait with a receipt ---
    info = TxReceiptInfo.from_receipt(receipt, w3, nonce=nonce)

    if receipt.status == 0:
        # A revert still consumed the nonce — terminal, same as success.
        nonce_mgr.mark_confirmed(nonce)
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

    nonce_mgr.mark_confirmed(nonce)

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
    """Decode one event type from a receipt, e.g.
    ``registry.events.ModelRegistrationRequested()``.

    Wraps web3's ``process_receipt`` over the retained raw receipt, then
    normalizes the result so callers get plain JSON-safe dicts rather than
    AttributeDict/HexBytes. Without that, the future operations layer would hit
    exactly the serialization failure TxReceiptInfo.logs already guards against
    (M6).
    """
    decoded = contract_event.process_receipt(receipt_info._raw)
    return [_normalize_log(entry) for entry in decoded]
