"""Tests for dind/config.py resolver precedence."""

import os
from pathlib import Path

from dincli.dind import config as dconf


def test_state_dir_default():
    result = dconf.resolve_state_dir(None)
    assert result == dconf.DEFAULT_STATE_DIR


def test_state_dir_flag(tmp_path):
    sd = tmp_path / "custom-state"
    result = dconf.resolve_state_dir(str(sd))
    assert result == sd.resolve()


def test_state_dir_env(monkeypatch, tmp_path):
    sd = tmp_path / "env-state"
    monkeypatch.setenv("DIN_DIND_STATE_DIR", str(sd))
    result = dconf.resolve_state_dir(None)
    assert result == sd.resolve()


def test_state_dir_flag_wins_over_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DIN_DIND_STATE_DIR", "/env/path")
    result = dconf.resolve_state_dir(str(tmp_path / "flag"))
    assert result != Path("/env/path")


def test_health_host_default():
    assert dconf.resolve_health_host(None) == "127.0.0.1"


def test_health_host_flag():
    assert dconf.resolve_health_host("0.0.0.0") == "0.0.0.0"


def test_health_host_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_HEALTH_HOST", "10.0.0.1")
    assert dconf.resolve_health_host(None) == "10.0.0.1"


def test_health_port_default():
    assert dconf.resolve_health_port(None) == 8787


def test_health_port_flag():
    assert dconf.resolve_health_port(9090) == 9090


def test_health_port_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_HEALTH_PORT", "1234")
    assert dconf.resolve_health_port(None) == 1234


def test_validate_health_port_ok():
    dconf.validate_health_port(1)
    dconf.validate_health_port(65535)
    dconf.validate_health_port(8080)


def test_validate_health_port_accepts_zero():
    # 0 means "ephemeral" — accepted so two racing daemons fail on the lock,
    # not on a fixed-port bind (BL-19).
    dconf.validate_health_port(0)


def test_validate_health_port_rejects_negative():
    import pytest
    with pytest.raises(ValueError, match="0-65535"):
        dconf.validate_health_port(-1)


def test_validate_health_port_rejects_too_high():
    import pytest
    with pytest.raises(ValueError, match="0-65535"):
        dconf.validate_health_port(99999)


def test_max_ticks_default_none():
    assert dconf.resolve_max_ticks(None) is None


def test_max_ticks_flag():
    assert dconf.resolve_max_ticks(5) == 5


def test_max_ticks_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_MAX_TICKS", "3")
    assert dconf.resolve_max_ticks(None) == 3


def test_max_ticks_flag_wins_over_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_MAX_TICKS", "3")
    assert dconf.resolve_max_ticks(7) == 7


def test_log_max_bytes_default():
    assert dconf.resolve_log_max_bytes(None) == dconf.LOG_MAX_BYTES_DEFAULT


def test_log_max_bytes_flag():
    assert dconf.resolve_log_max_bytes(123) == 123


def test_log_max_bytes_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_LOG_MAX_BYTES", "999")
    assert dconf.resolve_log_max_bytes(None) == 999


def test_log_max_bytes_rejects_zero():
    import pytest
    with pytest.raises(ValueError, match="DIN_DIND_LOG_MAX_BYTES"):
        dconf.resolve_log_max_bytes(0)


def test_log_max_bytes_rejects_negative():
    import pytest
    with pytest.raises(ValueError, match="DIN_DIND_LOG_MAX_BYTES"):
        dconf.resolve_log_max_bytes(-1)


def test_log_max_bytes_env_empty_raises(monkeypatch):
    import pytest
    monkeypatch.setenv("DIN_DIND_LOG_MAX_BYTES", "")
    with pytest.raises(ValueError, match="DIN_DIND_LOG_MAX_BYTES"):
        dconf.resolve_log_max_bytes(None)


def test_log_max_bytes_env_malformed_raises(monkeypatch):
    import pytest
    monkeypatch.setenv("DIN_DIND_LOG_MAX_BYTES", "not-a-number")
    with pytest.raises(ValueError, match="DIN_DIND_LOG_MAX_BYTES"):
        dconf.resolve_log_max_bytes(None)


def test_log_backup_count_default():
    assert dconf.resolve_log_backup_count(None) == dconf.LOG_BACKUP_COUNT_DEFAULT


def test_log_backup_count_flag():
    assert dconf.resolve_log_backup_count(3) == 3


def test_log_backup_count_env(monkeypatch):
    monkeypatch.setenv("DIN_DIND_LOG_BACKUP_COUNT", "9")
    assert dconf.resolve_log_backup_count(None) == 9


def test_log_backup_count_rejects_zero():
    import pytest
    with pytest.raises(ValueError, match="DIN_DIND_LOG_BACKUP_COUNT"):
        dconf.resolve_log_backup_count(0)


def test_log_backup_count_rejects_negative():
    import pytest
    with pytest.raises(ValueError, match="DIN_DIND_LOG_BACKUP_COUNT"):
        dconf.resolve_log_backup_count(-2)


def test_log_backup_count_env_empty_raises(monkeypatch):
    import pytest
    monkeypatch.setenv("DIN_DIND_LOG_BACKUP_COUNT", "")
    with pytest.raises(ValueError, match="DIN_DIND_LOG_BACKUP_COUNT"):
        dconf.resolve_log_backup_count(None)


def test_log_backup_count_env_malformed_raises(monkeypatch):
    import pytest
    monkeypatch.setenv("DIN_DIND_LOG_BACKUP_COUNT", "not-a-number")
    with pytest.raises(ValueError, match="DIN_DIND_LOG_BACKUP_COUNT"):
        dconf.resolve_log_backup_count(None)
