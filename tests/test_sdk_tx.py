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
    TX_ESTIMATION_FAILED,
    TX_NONCE_CONFLICT,
    TX_REPLACEMENT_UNDERPRICED,
    TX_REVERTED,
    TX_TIMEOUT,
    RECEIPT_MISSING,
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
        NonceManager._instances.clear()

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
        NonceManager._instances.clear()

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
        NonceManager._instances.clear()

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
        NonceManager._instances.clear()

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
        NonceManager._instances.clear()

    def test_build_tx_params_uses_nonce_manager(self):
        """BL-1: get_tx_params allocates through NonceManager (not bare get_transaction_count)."""
        NonceManager._instances.clear()
        w3 = _w3_mock(pending_nonce=11)
        session = _make_mock_session(w3=w3)
        params = build_tx_params(session)
        assert params["nonce"] == 11
        w3.eth.get_transaction_count.assert_called()  # used pending

    def test_release_reclaims_nonce(self):
        NonceManager._instances.clear()
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
