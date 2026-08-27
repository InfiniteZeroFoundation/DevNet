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


def test_validate_health_port_rejects_zero():
    import pytest
    with pytest.raises(ValueError, match="1-65535"):
        dconf.validate_health_port(0)


def test_validate_health_port_rejects_too_high():
    import pytest
    with pytest.raises(ValueError, match="1-65535"):
        dconf.validate_health_port(99999)
