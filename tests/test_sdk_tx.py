"""Tests for dincli.sdk.tx — send()/decode_events() + NonceManager."""
import json
import threading
import time
from dataclasses import asdict
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from eth_account import Account
from web3.datastructures import AttributeDict
from web3.exceptions import TimeExhausted, TransactionNotFound

from dincli.sdk import tx as sdk_tx
from dincli.sdk.tx import (
    NonceManager,
    TxReceiptInfo,
    build_tx_params,
    decode_events,
    send,
)
from dincli.sdk.session import DinSession
from dincli.sdk.errors import (
    TransactionError,
    SignerUnavailable,
    TX_ESTIMATION_FAILED,
    TX_NONCE_CONFLICT,
    TX_REPLACEMENT_UNDERPRICED,
    TX_REVERTED,
    TX_TIMEOUT,
    RECEIPT_MISSING,
    NONCE_MANAGER_CAPACITY,
)

DUMMY_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"
DUMMY_ADDR = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(w3=None, address=DUMMY_ADDR, network="local"):
    """Build a DinSession with minimal mocking so send() works."""
    session = MagicMock(spec=DinSession)
    session.w3 = w3 or MagicMock()
    session.address = address
    session.network = network
    # send() signs via the SignerProvider protocol; give it a realistic
    # SignedTransaction so tx_hash is a real 0x string, not a MagicMock.
    signed = MagicMock()
    signed.hash.hex.return_value = "de" * 32
    signed.raw_transaction = b"\xde\xad"
    session.signer.sign_transaction.return_value = signed
    session.account = MagicMock()
    session.account.sign_transaction.return_value = signed
    return session


def _make_mock_receipt(tx_hash=None, status=1, block_number=12345,
                        gas_used=21000, contract_address=None, logs=None):
    if tx_hash is None:
        tx_hash = b"\xde\xad\xbe\xef" * 8  # 32 bytes
    resolved_hash = tx_hash if isinstance(tx_hash, bytes) else hex_to_bytes(tx_hash)
    return AttributeDict({
        "transactionHash": resolved_hash,
        "status": status,
        "blockNumber": block_number,
        "gasUsed": gas_used,
        "contractAddress": contract_address,
        "logs": logs or [],
    })


def hex_to_bytes(h: str) -> bytes:
    return bytes.fromhex(h.replace("0x", ""))


def _w3_mock(chain_id=1337, gas_price=10_000_000_000, max_priority_fee=1_000_000_000,
             pending_nonce=5):
    w3 = MagicMock()
    w3.eth.chain_id = chain_id
    w3.eth.gas_price = gas_price
    w3.eth.max_priority_fee = max_priority_fee
    w3.eth.get_transaction_count.return_value = pending_nonce
    w3.eth.estimate_gas.return_value = 100_000
    w3.to_checksum_address = lambda a: a
    return w3


# ---------------------------------------------------------------------------
# TxReceiptInfo
# ---------------------------------------------------------------------------


class TestTxReceiptInfo:
    def test_fields_from_receipt(self):
        receipt = _make_mock_receipt(status=1, tx_hash="0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd")
        info = TxReceiptInfo.from_receipt(receipt, nonce=5)
        assert info.status == 1
        assert info.block_number == 12345
        assert info.gas_used == 21000
        assert info.tx_hash == "0xabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcdabcd"

    def test_contract_address_present(self):
        receipt = _make_mock_receipt(contract_address="0xdef")
        info = TxReceiptInfo.from_receipt(receipt, nonce=5)
        assert info.contract_address == "0xdef"

    def test_logs_normalized(self):
        receipt = _make_mock_receipt(logs=[
            AttributeDict({
                "address": "0xlog",
                "data": b"\x00\x01",
                "topics": [b"\xff" * 32],
            })
        ])
        info = TxReceiptInfo.from_receipt(receipt, nonce=5)
        assert len(info.logs) == 1
        log = info.logs[0]
        assert log["address"] == "0xlog"
        assert log["data"] == "0x0001"
        assert isinstance(log["topics"][0], str) and log["topics"][0].startswith("0x")

    def test_json_dumps_no_raw(self):
        """_raw is omitted from JSON serialization — no AttributeDict/HexBytes leak."""
        receipt = _make_mock_receipt(logs=[AttributeDict({
            "address": "0xlog",
            "data": b"\x00\x01",
            "topics": [b"\xff" * 32],
        })])
        info = TxReceiptInfo.from_receipt(receipt, nonce=5)
        d = {f.name: getattr(info, f.name)
             for f in info.__dataclass_fields__.values()
             if f.metadata.get("json") != "omit"}
        assert "_raw" not in d
        assert "nonce" in d
        assert "logs" in d
        payload = json.dumps(d, default=str)
        assert "0x0001" in payload


# ---------------------------------------------------------------------------
# NonceManager
# ---------------------------------------------------------------------------


class TestNonceManager:
    def setup_method(self):
        # Clean-slate: a leaked reservation/inflight nonce from an earlier
        # class fails this loudly instead of silently corrupting this test.
        # No teardown here — every test either constructs its own
        # NonceManager directly (bypassing the shared cache) or, in
        # test_for_session_singleton, leaves only an idle cached instance.
        NonceManager.reset_all()

    def test_reserve_returns_pending_nonce(self):
        w3 = _w3_mock(pending_nonce=7)
        mgr = NonceManager(1, "0xaaa")
        assert mgr.reserve(w3) == 7

    def test_reserve_skips_reserved(self):
        w3 = _w3_mock(pending_nonce=5)
        mgr = NonceManager(1, "0xaaa")
        mgr._reserved[5] = time.monotonic()
        assert mgr.reserve(w3) == 6

    def test_reserve_skips_inflight(self):
        w3 = _w3_mock(pending_nonce=5)
        mgr = NonceManager(1, "0xaaa")
        mgr._inflight.add(5)
        assert mgr.reserve(w3) == 6

    def test_distinctness_concurrent(self):
        """N threads calling reserve() against a frozen chain_pending get N distinct nonces."""
        w3 = _w3_mock(pending_nonce=10)
        mgr = NonceManager(1, "0xaaa")
        results = []

        def worker():
            n = mgr.reserve(w3)
            results.append(n)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 20

    def test_gap_refill(self, monkeypatch):
        """Reserve, abandon, advance clock past TTL → same nonce reused."""
        w3 = _w3_mock(pending_nonce=10)
        mgr = NonceManager(1, "0xaaa")
        n1 = mgr.reserve(w3)  # should be 10
        mgr.release(n1)
        # advance clock past TTL
        monkeypatch.setattr(sdk_tx, "_RESERVATION_TTL_S", 0.0)
        monkeypatch.setattr(mgr, "_now", lambda: time.monotonic() + 999)
        n2 = mgr.reserve(w3)
        assert n2 == n1

    def test_release_reclaims_immediately(self):
        w3 = _w3_mock(pending_nonce=5)
        mgr = NonceManager(1, "0xaaa")
        n1 = mgr.reserve(w3)
        assert n1 == 5
        mgr.release(5)
        n2 = mgr.reserve(w3)
        assert n2 == 5  # reclaimed immediately

    def test_prune_drops_confirmed(self):
        w3 = _w3_mock(pending_nonce=10)
        mgr = NonceManager(1, "0xaaa")
        mgr._reserved[5] = time.monotonic()
        mgr._inflight.add(6)
        mgr.prune(w3)  # base=10, drops 5 and 6
        assert 5 not in mgr._reserved
        assert 6 not in mgr._inflight

    def test_prune_drops_expired_reservations(self, monkeypatch):
        w3 = _w3_mock(pending_nonce=3)
        mgr = NonceManager(1, "0xaaa")
        monkeypatch.setattr(sdk_tx, "_RESERVATION_TTL_S", 0.0)
        mgr._reserved[10] = time.monotonic() - 999
        mgr.prune(w3)
        assert 10 not in mgr._reserved

    def test_mark_broadcast_moves_to_inflight(self):
        w3 = _w3_mock(pending_nonce=5)
        mgr = NonceManager(1, "0xaaa")
        mgr._reserved[5] = time.monotonic()
        mgr.mark_broadcast(5)
        assert 5 not in mgr._reserved
        assert 5 in mgr._inflight

    def test_inflight_not_expirable(self, monkeypatch):
        """inflight entries should never TTL-expire (only reserved)."""
        w3 = _w3_mock(pending_nonce=3)
        mgr = NonceManager(1, "0xaaa")
        monkeypatch.setattr(sdk_tx, "_RESERVATION_TTL_S", 0.0)
        mgr._inflight.add(10)
        mgr._reserved[11] = time.monotonic() - 999
        mgr.prune(w3)
        assert 10 in mgr._inflight  # inflight survives
        assert 11 not in mgr._reserved  # expired reserved dropped

    def test_resync_clears_all(self):
        mgr = NonceManager(1, "0xaaa")
        mgr._reserved[1] = time.monotonic()
        mgr._inflight.add(2)
        w3 = MagicMock()
        mgr.resync(w3)
        assert mgr._reserved == {}
        assert mgr._inflight == set()

    def test_for_session_singleton(self):
        session = _make_mock_session(w3=_w3_mock())
        mgr1 = NonceManager.for_session(session)
        mgr2 = NonceManager.for_session(session)
        assert mgr1 is mgr2


# ---------------------------------------------------------------------------
# build_tx_params
# ---------------------------------------------------------------------------


class TestBuildTxParams:
    def setup_method(self):
        # Clean-slate: see NonceManager.reset_all() docstring for the convention.
        NonceManager.reset_all()

    def teardown_method(self):
        # test_basic_params / test_override_gas reserve a nonce via
        # build_tx_params and never settle it; confine that to this class.
        NonceManager.reset_all(force=True)

    def test_basic_params(self):
        w3 = _w3_mock(pending_nonce=3)
        session = _make_mock_session(w3=w3)
        params = build_tx_params(session)
        assert params["from"] == DUMMY_ADDR
        assert params["chainId"] == 1337
        assert params["nonce"] == 3

    def test_override_nonce(self):
        w3 = _w3_mock(pending_nonce=3)
        session = _make_mock_session(w3=w3)
        params = build_tx_params(session, overrides={"nonce": 42})
        assert params["nonce"] == 42

    def test_override_gas(self):
        w3 = _w3_mock(pending_nonce=3)
        session = _make_mock_session(w3=w3)
        params = build_tx_params(session, overrides={"maxFeePerGas": 500})
        assert params["maxFeePerGas"] == 500
        assert params["nonce"] == 3


# ---------------------------------------------------------------------------
# send() happy path
# ---------------------------------------------------------------------------


class TestSendHappyPath:
    def setup_method(self):
        # Clean-slate: see NonceManager.reset_all() docstring for the
        # convention. No teardown here — every test in this class settles
        # its own nonce (mark_confirmed), so the plain setup_method above
        # doubles as a live check that this class cleans up after itself.
        NonceManager.reset_all()

    def test_successful_send(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt()
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction_receipt.return_value = receipt
        w3.eth.wait_for_transaction_receipt.return_value = receipt

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )

        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        info = send(session, contract_fn)
        assert info.status == 1
        assert info.block_number == 12345

    def test_on_event_sequence(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt()
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction_receipt.return_value = receipt
        w3.eth.wait_for_transaction_receipt.return_value = receipt

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        events = []

        def collector(name, payload):
            events.append(name)

        send(session, contract_fn, on_event=collector)
        assert events == ["broadcasting", "submitted", "confirmed"]

    def test_on_event_exception_does_not_break_send(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt()
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction_receipt.return_value = receipt
        w3.eth.wait_for_transaction_receipt.return_value = receipt

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        def buggy(name, payload):
            raise RuntimeError("callback bug")

        info = send(session, contract_fn, on_event=buggy)
        assert info.status == 1


# ---------------------------------------------------------------------------
# send() failure paths — §3d subcodes
# ---------------------------------------------------------------------------


class TestSendFailurePaths:
    def setup_method(self):
        # Clean-slate: see NonceManager.reset_all() docstring for the convention.
        NonceManager.reset_all()

    def teardown_method(self):
        # test_already_known_broadcast_true / test_timeout deliberately end
        # inflight; confine that known-busy state to this class.
        NonceManager.reset_all(force=True)

    def test_estimation_failed(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.estimate_gas.side_effect = ValueError("out of gas")

        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_ESTIMATION_FAILED
        assert exc.value.details["broadcast"] is False

    def test_nonce_too_low(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.side_effect = ValueError("nonce too low")

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_NONCE_CONFLICT
        assert exc.value.details["broadcast"] is False
        assert "tx_hash" in exc.value.details

    def test_already_known_broadcast_true(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.side_effect = ValueError("already known")

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_NONCE_CONFLICT
        assert exc.value.details["broadcast"] is True
        assert "tx_hash" in exc.value.details

    def test_replacement_underpriced(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.side_effect = ValueError(
            "replacement transaction underpriced"
        )

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_REPLACEMENT_UNDERPRICED
        assert exc.value.details["broadcast"] is False

    def test_timeout(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction_receipt.side_effect = TransactionNotFound('unmined')
        w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted('timed out')
        w3.eth.get_transaction.return_value = {'hash': b'\xab\xcd'}  # still pending

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn, timeout_s=0.001)
        assert exc.value.code == TX_TIMEOUT
        assert exc.value.details["broadcast"] is True
        assert "tx_hash" in exc.value.details

    def test_reverted(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt(status=0)
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction_receipt.return_value = receipt
        w3.eth.wait_for_transaction_receipt.return_value = receipt

        session = _make_mock_session(w3=w3)
        session.account.sign_transaction.return_value = MagicMock(
            hash=b"\xab\xcd", raw_transaction=b"\xde\xad"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_REVERTED
        assert exc.value.details["broadcast"] is True
        assert "block_number" in exc.value.details


# ---------------------------------------------------------------------------
# send-eth nonce path (BL-1 fix reaches send-eth via get_tx_params)
# ---------------------------------------------------------------------------


class TestSendEthNoncePath:
    def setup_method(self):
        # Clean-slate: see NonceManager.reset_all() docstring for the convention.
        NonceManager.reset_all()

    def teardown_method(self):
        # test_build_tx_params_uses_nonce_manager reserves without settling.
        NonceManager.reset_all(force=True)

    def test_build_tx_params_uses_nonce_manager(self):
        """BL-1: get_tx_params allocates through NonceManager (not bare get_transaction_count)."""
        NonceManager.reset_all()
        w3 = _w3_mock(pending_nonce=11)
        session = _make_mock_session(w3=w3)
        params = build_tx_params(session)
        assert params["nonce"] == 11
        w3.eth.get_transaction_count.assert_called()  # used pending

    def test_release_reclaims_nonce(self):
        NonceManager.reset_all()
        w3 = _w3_mock(pending_nonce=5)
        session = _make_mock_session(w3=w3)
        mgr = NonceManager.for_session(session)
        n = mgr.reserve(w3)
        assert n == 5
        mgr.release(5)
        assert mgr.reserve(w3) == 5


# ---------------------------------------------------------------------------
# decode_events
# ---------------------------------------------------------------------------


class TestDecodeEvents:
    def test_decode_delegates(self):
        receipt = _make_mock_receipt()
        info = TxReceiptInfo.from_receipt(receipt, nonce=5)
        contract_event = MagicMock()
        contract_event.process_receipt.return_value = [{"event": "Test"}]

        result = decode_events(info, contract_event)
        assert result == [{"event": "Test"}]
        contract_event.process_receipt.assert_called_once_with(info._raw)


# ---------------------------------------------------------------------------
# NonceManager bound: cap, LRU, idle-only eviction (BL-22)
# ---------------------------------------------------------------------------


def _session_with_key(chain_id, address):
    """A minimal object with the only two attrs for_session() reads."""
    session = MagicMock(spec=DinSession)
    session.w3 = MagicMock()
    session.w3.eth.chain_id = chain_id
    session.address = address
    return session


class TestNonceManagerBound:
    def setup_method(self):
        NonceManager.reset_all()

    def teardown_method(self):
        NonceManager.reset_all(force=True)

    def _fill(self, n, chain_id=1337):
        keys = []
        for i in range(n):
            address = f"0x{i:040x}"
            NonceManager.for_session(_session_with_key(chain_id, address))
            keys.append((chain_id, address))
        return keys

    def test_cache_bounded_and_keeps_most_recent(self):
        cap = NonceManager._MAX_INSTANCES
        keys = self._fill(cap + 6)
        assert len(NonceManager._instances) == cap
        for key in keys[-cap:]:
            assert key in NonceManager._instances
        for key in keys[:6]:
            assert key not in NonceManager._instances

    def test_touching_old_key_keeps_it_alive(self):
        cap = NonceManager._MAX_INSTANCES
        keys = self._fill(cap)
        # Touch the oldest key so it is no longer the LRU entry.
        NonceManager.for_session(_session_with_key(1337, keys[0][1]))
        new_key = (1337, "0x" + "ff" * 20)
        NonceManager.for_session(_session_with_key(*new_key))
        assert keys[0] in NonceManager._instances
        assert keys[1] not in NonceManager._instances
        assert new_key in NonceManager._instances

    def test_busy_lru_survives_newer_idle_dropped(self):
        cap = NonceManager._MAX_INSTANCES
        keys = self._fill(cap)
        busy = NonceManager._instances[keys[0]]
        busy.mark_broadcast(123)  # busy manager at the LRU end
        new_key = (1337, "0x" + "ab" * 20)
        NonceManager.for_session(_session_with_key(*new_key))
        assert keys[0] in NonceManager._instances
        assert busy is NonceManager._instances[keys[0]]
        assert 123 in busy._inflight
        assert keys[1] not in NonceManager._instances
        assert new_key in NonceManager._instances

    def test_all_busy_raises_capacity_and_leaves_cache_unchanged(self):
        cap = NonceManager._MAX_INSTANCES
        keys = self._fill(cap)
        for key in keys:
            NonceManager._instances[key].mark_broadcast(1)
        before = list(NonceManager._instances.keys())
        with pytest.raises(TransactionError) as exc:
            NonceManager.for_session(_session_with_key(1337, "0x" + "cd" * 20))
        assert exc.value.code == NONCE_MANAGER_CAPACITY
        assert list(NonceManager._instances.keys()) == before
        assert all(1 in NonceManager._instances[k]._inflight for k in keys)
        assert exc.value.details["limit"] == cap
        assert exc.value.details["busy"] == cap

    def test_idle_but_held_manager_survives_eviction_pressure(self):
        """Regression for the independent review's finding 1: a manager
        returned to a caller who has not yet reserved anything is idle, and
        idle managers are exactly what ``_evict_lru_idle`` reclaims. Without
        the ``_live`` weak registry, evicting it from ``_instances`` while
        the caller still holds it let a second ``for_session()`` call build
        an independent manager for the same account — both would then
        allocate nonce 0.
        """
        cap = NonceManager._MAX_INSTANCES
        session = _session_with_key(1337, "0x" + "aa" * 20)
        held = NonceManager.for_session(session)  # idle: no reserve() yet

        # Enough other accounts to push `held`'s key past the LRU cap.
        self._fill(cap, chain_id=9999)

        recovered = NonceManager.for_session(session)
        assert held is recovered, (
            "for_session() returned a different NonceManager for the same "
            "(chain_id, address) after eviction pressure — duplicate "
            "allocator hazard is back."
        )

        # And the shared identity actually prevents the duplicate-nonce bug:
        # two "handles" to the same account now hand out distinct nonces
        # rather than both returning 0.
        session.w3.eth.get_transaction_count.return_value = 0
        n1 = held.reserve(session.w3)
        n2 = recovered.reserve(session.w3)
        assert n1 != n2
        assert {n1, n2} == {0, 1}

    def test_strong_cache_still_respects_cap_with_live_lookups(self):
        """The weak registry restores identity but must not defeat the
        memory bound: the strong ``_instances`` cache stays at or under
        ``_MAX_INSTANCES`` even when idle-but-held managers keep getting
        looked up and re-admitted via ``_live``.
        """
        cap = NonceManager._MAX_INSTANCES
        session = _session_with_key(1337, "0x" + "aa" * 20)
        NonceManager.for_session(session)
        self._fill(cap, chain_id=9999)
        assert len(NonceManager._instances) <= cap
        NonceManager.for_session(session)  # re-admit via _live
        assert len(NonceManager._instances) <= cap

    def test_successful_send_leaves_manager_idle(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt()
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.wait_for_transaction_receipt.return_value = receipt
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        send(session, contract_fn)

        mgr = NonceManager.for_session(session)
        assert mgr._inflight == set()
        assert mgr._reserved == {}
        assert mgr._is_idle_nonblocking()

    def test_reverted_send_leaves_manager_idle(self):
        w3 = _w3_mock(pending_nonce=0)
        receipt = _make_mock_receipt(status=0)
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.wait_for_transaction_receipt.return_value = receipt
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_REVERTED

        mgr = NonceManager.for_session(session)
        assert mgr._inflight == set()
        assert mgr._is_idle_nonblocking()

    def test_timeout_leaves_nonce_inflight(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.get_transaction.return_value = {"hash": b"\xab\xcd"}
        w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted("timed out")
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn, timeout_s=0.001)
        assert exc.value.code == TX_TIMEOUT
        assert 0 in NonceManager.for_session(session)._inflight

    def test_missing_receipt_leaves_nonce_inflight(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.return_value = b"\xde\xad"
        w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted("timed out")
        w3.eth.get_transaction.side_effect = TransactionNotFound("gone")
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn, timeout_s=0.001)
        assert exc.value.code == RECEIPT_MISSING
        assert 0 in NonceManager.for_session(session)._inflight

    def test_already_known_leaves_nonce_inflight(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.side_effect = ValueError("already known")
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == TX_NONCE_CONFLICT
        assert 0 in NonceManager.for_session(session)._inflight

    def test_unclassified_broadcast_leaves_nonce_inflight(self):
        w3 = _w3_mock(pending_nonce=0)
        w3.eth.send_raw_transaction.side_effect = ConnectionError("socket hung up")
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == "tx_failed"
        assert 0 in NonceManager.for_session(session)._inflight

    def test_build_transaction_failure_releases_reservation(self):
        w3 = _w3_mock(pending_nonce=0)
        session = _make_mock_session(w3=w3)
        contract_fn = MagicMock()
        # First call (gas estimation) succeeds; second (post-gas build) fails.
        contract_fn.build_transaction.side_effect = [{}, ValueError("abi encode failed")]

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == "tx_failed"
        assert exc.value.details["broadcast"] is False
        assert exc.value.details["nonce"] == 0
        assert NonceManager.for_session(session)._reserved == {}

    def test_sign_transaction_failure_releases_reservation(self):
        w3 = _w3_mock(pending_nonce=0)
        session = _make_mock_session(w3=w3)
        session.signer.sign_transaction.side_effect = ValueError("signer boom")
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(TransactionError) as exc:
            send(session, contract_fn)
        assert exc.value.code == "tx_failed"
        assert exc.value.details["broadcast"] is False
        assert NonceManager.for_session(session)._reserved == {}

    def test_signer_unavailable_propagates_unrecoded(self):
        """A DinError raised by the signer (e.g. a daemon signing without a
        cached password) must surface with its own stable code, not be
        re-coded as tx_failed — the daemon retry policy keys off it."""
        w3 = _w3_mock(pending_nonce=0)
        session = _make_mock_session(w3=w3)
        session.signer.sign_transaction.side_effect = SignerUnavailable(
            "no password available"
        )
        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {}

        with pytest.raises(SignerUnavailable) as exc:
            send(session, contract_fn)
        assert exc.value.code == "signer_unavailable"
        assert NonceManager.for_session(session)._reserved == {}

    def test_busy_probe_does_not_block_on_held_mutex(self):
        cap = NonceManager._MAX_INSTANCES
        keys = self._fill(cap)
        busy = NonceManager._instances[keys[0]]
        entered = threading.Event()
        release_evt = threading.Event()

        def hold_mutex():
            with busy._mutex:
                entered.set()
                release_evt.wait(5)

        holder = threading.Thread(target=hold_mutex)
        holder.start()
        try:
            assert entered.wait(5)
            result = {}

            def insert():
                result["mgr"] = NonceManager.for_session(
                    _session_with_key(1337, "0x" + "ef" * 20)
                )

            inserter = threading.Thread(target=insert)
            inserter.start()
            inserter.join(timeout=5)
            assert not inserter.is_alive(), (
                "for_session() blocked on a manager mutex held inside reserve()"
            )
            assert "mgr" in result
            # The busy LRU manager is skipped, not evicted or waited on.
            assert keys[0] in NonceManager._instances
            assert busy is NonceManager._instances[keys[0]]
        finally:
            release_evt.set()
            holder.join(timeout=5)

    def test_reset_all_clears_idle_cache(self):
        NonceManager.for_session(_session_with_key(1337, "0x" + "01" * 20))
        NonceManager.reset_all()
        assert NonceManager._instances == {}

    def test_reset_all_refuses_when_busy(self):
        mgr = NonceManager.for_session(_session_with_key(1337, "0x" + "02" * 20))
        mgr.mark_broadcast(7)
        with pytest.raises(RuntimeError):
            NonceManager.reset_all()
        assert len(NonceManager._instances) == 1

    def test_reset_all_force_discards_busy(self):
        mgr = NonceManager.for_session(_session_with_key(1337, "0x" + "03" * 20))
        mgr.mark_broadcast(7)
        NonceManager.reset_all(force=True)
        assert NonceManager._instances == {}
