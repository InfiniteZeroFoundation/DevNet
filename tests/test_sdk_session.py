"""Tests for dincli.sdk.session — DinSession + SignerProvider protocol."""
import subprocess
import sys
import textwrap
from unittest.mock import MagicMock

import pytest
from eth_account import Account

from dincli.sdk.session import DinSession, SignerProvider, _resolve_w3
from dincli.sdk.errors import NetworkError, RPC_UNREACHABLE, SignerUnavailable, WalletError
from dincli.sdk.wallet import KeystoreSigner, PrivateKeySigner

DUMMY_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"


# ---------------------------------------------------------------------------
# SignerProvider protocol conformance
# ---------------------------------------------------------------------------


class TestSignerProviderProtocol:
    def test_keystore_signer_conforms(self):
        assert isinstance(KeystoreSigner("default"), SignerProvider)

    def test_private_key_signer_conforms(self):
        assert isinstance(PrivateKeySigner(DUMMY_KEY), SignerProvider)

    def test_runtime_checkable(self):
        """A class with the right methods but no explicit inheritance passes."""
        class _Conforming:
            def address(self) -> str:
                return "0x"
            def can_decrypt(self) -> bool:
                return True
            def sign_transaction(self, tx: dict):
                return tx
        assert isinstance(_Conforming(), SignerProvider)

    def test_missing_method_fails_check(self):
        class _MissingSign:
            def address(self) -> str:
                return "0x"
            def can_decrypt(self) -> bool:
                return True
        assert not isinstance(_MissingSign(), SignerProvider)


# ---------------------------------------------------------------------------
# _resolve_w3 — NetworkError
# ---------------------------------------------------------------------------


class TestResolveW3:
    def test_raises_network_error(self, monkeypatch):
        monkeypatch.setattr(
            "dincli.sdk.web3.resolve_network_value",
            lambda *a, **kw: "http://dead:8545",
        )
        with pytest.raises(NetworkError) as exc:
            _resolve_w3("testnet")
        assert exc.value.code == RPC_UNREACHABLE
        assert exc.value.details["endpoint_host"] == "http://dead:8545"


# ---------------------------------------------------------------------------
# DinSession lazy resolution
# ---------------------------------------------------------------------------


class TestDinSessionLazy:
    def test_network_resolves_lazily(self, monkeypatch):
        monkeypatch.setattr(
            "dincli.sdk.session.resolve_network",
            lambda arg: "sepolia_op_devnet",
        )
        session = DinSession(network="sepolia_op_devnet")
        assert session.network == "sepolia_op_devnet"

    def test_config_resolves_lazily(self, monkeypatch):
        monkeypatch.setattr(
            "dincli.sdk.session.load_config",
            lambda: {"network": "local"},
        )
        session = DinSession()
        assert session.config == {"network": "local"}

    def test_no_rpc_call_until_w3_touched(self, monkeypatch):
        """Constructing a DinSession must not trigger any RPC call."""
        monkeypatch.setattr(
            "dincli.sdk.session.resolve_network",
            lambda arg: "local",
        )
        session = DinSession(network="local")
        assert session._w3 is None  # not resolved yet  # pyright: ignore[reportPrivateUsage]
        assert session.network == "local"

    def test_w3_raises_network_error_on_first_use(self, monkeypatch):
        monkeypatch.setattr(
            "dincli.sdk.session.resolve_network",
            lambda arg: "local",
        )
        monkeypatch.setattr(
            "dincli.sdk.web3.resolve_network_value",
            lambda *a, **kw: "http://dead:8545",
        )
        session = DinSession(network="local")
        with pytest.raises(NetworkError):
            _ = session.w3

    def test_address_delegates_to_signer(self, monkeypatch, tmp_path):
        from dincli.sdk import wallet as sdk_wallet
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "nonexistent.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k, **kw: "testpw")

        import json
        acct = Account.from_key(DUMMY_KEY)
        ks = Account.encrypt(DUMMY_KEY, "testpw")
        wrapper = {"version": 1, "address": acct.address, "keystore": ks, "source": "created", "name": "default"}
        tmp_path.mkdir(parents=True, exist_ok=True)
        (tmp_path / "wallet_default.json").write_text(json.dumps(wrapper))

        session = DinSession(wallet="default")
        assert session.address == acct.address


# ---------------------------------------------------------------------------
# DinSession signer injection
# ---------------------------------------------------------------------------


class TestDinSessionSignerInjection:
    def test_custom_signer(self):
        signer = PrivateKeySigner(DUMMY_KEY)
        session = DinSession(signer=signer)
        assert session.signer is signer
        assert session.address == signer.address()

    def test_default_signer_is_keystore(self, monkeypatch):
        monkeypatch.setattr(
            "dincli.sdk.session.resolve_network",
            lambda arg: "local",
        )
        session = DinSession(wallet="testwallet")
        signer = session.signer
        assert isinstance(signer, KeystoreSigner)
        assert signer._wallet_name == "testwallet"  # pyright: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# Daemon adapter reference (D3)
# ---------------------------------------------------------------------------


class TestDaemonAdapter:
    """Reference tests for the daemon SignerProvider adapter contract.

    No code edits land on ``feat/din-daemon`` — these tests are documentation
    of expected behavior only.
    """

    def test_adapter_conforms_to_protocol(self):
        """Any adapter that implements address/can_decrypt/sign_transaction passes."""

        class DaemonAdapter:
            def __init__(self, account: Account):
                self._account = account

            def address(self) -> str:
                return self._account.address

            def can_decrypt(self) -> bool:
                return True

            def sign_transaction(self, tx: dict):
                return self._account.sign_transaction(tx)

        acct = Account.from_key(DUMMY_KEY)
        adapter = DaemonAdapter(acct)
        assert isinstance(adapter, SignerProvider)
        session = DinSession(signer=adapter)
        assert session.address == acct.address

    def test_session_never_blocks_with_closed_stdin(self):
        """Constructing and resolving a DinSession should never hang even
        when stdin is closed — the non-interactive default signer raises
        SignerUnavailable rather than blocking."""
        script = textwrap.dedent("""
            from dincli.sdk.session import DinSession
            from dincli.sdk.errors import SignerUnavailable, WalletError

            import os
            os.close(0)  # close stdin

            session = DinSession(network="local")
            # Network resolution is fine — no interaction needed
            assert session.network == "local"

            try:
                _ = session.account
                print("ok")
            except (SignerUnavailable, WalletError):
                # Either no wallet file, or no password — both non-blocking
                print("ok")
            except Exception as e:
                print(f"unexpected: {type(e).__name__}: {e}")
        """)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, f"stderr={result.stderr!r}"
        assert "ok" in result.stdout
