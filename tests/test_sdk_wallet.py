"""Tests for dincli.sdk.wallet — non-interactive keystore/account resolution."""
import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from eth_account import Account

from dincli.sdk import wallet as sdk_wallet
from dincli.sdk.errors import SignerUnavailable, WalletError

DUMMY_KEY = "0x0000000000000000000000000000000000000000000000000000000000000001"
# Derived from DUMMY_KEY via Account.from_key
DUMMY_ADDR = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
DUMMY_PW = "testpassword"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_keystore_wrapper(private_key: str, password: str, name: str = "default") -> dict:
    """Create a wallet wrapper dict matching the on-disk format."""
    acct = Account.from_key(private_key)
    ks = Account.encrypt(private_key, password)
    return {
        "version": 1,
        "address": acct.address,
        "keystore": ks,
        "source": "created",
        "name": name,
    }


def _make_demo_wallet(private_key: str) -> dict:
    """Create a demo-mode wallet dict (plaintext)."""
    acct = Account.from_key(private_key)
    return {
        "address": acct.address,
        "private_key": private_key,
        "demo_mode": True,
    }


def _write_wallet(wallet_dir: Path, name: str, data: dict):
    wallet_dir.mkdir(parents=True, exist_ok=True)
    path = wallet_dir / f"wallet_{name}.json"
    with open(path, "w") as f:
        json.dump(data, f)
    return path


# ---------------------------------------------------------------------------
# validate_account_name
# ---------------------------------------------------------------------------


class TestValidateAccountName:
    def test_valid_names(self):
        for name in ["default", "my-wallet", "wallet_1", "Abc_123-X"]:
            assert sdk_wallet.validate_account_name(name) == name

    def test_invalid_names_raise_valueerror(self):
        for name in ["", "a" * 65, "hello world", "bad/name", "bad.name"]:
            with pytest.raises(ValueError):
                sdk_wallet.validate_account_name(name)

    def test_strips_whitespace(self):
        assert sdk_wallet.validate_account_name("  my-wallet  ") == "my-wallet"


# ---------------------------------------------------------------------------
# Wallet path helpers
# ---------------------------------------------------------------------------


class TestWalletPathHelpers:
    def test_wallet_path_for_name(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        path = sdk_wallet.wallet_path_for_name("testnet")
        assert path == tmp_path / "wallet_testnet.json"

    def test_resolve_wallet_path_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        (tmp_path / "wallet_mine.json").write_text("{}")
        path, exists = sdk_wallet.resolve_wallet_path("mine")
        assert exists is True
        assert path == tmp_path / "wallet_mine.json"

    def test_resolve_wallet_path_legacy_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        legacy = tmp_path / "wallet.json"
        legacy.write_text('{"address": "0xabc"}')
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE", legacy)
        path, exists = sdk_wallet.resolve_wallet_path("default")
        assert exists is True
        assert path == legacy

    def test_resolve_wallet_path_missing(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE", tmp_path / "nonexistent.json")
        path, exists = sdk_wallet.resolve_wallet_path("nobody")
        assert exists is False
        assert path == tmp_path / "wallet_nobody.json"

    def test_ensure_wallets_dir(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path / "sub" / "wallets")
        sdk_wallet.ensure_wallets_dir()
        assert (tmp_path / "sub" / "wallets").is_dir()


# ---------------------------------------------------------------------------
# atomic_write_wallet
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_writes_and_sets_permissions(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path / "wallets")
        path = tmp_path / "wallets" / "wallet_test.json"
        data = {"address": "0xabc", "version": 1}
        sdk_wallet.atomic_write_wallet(path, data)

        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded == data
        assert not path.with_suffix(".json.tmp").exists()


# ---------------------------------------------------------------------------
# _extract_keystore
# ---------------------------------------------------------------------------


class TestExtractKeystore:
    def test_wrapper_shape(self):
        inner = {"crypto": {}, "version": 3}
        data = {"version": 1, "keystore": inner}
        assert sdk_wallet._extract_keystore(data) is inner

    def test_bare_shape(self):
        bare = {"crypto": {}, "version": 3}
        assert sdk_wallet._extract_keystore(bare) is bare

    def test_demo_wallet_raises(self):
        with pytest.raises(ValueError, match="not a recognised keystore"):
            sdk_wallet._extract_keystore({"address": "0x", "private_key": "0x"})

    def test_no_crypto_raises(self):
        with pytest.raises(ValueError, match="not a recognised keystore"):
            sdk_wallet._extract_keystore({"keystore": {"nokey": True}})


# ---------------------------------------------------------------------------
# Demo account helpers
# ---------------------------------------------------------------------------


class TestDemoAccounts:
    def test_get_demo_private_key_smoke(self, monkeypatch, tmp_path):
        accounts = {"hardhat": [{"private_key": DUMMY_KEY, "address": DUMMY_ADDR}]}
        accounts_file = tmp_path / "accounts.json"
        accounts_file.write_text(json.dumps(accounts))
        monkeypatch.setattr(sdk_wallet, "files",
                            lambda pkg: MagicMock(joinpath=lambda *a: accounts_file))
        key = sdk_wallet.get_demo_private_key(0)
        assert key == DUMMY_KEY

    def test_get_demo_account_index_smoke(self, monkeypatch, tmp_path):
        accounts = {"hardhat": [{"private_key": DUMMY_KEY, "address": DUMMY_ADDR}]}
        accounts_file = tmp_path / "accounts.json"
        accounts_file.write_text(json.dumps(accounts))
        monkeypatch.setattr(sdk_wallet, "files",
                            lambda pkg: MagicMock(joinpath=lambda *a: accounts_file))
        idx = sdk_wallet.get_demo_account_index(DUMMY_ADDR)
        assert idx == 0


# ---------------------------------------------------------------------------
# Password cache
# ---------------------------------------------------------------------------


class TestPasswordCache:
    def setup_method(self):
        sdk_wallet._clear_memory_cache()

    def teardown_method(self):
        sdk_wallet._clear_memory_cache()

    def test_cache_and_retrieve(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        sdk_wallet._cache_password_in_memory("test", "secret")
        result = sdk_wallet.resolve_password("test")
        assert result == "secret"

    def test_cache_skipped_when_env_set(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: "env_pass")
        sdk_wallet._cache_password_in_memory("test", "secret", env_pass="env_pass")
        assert "test" not in sdk_wallet._PASSWORD_CACHE

    def test_clear_by_name(self):
        sdk_wallet._cache_password_in_memory("a", "pw1")
        sdk_wallet._cache_password_in_memory("b", "pw2")
        assert sdk_wallet._clear_memory_cache("a") is True
        assert sdk_wallet._clear_memory_cache("a") is False
        assert sdk_wallet.resolve_password("b") == "pw2"

    def test_clear_all(self):
        sdk_wallet._cache_password_in_memory("a", "pw1")
        sdk_wallet._cache_password_in_memory("b", "pw2")
        sdk_wallet._clear_memory_cache()
        assert sdk_wallet.resolve_password("a") is None
        assert sdk_wallet.resolve_password("b") is None

    def test_cache_expiry(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        monkeypatch.setattr(time, "time", lambda: 1000.0)
        sdk_wallet._cache_password_in_memory("test", "secret")
        monkeypatch.setattr(time, "time", lambda: 1000.0 + 901)
        assert sdk_wallet.resolve_password("test") is None


# ---------------------------------------------------------------------------
# resolve_password
# ---------------------------------------------------------------------------


class TestResolvePassword:
    def setup_method(self):
        sdk_wallet._clear_memory_cache()

    def teardown_method(self):
        sdk_wallet._clear_memory_cache()

    def test_env_takes_priority(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: "env_val")
        sdk_wallet._cache_password_in_memory("test", "cached")
        result = sdk_wallet.resolve_password("test")
        assert result == "env_val"

    def test_cache_when_no_env(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        sdk_wallet._cache_password_in_memory("test", "cached")
        result = sdk_wallet.resolve_password("test")
        assert result == "cached"

    def test_none_when_no_sources(self, monkeypatch):
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        assert sdk_wallet.resolve_password("test") is None

    def test_injected_env_pass(self):
        assert sdk_wallet.resolve_password("test", env_pass="injected") == "injected"


# ---------------------------------------------------------------------------
# load_keystore
# ---------------------------------------------------------------------------


class TestLoadKeystore:
    def test_loads_valid_wallet(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        data = sdk_wallet.load_keystore("default")
        assert data["address"] == wrapper["address"]

    def test_missing_raises_walleterror(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        with pytest.raises(WalletError, match="No wallet found for name"):
            sdk_wallet.load_keystore("nobody")


# ---------------------------------------------------------------------------
# account_from_keystore
# ---------------------------------------------------------------------------


class TestAccountFromKeystore:
    def test_decrypts_and_returns_account(self):
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        acct = sdk_wallet.account_from_keystore(wrapper, DUMMY_PW)
        assert acct.address == DUMMY_ADDR

    def test_bad_password_raises_walleterror(self):
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        with pytest.raises(WalletError, match="Invalid password or corrupted keystore."):
            sdk_wallet.account_from_keystore(wrapper, "wrongpw")


# ---------------------------------------------------------------------------
# load_account_noninteractive
# ---------------------------------------------------------------------------


class TestLoadAccountNoninteractive:
    def setup_method(self):
        sdk_wallet._clear_memory_cache()

    def teardown_method(self):
        sdk_wallet._clear_memory_cache()

    def test_demo_mode_shortcut(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        demo = _make_demo_wallet(DUMMY_KEY)
        _write_wallet(tmp_path, "demo", demo)
        acct = sdk_wallet.load_account_noninteractive("demo")
        assert acct.address == DUMMY_ADDR

    def test_env_password(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: DUMMY_PW)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        acct = sdk_wallet.load_account_noninteractive("default")
        assert acct.address == DUMMY_ADDR

    def test_cached_password(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        sdk_wallet._cache_password_in_memory("default", DUMMY_PW)
        acct = sdk_wallet.load_account_noninteractive("default")
        assert acct.address == DUMMY_ADDR

    def test_no_password_raises_signerunavailable(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        with pytest.raises(SignerUnavailable):
            sdk_wallet.load_account_noninteractive("default")

    def test_bad_password_raises_walleterror(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: "wrongpassword")
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        with pytest.raises(WalletError, match="Invalid password or corrupted keystore."):
            sdk_wallet.load_account_noninteractive("default")

    def test_missing_wallet_raises_walleterror(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        with pytest.raises(WalletError, match="No wallet found for name"):
            sdk_wallet.load_account_noninteractive("nobody")


# ---------------------------------------------------------------------------
# SignerProvider implementations
# ---------------------------------------------------------------------------


class TestKeystoreSigner:
    def setup_method(self):
        sdk_wallet._clear_memory_cache()

    def teardown_method(self):
        sdk_wallet._clear_memory_cache()

    def test_address(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: DUMMY_PW)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        signer = sdk_wallet.KeystoreSigner("default")
        assert signer.address() == DUMMY_ADDR

    def test_can_decrypt_true(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: DUMMY_PW)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        signer = sdk_wallet.KeystoreSigner("default")
        assert signer.can_decrypt() is True

    def test_can_decrypt_false(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: None)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        signer = sdk_wallet.KeystoreSigner("default")
        assert signer.can_decrypt() is False

    def test_sign_transaction(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "WALLETS_DIR", tmp_path)
        monkeypatch.setattr(sdk_wallet, "LEGACY_WALLET_FILE",
                            tmp_path / "no_wallet.json")
        monkeypatch.setattr(sdk_wallet, "get_env_key", lambda k: DUMMY_PW)
        wrapper = _make_keystore_wrapper(DUMMY_KEY, DUMMY_PW)
        _write_wallet(tmp_path, "default", wrapper)
        signer = sdk_wallet.KeystoreSigner("default")
        tx = {"chainId": 1, "nonce": 0, "to": DUMMY_ADDR, "value": 0, "gas": 21000,
              "maxFeePerGas": 1000000000, "maxPriorityFeePerGas": 1000000000}
        signed = signer.sign_transaction(tx)
        assert signed.hash is not None  # pyright: ignore[reportAttributeAccessIssue]


class TestPrivateKeySigner:
    def test_address(self):
        signer = sdk_wallet.PrivateKeySigner(DUMMY_KEY)
        assert signer.address() == DUMMY_ADDR

    def test_can_decrypt(self):
        signer = sdk_wallet.PrivateKeySigner(DUMMY_KEY)
        assert signer.can_decrypt() is True

    def test_sign_transaction(self):
        signer = sdk_wallet.PrivateKeySigner(DUMMY_KEY)
        tx = {"chainId": 1, "nonce": 0, "to": DUMMY_ADDR, "value": 0, "gas": 21000,
              "maxFeePerGas": 1000000000, "maxPriorityFeePerGas": 1000000000}
        signed = signer.sign_transaction(tx)
        assert signed.hash is not None  # pyright: ignore[reportAttributeAccessIssue]


# ---------------------------------------------------------------------------
# Stale session cleanup
# ---------------------------------------------------------------------------


class TestStaleSession:
    def test_cleans_session_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "CONFIG_DIR", tmp_path)
        session = tmp_path / ".session"
        session.write_text("old")
        assert sdk_wallet._clean_stale_session_file() is True
        assert not session.exists()

    def test_no_session_file(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sdk_wallet, "CONFIG_DIR", tmp_path)
        assert sdk_wallet._clean_stale_session_file() is False
