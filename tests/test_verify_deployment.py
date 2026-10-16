"""
Tests for `dincli system verify-deployment`.

Mocking pattern mirrors tests/test_dintoken.py: a DummyContextObj holds
a DummyWeb3 that returns scripted values; the command function is called
directly (not through CliRunner) so we can assert on exit codes without
subprocess overhead.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
import click
from rich.console import Console

from dincli.cli import system as system_mod
from dincli.cli.system import verify_deployment


# ── EIP-1967 slots (mirrors system.py) ──────────────────────────────────────
_IMPL_SLOT  = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc"
_ADMIN_SLOT = "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103"

# Deterministic fixture addresses
_OWNER   = "0xDe1111111111111111111111111111111111111D"
_PROXY   = "0xAaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaA"
_IMPL    = "0xBbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_ADMIN   = "0xCccccccccccccccccccccccccccccccccccccccc"
_CODE    = b"\x60\x80\x60\x40"          # minimal non-empty bytecode
_CODEHASH = "0x" + __import__("eth_utils").keccak(_CODE).hex()

# ── Minimal deployments JSON (one proxy) ────────────────────────────────────

def _one_proxy_deps(impl_addr=_IMPL, admin_addr=_ADMIN, codehash=_CODEHASH, owner=_OWNER) -> dict:
    return {
        "dinCoordinator":                "0x0000000000000000000000000000000000000000",
        "dinToken":                      "0x0000000000000000000000000000000000000000",
        "dinValidatorStake":             "0x0000000000000000000000000000000000000000",
        "dinModelRegistry":              "0x0000000000000000000000000000000000000000",
        "dinTreasury":                   _PROXY,
        "dinTreasuryImpl":               impl_addr,
        "dinTreasuryImplCodehash":       codehash,
        "proxyAdminTreasury":            admin_addr,
        "dinFeeRouter":                  "0x0000000000000000000000000000000000000000",
        "dinEmission":                   "0x0000000000000000000000000000000000000000",
        "owner":                         owner,
        "deployedAtCommit":              "abc1234",
    }


# ── Dummy web3 ───────────────────────────────────────────────────────────────

class DummyEth:
    def __init__(self, impl=_IMPL, admin=_ADMIN, code=_CODE, owner_ret=_OWNER,
                 wiring=None, slasher_authorized=True):
        self._impl  = impl
        self._admin = admin
        self._code  = code
        self._owner = owner_ret
        self._wiring = wiring or {
            "dinToken":          "0x0000000000000000000000000000000000000000",
            "dinValidatorStake": "0x0000000000000000000000000000000000000000",
            "dinModelRegistry":  "0x0000000000000000000000000000000000000000",
        }
        self._slasher_authorized = slasher_authorized

    def get_storage_at(self, addr, slot):
        if slot == _IMPL_SLOT:
            return bytes.fromhex(self._impl[2:].zfill(64))
        if slot == _ADMIN_SLOT:
            return bytes.fromhex(self._admin[2:].zfill(64))
        return b"\x00" * 32

    def get_code(self, addr):
        return self._code

    def contract(self, address, abi):
        outer = self
        class _C:
            class functions:
                @staticmethod
                def owner():
                    class _R:
                        @staticmethod
                        def call():
                            return outer._owner
                    return _R
                @staticmethod
                def dinToken():
                    class _R:
                        @staticmethod
                        def call():
                            return outer._wiring["dinToken"]
                    return _R
                @staticmethod
                def dinValidatorStake():
                    class _R:
                        @staticmethod
                        def call():
                            return outer._wiring["dinValidatorStake"]
                    return _R
                @staticmethod
                def dinModelRegistry():
                    class _R:
                        @staticmethod
                        def call():
                            return outer._wiring["dinModelRegistry"]
                    return _R
                @staticmethod
                def slasherContracts(addr):
                    class _R:
                        @staticmethod
                        def call():
                            return outer._slasher_authorized
                    return _R
        return _C


class DummyWeb3:
    def __init__(self, **kwargs):
        self.eth = DummyEth(**kwargs)

    @staticmethod
    def to_checksum_address(addr):
        from eth_utils import to_checksum_address
        return to_checksum_address(addr)


class DummyConsole:
    def __init__(self):
        self.lines = []

    def print(self, *args, **kwargs):
        self.lines.append(" ".join(str(a) for a in args))


class DummyCtxObj:
    def __init__(self, w3=None, network="local"):
        self.console = DummyConsole()
        self.w3 = w3 or DummyWeb3()
        self.network = network


def make_ctx(**kwargs) -> SimpleNamespace:
    return SimpleNamespace(obj=DummyCtxObj(**kwargs))


# ── Helpers ──────────────────────────────────────────────────────────────────

def run_cmd(tmp_path, deps: dict, w3=None, no_color=True, slashers=None):
    """Write deps to a temp file and call verify_deployment directly.
    Returns (exit_code, output_lines).  exit_code is 0 on clean completion."""
    dep_file = tmp_path / "deployments.json"
    dep_file.write_text(json.dumps(deps))
    ctx = make_ctx(w3=w3 or DummyWeb3())
    exit_code = 0
    try:
        verify_deployment(ctx, file=dep_file, no_color=no_color, slashers=slashers)
    except (SystemExit,) as exc:
        exit_code = exc.code or 0
    except (click.exceptions.Exit, typer.Exit) as exc:
        exit_code = exc.exit_code
    return exit_code, ctx.obj.console.lines


def assert_all_ok(lines):
    drifts = [l for l in lines if "[DRIFT]" in l or "[ERROR]" in l]
    assert not drifts, f"Unexpected DRIFT/ERROR lines: {drifts}"


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAllOK:
    def test_exits_zero(self, tmp_path):
        code, _lines = run_cmd(tmp_path, _one_proxy_deps())
        assert code == 0

    def test_prints_only_ok_and_info(self, tmp_path):
        _code, lines = run_cmd(tmp_path, _one_proxy_deps())
        assert_all_ok(lines)

    def test_reports_deploy_commit(self, tmp_path):
        _code, lines = run_cmd(tmp_path, _one_proxy_deps())
        assert any("abc1234" in l for l in lines)


class TestDriftOnImplMismatch:
    def test_exits_nonzero(self, tmp_path):
        wrong_impl = "0xDddddddddddddddddddddddddddddddddddddddd"
        w3 = DummyWeb3(impl=wrong_impl)
        code, _lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert code != 0

    def test_prints_drift_line(self, tmp_path):
        wrong_impl = "0xDddddddddddddddddddddddddddddddddddddddd"
        w3 = DummyWeb3(impl=wrong_impl)
        _code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert any("[DRIFT]" in l and "impl" in l for l in lines)


class TestDriftOnCodehashMismatch:
    def test_exits_nonzero(self, tmp_path):
        w3 = DummyWeb3(code=b"\xfe")    # different bytecode → different hash
        code, _lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert code != 0

    def test_prints_drift_line(self, tmp_path):
        w3 = DummyWeb3(code=b"\xfe")
        _code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert any("[DRIFT]" in l and "codehash" in l for l in lines)


class TestDriftOnAdminMismatch:
    def test_exits_nonzero(self, tmp_path):
        wrong_admin = "0xEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
        w3 = DummyWeb3(admin=wrong_admin)
        code, _lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert code != 0

    def test_prints_drift_line(self, tmp_path):
        wrong_admin = "0xEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE"
        w3 = DummyWeb3(admin=wrong_admin)
        _code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert any("[DRIFT]" in l and "proxyAdmin" in l for l in lines)


class TestDriftOnOwnerMismatch:
    def test_exits_nonzero(self, tmp_path):
        wrong_owner = "0xFfffffffffffffffffffffffffffffffFfffffff"
        w3 = DummyWeb3(owner_ret=wrong_owner)
        code, _lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert code != 0

    def test_prints_drift_line(self, tmp_path):
        wrong_owner = "0xFfffffffffffffffffffffffffffffffFfffffff"
        w3 = DummyWeb3(owner_ret=wrong_owner)
        _code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3)
        assert any("[DRIFT]" in l and "owner" in l for l in lines)


class TestSlasherCheck:
    def test_ok_when_slasher_authorized(self, tmp_path):
        slasher = "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        w3 = DummyWeb3(slasher_authorized=True)
        code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3, slashers=slasher)
        assert code == 0
        assert any("[OK]" in l and "slasher" in l for l in lines)

    def test_drift_when_slasher_not_authorized(self, tmp_path):
        slasher = "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        w3 = DummyWeb3(slasher_authorized=False)
        code, lines = run_cmd(tmp_path, _one_proxy_deps(), w3=w3, slashers=slasher)
        assert code != 0
        assert any("[DRIFT]" in l and "slasher" in l for l in lines)

    def test_info_when_no_slashers_given(self, tmp_path):
        _code, lines = run_cmd(tmp_path, _one_proxy_deps())
        assert any("[INFO]" in l and "slasher" in l for l in lines)


class TestFileHandling:
    def test_missing_file_exits_nonzero(self, tmp_path):
        ctx = make_ctx()
        exit_code = 0
        try:
            verify_deployment(ctx, file=tmp_path / "missing.json", no_color=True, slashers=None)
        except (SystemExit,) as exc:
            exit_code = exc.code or 0
        except (click.exceptions.Exit, typer.Exit) as exc:
            exit_code = exc.exit_code
        assert exit_code != 0

    def test_malformed_json_exits_nonzero(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        ctx = make_ctx()
        exit_code = 0
        try:
            verify_deployment(ctx, file=bad, no_color=True, slashers=None)
        except (SystemExit,) as exc:
            exit_code = exc.code or 0
        except (click.exceptions.Exit, typer.Exit) as exc:
            exit_code = exc.exit_code
        assert exit_code != 0
