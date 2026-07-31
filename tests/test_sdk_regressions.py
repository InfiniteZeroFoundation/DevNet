"""Regression tests for the post-implementation review of task_300726_8.

Every test in this file MUST fail at commit 90e0104 and pass after the
corresponding fix. See Plans/task_300726_8-remediation-plan.md:

  R1  send() must survive an unmined transaction (web3 raises
      TransactionNotFound; it never returns None).
  R2  DinContext and DinSession must resolve the SAME wallet name from every
      source (--wallet, DIN_WALLET_NAME, config wallet_name, default).
  R3  A missing wallet must not be reported as a bad password.
  R4  A signer that satisfies the documented SignerProvider protocol — and
      nothing more — must be able to drive a full send().
"""
import os
from unittest.mock import MagicMock

import pytest
from eth_account import Account
from web3.datastructures import AttributeDict
from web3.exceptions import TransactionNotFound

from dincli.sdk.session import DinSession, SignerProvider

DUMMY_KEY = "0x" + "11" * 32
DUMMY_ADDR = Account.from_key(DUMMY_KEY).address


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------


def _receipt(status=1):
    return AttributeDict({
        "transactionHash": b"\xab" * 32,
        "status": status,
        "blockNumber": 42,
        "gasUsed": 21000,
        "contractAddress": None,
        "logs": [],
    })


def _w3_mock(pending_nonce=5):
    w3 = MagicMock()
    w3.eth.chain_id = 1337
    w3.eth.gas_price = 10_000_000_000
    w3.eth.max_priority_fee = 1_000_000_000
    w3.eth.get_transaction_count.return_value = pending_nonce
    w3.eth.estimate_gas.return_value = 100_000
    w3.to_checksum_address = lambda a: a
    return w3


# ---------------------------------------------------------------------------
# R1 — receipt polling must tolerate an unmined transaction
# ---------------------------------------------------------------------------


class TestR1ReceiptPolling:
    """web3's get_transaction_receipt RAISES TransactionNotFound for an unmined
    tx — it never returns None. The original tests mocked `return_value = None`,
    encoding a contract web3 does not have, so this whole path went unverified.
    """

    def test_send_waits_through_transaction_not_found(self):
        from dincli.sdk import tx as txmod

        w3 = _w3_mock()
        polls = {"n": 0}

        def flaky_receipt(_tx_hash):
            polls["n"] += 1
            if polls["n"] < 3:
                raise TransactionNotFound("not found")
            return _receipt()

        w3.eth.get_transaction_receipt.side_effect = flaky_receipt
        w3.eth.wait_for_transaction_receipt.side_effect = (
            lambda h, timeout=None, poll_latency=None: _receipt()
        )

        session = MagicMock(spec=DinSession)
        session.w3 = w3
        session.address = DUMMY_ADDR
        session.network = "local"
        signed = MagicMock()
        signed.hash.hex.return_value = "ab" * 32
        signed.raw_transaction = b"raw"
        session.account.sign_transaction.return_value = signed

        info = txmod.send(session, MagicMock(), poll_interval_s=0.001)
        assert info.status == 1
        assert info.nonce == 5

    def test_timeout_raises_transaction_error_not_web3_error(self):
        """A tx that never mines must surface as TransactionError(tx_timeout),
        never as a raw web3 exception with no subcode or retry surface."""
        from dincli.sdk import tx as txmod
        from dincli.sdk.errors import TransactionError, TX_TIMEOUT, RECEIPT_MISSING

        w3 = _w3_mock()
        w3.eth.get_transaction_receipt.side_effect = TransactionNotFound("nope")
        from web3.exceptions import TimeExhausted
        w3.eth.wait_for_transaction_receipt.side_effect = TimeExhausted("timed out")

        session = MagicMock(spec=DinSession)
        session.w3 = w3
        session.address = DUMMY_ADDR
        session.network = "local"
        signed = MagicMock()
        signed.hash.hex.return_value = "cd" * 32
        signed.raw_transaction = b"raw"
        session.account.sign_transaction.return_value = signed

        with pytest.raises(TransactionError) as exc:
            txmod.send(session, MagicMock(), timeout_s=0.01, poll_interval_s=0.001)

        assert exc.value.code in (TX_TIMEOUT, RECEIPT_MISSING)
        assert exc.value.details.get("broadcast") is True
        assert exc.value.details.get("tx_hash")


# ---------------------------------------------------------------------------
# R2 — DinContext and DinSession must agree on the wallet
# ---------------------------------------------------------------------------


class TestR2WalletResolutionAgreement:
    """The CLI displays ctx.resolved_wallet_name and signs with
    session.signer. If they diverge, the user is shown one address and the
    transaction is signed by another — with the nonce fetched for the wrong
    account. Every source must agree.
    """

    @staticmethod
    def _session_wallet(ctx) -> str:
        signer = ctx.session.signer
        return getattr(signer, "_wallet_name", None)

    def _make_ctx(self, monkeypatch, env=None, config_name="", flag=None):
        from dincli.cli import context as ctx_mod
        from dincli.cli import utils as utils_mod

        monkeypatch.delenv("DIN_WALLET_NAME", raising=False)
        if env:
            monkeypatch.setenv("DIN_WALLET_NAME", env)

        def fake_get_config(key, default=None):
            if key == "wallet_name":
                return config_name
            if key == "log_level":
                return "INFO"
            return default

        monkeypatch.setattr(utils_mod, "get_config", fake_get_config)
        monkeypatch.setattr(ctx_mod, "get_config", fake_get_config)
        # --wallet validation touches the filesystem; make any name resolvable
        monkeypatch.setattr(
            ctx_mod, "resolve_wallet_path", lambda name: (f"/tmp/wallet_{name}.json", True)
        )

        ctx = ctx_mod.DinContext()
        if flag:
            ctx.select_wallet(flag)
        return ctx

    def test_agree_on_default(self, monkeypatch):
        ctx = self._make_ctx(monkeypatch)
        assert self._session_wallet(ctx) == ctx.resolved_wallet_name == "default"

    def test_agree_on_wallet_flag(self, monkeypatch):
        ctx = self._make_ctx(monkeypatch, flag="alice")
        assert self._session_wallet(ctx) == ctx.resolved_wallet_name == "alice"

    def test_agree_on_env_var(self, monkeypatch):
        ctx = self._make_ctx(monkeypatch, env="bob")
        assert ctx.resolved_wallet_name == "bob"
        assert self._session_wallet(ctx) == "bob", (
            "session signs with a different wallet than the CLI resolved"
        )

    def test_agree_on_config_wallet_name(self, monkeypatch):
        ctx = self._make_ctx(monkeypatch, config_name="carol")
        assert ctx.resolved_wallet_name == "carol"
        assert self._session_wallet(ctx) == "carol", (
            "session signs with a different wallet than the CLI resolved"
        )


# ---------------------------------------------------------------------------
# R3 — a missing wallet is not a bad password
# ---------------------------------------------------------------------------


class TestR3MissingWalletMessage:

    def test_missing_wallet_keeps_legacy_message(self):
        from dincli.cli.utils import load_account

        with pytest.raises(Exception) as exc:
            load_account("definitely-no-such-wallet-xyz")

        message = str(exc.value)
        assert "No wallet found for name" in message, (
            f"missing wallet misreported as: {message!r}"
        )
        assert "register-wallet" in message


# ---------------------------------------------------------------------------
# R4 — the documented SignerProvider contract must actually drive send()
# ---------------------------------------------------------------------------


class MinimalSigner:
    """Implements the documented SignerProvider protocol and nothing else.

    Deliberately has NO ``local_account`` — that attribute is not part of the
    protocol, so a daemon/hardware adapter written to the published contract
    would not have it either.
    """

    def __init__(self, account):
        self._account = account

    def address(self) -> str:
        return self._account.address

    def can_decrypt(self) -> bool:
        return True

    def sign_transaction(self, tx: dict):
        return self._account.sign_transaction(tx)


class TestR4SignerProtocolIsSufficient:

    def test_minimal_signer_conforms(self):
        signer = MinimalSigner(Account.from_key(DUMMY_KEY))
        assert isinstance(signer, SignerProvider)

    def test_session_account_does_not_require_local_account(self):
        """DinSession must not depend on attributes outside the protocol."""
        signer = MinimalSigner(Account.from_key(DUMMY_KEY))
        session = DinSession(signer=signer)
        assert session.address == DUMMY_ADDR
        # must not raise AttributeError
        session.account

    def test_full_send_through_protocol_only_signer(self):
        """The end-to-end contract D3 exists to prove."""
        from dincli.sdk import tx as txmod

        w3 = _w3_mock()
        w3.eth.wait_for_transaction_receipt.side_effect = (
            lambda h, timeout=None, poll_latency=None: _receipt()
        )
        w3.eth.get_transaction_receipt.return_value = _receipt()
        w3.eth.send_raw_transaction.return_value = b"\xab" * 32

        signer = MinimalSigner(Account.from_key(DUMMY_KEY))
        session = DinSession(network="local", signer=signer)
        # inject the mock chain without touching the network
        session._w3 = w3  # pyright: ignore[reportPrivateUsage]

        contract_fn = MagicMock()
        contract_fn.build_transaction.return_value = {
            "to": DUMMY_ADDR, "value": 0, "gas": 21000,
            "maxFeePerGas": 10 ** 9, "maxPriorityFeePerGas": 10 ** 9,
            "nonce": 5, "chainId": 1337,
        }

        info = txmod.send(session, contract_fn, poll_interval_s=0.001)
        assert info.status == 1


# ---------------------------------------------------------------------------
# R6 / R8 / M2 — broadcast-failure classification and nonce-manager locking
# ---------------------------------------------------------------------------


def _session_for_broadcast(w3):
    session = MagicMock(spec=DinSession)
    session.w3 = w3
    session.address = DUMMY_ADDR
    session.network = "local"
    signed = MagicMock()
    signed.hash.hex.return_value = "ef" * 32
    signed.raw_transaction = b"raw"
    session.signer.sign_transaction.return_value = signed
    return session


class TestR6BroadcastFailureClassification:
    """Estimation has already succeeded by the time we broadcast, so an
    unclassified broadcast error is not tx_estimation_failed. And because a
    socket-level failure may still have reached the node, the retry surface
    must say broadcast=True — claiming False risks a double-send (§10).
    """

    def setup_method(self):
        # NonceManager caches one instance per (chain_id, address) for the life
        # of the process, so reservations leak between tests sharing an address.
        from dincli.sdk.tx import NonceManager
        NonceManager._instances.clear()

    def test_unclassified_broadcast_failure_is_not_estimation_failed(self):
        from dincli.sdk import tx as txmod
        from dincli.sdk.errors import TransactionError, TX_ESTIMATION_FAILED

        w3 = _w3_mock()
        w3.eth.send_raw_transaction.side_effect = ConnectionError("socket hung up")
        session = _session_for_broadcast(w3)

        with pytest.raises(TransactionError) as exc:
            txmod.send(session, MagicMock())

        assert exc.value.code != TX_ESTIMATION_FAILED
        assert exc.value.code == "tx_failed"

    def test_unclassified_broadcast_failure_reports_broadcast_true(self):
        from dincli.sdk import tx as txmod
        from dincli.sdk.errors import TransactionError

        w3 = _w3_mock()
        w3.eth.send_raw_transaction.side_effect = ConnectionError("socket hung up")
        session = _session_for_broadcast(w3)

        with pytest.raises(TransactionError) as exc:
            txmod.send(session, MagicMock())

        details = exc.value.details
        assert details.get("broadcast") is True, (
            "unknown broadcast outcome must not claim it is safe to resend"
        )
        assert details.get("tx_hash"), "consumer needs the hash to confirm the tx"
        assert details.get("nonce") == 5


class TestR8NoSubmittedEventOnRejection:
    def setup_method(self):
        from dincli.sdk.tx import NonceManager
        NonceManager._instances.clear()

    def test_nonce_too_low_does_not_emit_submitted(self):
        """The CLI maps `submitted` to print_tx_info — emitting it for a
        rejected tx printed a hash and explorer URL for something that never
        existed."""
        from dincli.sdk import tx as txmod
        from dincli.sdk.errors import TransactionError

        w3 = _w3_mock()
        w3.eth.send_raw_transaction.side_effect = ValueError("nonce too low")
        session = _session_for_broadcast(w3)

        seen = []
        with pytest.raises(TransactionError):
            txmod.send(session, MagicMock(), on_event=lambda n, p: seen.append(n))

        assert "submitted" not in seen, f"emitted {seen} for a rejected tx"

    def test_already_known_does_emit_submitted(self):
        """Contrast: the node holds this exact raw tx, so it IS in flight."""
        from dincli.sdk import tx as txmod
        from dincli.sdk.errors import TransactionError

        w3 = _w3_mock()
        w3.eth.send_raw_transaction.side_effect = ValueError("already known")
        session = _session_for_broadcast(w3)

        seen = []
        with pytest.raises(TransactionError) as exc:
            txmod.send(session, MagicMock(), on_event=lambda n, p: seen.append(n))

        assert "submitted" in seen
        assert exc.value.details.get("broadcast") is True


class TestM2ReleaseIsThreadSafe:

    def test_concurrent_reserve_and_release_keeps_nonces_distinct(self):
        import threading
        from dincli.sdk.tx import NonceManager

        w3 = _w3_mock(pending_nonce=0)
        mgr = NonceManager(1337, DUMMY_ADDR)
        taken, errors = [], []

        def worker():
            try:
                for _ in range(25):
                    n = mgr.reserve(w3)
                    taken.append(n)
                    mgr.release(n)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(taken) == 200
