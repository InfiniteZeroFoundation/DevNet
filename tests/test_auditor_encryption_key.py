from types import SimpleNamespace

import pytest
from nacl.public import PrivateKey

from dincli.cli import auditor
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs

AUDITOR_A = "0x000000000000000000000000000000000000A11c"
AUDITOR_B = "0x000000000000000000000000000000000000b0B0"


@pytest.fixture
def config_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(auditor, "CONFIG_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def sent(monkeypatch):
    return record_txs(monkeypatch, auditor)


def make_ctx(account, registered_key=b""):
    stake = FakeContract("0x5A", getEncryptionKey=registered_key)
    return SimpleNamespace(obj=FakeCtxObj(account=account, stake=stake))


def test_register_generates_an_owner_only_key_per_wallet(config_dir, sent):
    auditor.register_encryption_key(make_ctx(AUDITOR_A))

    key_path = auditor._auditor_x25519_key_path(AUDITOR_A)
    assert key_path.parent == config_dir
    assert key_path.stat().st_mode & 0o777 == 0o600
    pubkey = bytes(auditor._load_auditor_x25519_key(AUDITOR_A).public_key)
    assert sent == [("registerEncryptionKey", (pubkey,))]


def test_two_wallets_on_one_machine_get_different_keys(config_dir, sent):
    auditor.register_encryption_key(make_ctx(AUDITOR_A))
    auditor.register_encryption_key(make_ctx(AUDITOR_B))

    key_a = bytes(auditor._load_auditor_x25519_key(AUDITOR_A).public_key)
    key_b = bytes(auditor._load_auditor_x25519_key(AUDITOR_B).public_key)
    assert key_a != key_b
    assert sent == [("registerEncryptionKey", (key_a,)), ("registerEncryptionKey", (key_b,))]


def test_register_reuses_the_existing_key(config_dir, sent):
    auditor.register_encryption_key(make_ctx(AUDITOR_A))
    first = auditor._auditor_x25519_key_path(AUDITOR_A).read_text()

    auditor.register_encryption_key(make_ctx(AUDITOR_A))

    assert auditor._auditor_x25519_key_path(AUDITOR_A).read_text() == first
    assert sent[0] == sent[1]


def test_register_skips_the_tx_when_the_key_is_already_on_chain(config_dir, sent):
    key = PrivateKey.generate()
    auditor._auditor_x25519_key_path(AUDITOR_A).write_text(key.encode().hex())

    ctx = make_ctx(AUDITOR_A, registered_key=bytes(key.public_key))
    auditor.register_encryption_key(ctx)

    assert sent == []
    assert "already registered" in ctx.obj.console.text()


def test_load_names_the_command_when_the_key_is_missing(config_dir):
    with pytest.raises(FileNotFoundError, match="register-encryption-key"):
        auditor._load_auditor_x25519_key(AUDITOR_A)
