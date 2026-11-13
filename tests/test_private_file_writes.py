"""Secret files (test-data K, owner and auditor X25519 keys) are owner-only
from the first byte, whatever the umask: an interrupted write must never
leave them readable by other users (task_061026_21 close-out, Discussion 231).
"""
import os
import stat
from types import SimpleNamespace

import pytest

from dincli.cli import auditor, utils
from dincli.cli.modelownerd import auditor_batches
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs


@pytest.fixture
def umask_022():
    old = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(old)


@pytest.fixture
def renamed_modes(monkeypatch):
    """Records {destination: mode of the source file} for every os.replace."""
    modes = {}
    real_replace = os.replace

    def spy(src, dst):
        modes[str(dst)] = stat.S_IMODE(os.stat(src).st_mode)
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    return modes


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_write_private_text_is_0600_before_it_is_renamed(tmp_path, umask_022, renamed_modes):
    target = tmp_path / "secret.json"

    utils.write_private_text(target, "s3cret")

    assert renamed_modes == {str(target): 0o600}
    assert _mode(target) == 0o600
    assert target.read_text() == "s3cret"
    assert not (tmp_path / "secret.json.tmp").exists()


def test_write_private_text_tightens_a_stale_temp_file_and_a_wide_target(tmp_path, umask_022, renamed_modes):
    target = tmp_path / "secret.json"
    target.write_text("old")
    target.chmod(0o644)
    stale_tmp = tmp_path / "secret.json.tmp"
    stale_tmp.write_text("leftover")
    stale_tmp.chmod(0o644)

    utils.write_private_text(target, "new")

    assert renamed_modes[str(target)] == 0o600
    assert _mode(target) == 0o600
    assert target.read_text() == "new"


def test_write_private_text_keeps_the_old_file_when_the_write_fails(tmp_path, monkeypatch):
    target = tmp_path / "secret.json"
    utils.write_private_text(target, "old")

    def boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(os, "fsync", boom)
    with pytest.raises(OSError):
        utils.write_private_text(target, "new")

    assert target.read_text() == "old"
    assert not (tmp_path / "secret.json.tmp").exists()


def test_testdata_secrets_are_written_owner_only(tmp_path, umask_022, renamed_modes):
    auditor_batches._save_testdata_secret(tmp_path, 1, 0, b"\x01" * 32, b"\x02" * 32)
    auditor_batches._stage_testdata_secret(tmp_path, 1, 0, b"\x03" * 32, b"\x02" * 32)

    confirmed = auditor_batches._testdata_secret_path(tmp_path, 1, 0)
    pending = auditor_batches._pending_testdata_secret_path(tmp_path, 1, 0)
    assert renamed_modes == {str(confirmed): 0o600, str(pending): 0o600}
    assert _mode(confirmed) == _mode(pending) == 0o600


def test_owner_x25519_key_is_generated_owner_only(tmp_path, monkeypatch, umask_022, renamed_modes):
    monkeypatch.setattr(auditor_batches, "CONFIG_DIR", str(tmp_path))

    auditor_batches._load_owner_x25519_key(SimpleNamespace(print=lambda *a, **kw: None))

    key_path = tmp_path / "owner_x25519.key"
    assert renamed_modes == {str(key_path): 0o600}
    assert _mode(key_path) == 0o600


def test_auditor_x25519_key_is_generated_owner_only(tmp_path, monkeypatch, umask_022, renamed_modes):
    monkeypatch.setattr(auditor, "CONFIG_DIR", str(tmp_path))
    record_txs(monkeypatch, auditor)
    address = "0x000000000000000000000000000000000000A11c"
    ctx = SimpleNamespace(obj=FakeCtxObj(account=address, stake=FakeContract("0x5A", getEncryptionKey=b"")))

    auditor.register_encryption_key(ctx)

    key_path = auditor._auditor_x25519_key_path(address)
    assert renamed_modes == {str(key_path): 0o600}
    assert _mode(key_path) == 0o600
