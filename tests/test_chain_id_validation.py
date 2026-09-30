"""Tests for RPC chain-id validation on develop (PR B).

Retargeted for the SDK extraction (issue #20): get_w3 lives in
dincli.sdk.web3, raises SDK DinError subclasses (NetworkError /
ChainIdMismatchError) with a stable ``.code`` rather than builtin
``ConnectionError`` — see §4.5/§6 of the develop-sync plan.
"""
import io
import json
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from dincli.sdk.errors import ChainIdMismatchError, NetworkError, RPC_UNREACHABLE
from dincli.sdk.manifest import load_din_info
from dincli.sdk.web3 import get_w3

SENTINEL = "SECRET123"
NETWORK = "sepolia_op_devnet"
UNPINNED = "sepolia_devnet"
VALID_CHAIN_ID = 11155420
WRONG_CHAIN_ID = 10


class _FakeEth:
    def __init__(self, getter):
        self._getter = getter
        self.chain_id_calls = 0

    @property
    def chain_id(self):
        self.chain_id_calls += 1
        return self._getter()


class _FakeWeb3:
    def __init__(self, *, connected=True, chain_id=VALID_CHAIN_ID, chain_id_raises=None):
        self._connected = connected
        self._chain_id = chain_id
        self._chain_id_raises = chain_id_raises
        self.eth = _FakeEth(self._read_chain_id)

    def _read_chain_id(self):
        if self._chain_id_raises is not None:
            raise self._chain_id_raises
        return self._chain_id

    def is_connected(self):
        return self._connected


class _DummyConsole:
    def print(self, *args, **kwargs):
        pass


def _invoke_group_with(error):
    from dincli.cli.core import GlobalOptionsGroup

    group = GlobalOptionsGroup(name="test")
    ctx = MagicMock()
    old_stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        with patch("typer.core.TyperGroup.invoke", side_effect=error):
            with pytest.raises(SystemExit) as exc_info:
                group.invoke(ctx)
    finally:
        captured = sys.stderr.getvalue()
        sys.stderr = old_stderr
    return exc_info.value.code, captured


# ---------------------------------------------------------------------------
# Stage 1 — resolve + connect
# ---------------------------------------------------------------------------

class TestStage0:
    """Resolution failures must stay distinguishable from connection failures."""

    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_unresolvable_rpc_url_propagates_its_own_error(
        self, mock_web3_cls, mock_load_info
    ):
        """A missing rpc_url is a config error, not an unreachable endpoint.

        resolve_network_value raises a KeyError naming the env var and the config
        path it checked. Wrapping that in stage 1 would tell an operator with no
        RPC configured at all that their node is unreachable -- the same class of
        misleading error this whole function exists to remove.
        """
        guidance = KeyError(
            "Could not resolve 'rpc_url' for network 'sepolia_op_devnet'.\n"
            "-> Checked .env for 'SEPOLIA_OP_DEVNET_RPC_URL'"
        )
        with patch("dincli.sdk.web3.resolve_network_value", side_effect=guidance):
            with pytest.raises(KeyError) as exc_info:
                get_w3(NETWORK)

        assert "SEPOLIA_OP_DEVNET_RPC_URL" in str(exc_info.value)
        # Never reached the transport: nothing was constructed or dialled.
        mock_web3_cls.assert_not_called()

    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_resolution_error_is_not_masked_as_connection_error(
        self, mock_web3_cls, mock_load_info
    ):
        with patch("dincli.sdk.web3.resolve_network_value", side_effect=KeyError("no rpc_url")):
            with pytest.raises(Exception) as exc_info:
                get_w3(NETWORK)

        assert not isinstance(exc_info.value, NetworkError)


class TestStage1:
    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_unreachable_raises_network_error_without_url_or_provider_text(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(connected=False)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(NetworkError) as exc_info:
            get_w3(NETWORK)

        assert exc_info.value.code == RPC_UNREACHABLE
        msg = str(exc_info.value)
        assert NETWORK in msg
        assert "Could not connect to the configured Ethereum node" in msg
        assert SENTINEL not in msg
        assert "endpoint did not respond" not in msg

    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_leaking_provider_exception_is_scrubbed(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3_cls.side_effect = Exception(
            f"request failed: https://x.invalid/v3/{SENTINEL}"
        )
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(NetworkError) as exc_info:
            get_w3(NETWORK)

        exc = exc_info.value
        assert SENTINEL not in str(exc)
        assert SENTINEL not in "".join(traceback.format_exception(exc))
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True

    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_plain_connection_failure_has_no_cause(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(connected=False)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(NetworkError) as exc_info:
            get_w3(NETWORK)

        exc = exc_info.value
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True


# ---------------------------------------------------------------------------
# Stage 2 — read chain id
# ---------------------------------------------------------------------------

class TestStage2:
    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_chain_id_read_failure_raises_stage2_network_error(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(chain_id_raises=Exception("RPC timeout"))
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(NetworkError) as exc_info:
            get_w3(NETWORK)

        assert exc_info.value.code == RPC_UNREACHABLE
        msg = str(exc_info.value)
        assert "Connected to the RPC for network" in msg
        assert "could not read its chain id" in msg
        assert not isinstance(exc_info.value, ChainIdMismatchError)

    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_leaking_chain_id_exception_is_scrubbed(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(
            chain_id_raises=Exception(f"request failed: https://x.invalid/v3/{SENTINEL}")
        )
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(NetworkError) as exc_info:
            get_w3(NETWORK)

        exc = exc_info.value
        assert SENTINEL not in str(exc)
        assert SENTINEL not in "".join(traceback.format_exception(exc))
        assert exc.__cause__ is None
        assert exc.__suppress_context__ is True


# ---------------------------------------------------------------------------
# Stage 3 — compare
# ---------------------------------------------------------------------------

class TestStage3:
    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_match_returns_web3(self, mock_web3_cls, mock_load_info, mock_resolve):
        mock_web3 = _FakeWeb3(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        result = get_w3(NETWORK)

        assert result is mock_web3
        assert mock_web3.eth.chain_id_calls == 1

    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_mismatch_raises_chain_error_naming_both_ids(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(chain_id=WRONG_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {NETWORK: {"chain_id": VALID_CHAIN_ID}}

        with pytest.raises(ChainIdMismatchError) as exc_info:
            get_w3(NETWORK)

        assert exc_info.value.code == "chain_id_mismatch"
        assert exc_info.value.details == {
            "network": NETWORK,
            "expected_chain_id": VALID_CHAIN_ID,
            "actual_chain_id": WRONG_CHAIN_ID,
        }
        msg = str(exc_info.value)
        assert NETWORK in msg
        assert str(WRONG_CHAIN_ID) in msg
        assert str(VALID_CHAIN_ID) in msg
        assert SENTINEL not in msg


# ---------------------------------------------------------------------------
# Skip when chain_id is absent
# ---------------------------------------------------------------------------

class TestSkip:
    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_absent_chain_id_never_reads_eth_chain_id(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {UNPINNED: {}}

        result = get_w3(UNPINNED)

        assert result is mock_web3
        assert mock_web3.eth.chain_id_calls == 0

    @patch("dincli.sdk.web3.resolve_network_value", return_value=SENTINEL)
    @patch("dincli.sdk.web3.load_din_info")
    @patch("dincli.sdk.web3.Web3")
    def test_absent_network_resolves_without_raising(
        self, mock_web3_cls, mock_load_info, mock_resolve
    ):
        mock_web3 = _FakeWeb3(chain_id=VALID_CHAIN_ID)
        mock_web3_cls.return_value = mock_web3
        mock_load_info.return_value = {"local": {"chain_id": 1337}}

        result = get_w3(UNPINNED)

        assert result is mock_web3
        assert mock_web3.eth.chain_id_calls == 0


# ---------------------------------------------------------------------------
# Shipped config values
# ---------------------------------------------------------------------------

class TestConfigValues:
    def test_local_chain_id_is_1337(self):
        assert load_din_info()["local"]["chain_id"] == 1337

    def test_sepolia_op_devnet_chain_id_is_11155420(self):
        assert load_din_info()["sepolia_op_devnet"]["chain_id"] == 11155420

    def test_mainnet_has_no_chain_id(self):
        assert "chain_id" not in load_din_info()["mainnet"]


# ---------------------------------------------------------------------------
# CLI boundary rendering
# ---------------------------------------------------------------------------

class TestCLIBoundary:
    def test_invoke_renders_chain_mismatch_as_one_red_line(self):
        error = ChainIdMismatchError(
            f"RPC chain mismatch for network '{NETWORK}': "
            f"the endpoint reports chain id {WRONG_CHAIN_ID}, expected {VALID_CHAIN_ID}. "
            f"Check {NETWORK.upper()}_RPC_URL in your .env — it points at a different chain."
        )
        code, captured = _invoke_group_with(error)

        assert code == 1
        assert NETWORK in captured
        assert str(WRONG_CHAIN_ID) in captured
        assert str(VALID_CHAIN_ID) in captured
        assert "Traceback" not in captured
        assert "File " not in captured
        assert captured.strip().count("\n") == 0

    def test_invoke_renders_network_error_as_one_red_line(self):
        error = NetworkError(
            f"Connected to the RPC for network '{NETWORK}', "
            "but could not read its chain id",
            code=RPC_UNREACHABLE,
        )
        code, captured = _invoke_group_with(error)

        assert code == 1
        assert NETWORK in captured
        assert "Traceback" not in captured
        assert "File " not in captured
        assert captured.strip().count("\n") == 0

    def test_invoke_still_catches_builtin_connection_error(self):
        """ConnectionError stays in the boundary tuple for compatibility (§6):
        a raw-socket ConnectionRefusedError/ConnectionResetError surfacing
        unwrapped from a dependency should still render as one red line."""
        error = ConnectionError("connection refused")
        code, captured = _invoke_group_with(error)

        assert code == 1
        assert "Traceback" not in captured

    def test_invoke_respects_din_debug_escape_hatch(self, monkeypatch):
        monkeypatch.setenv("DIN_DEBUG", "1")
        from dincli.cli.core import GlobalOptionsGroup

        group = GlobalOptionsGroup(name="test")
        ctx = MagicMock()
        error = NetworkError("boom", code=RPC_UNREACHABLE)
        with patch("typer.core.TyperGroup.invoke", side_effect=error):
            with pytest.raises(NetworkError):
                group.invoke(ctx)

    def test_invoke_truthy_din_debug_values_do_not_enable_debug(self, monkeypatch):
        """DIN_DEBUG must be exact '1', not merely truthy (§6) — '0'/'false' must
        NOT enable debug, since that is the opposite of what those values say."""
        for value in ("0", "false", "False", ""):
            monkeypatch.setenv("DIN_DEBUG", value)
            error = NetworkError("boom", code=RPC_UNREACHABLE)
            code, captured = _invoke_group_with(error)
            assert code == 1
            assert "Traceback" not in captured


# ---------------------------------------------------------------------------
# Global option parsing must keep consuming values
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_wallet_value_still_consumed(self):
        from dincli.cli.core import GlobalOptionsGroup

        group = GlobalOptionsGroup(name="test")
        captured = []
        with patch(
            "typer.core.TyperGroup.parse_args",
            side_effect=lambda ctx, args: captured.append(args),
        ):
            remaining = group.parse_args(
                MagicMock(), ["--wallet", "alice", "system", "list-accounts"]
            )

        assert remaining == ["system", "list-accounts"]
        assert captured == [["--wallet", "alice", "system", "list-accounts"]]

    def test_demokey_value_still_consumed(self):
        from dincli.cli.core import GlobalOptionsGroup

        group = GlobalOptionsGroup(name="test")
        captured = []
        with patch(
            "typer.core.TyperGroup.parse_args",
            side_effect=lambda ctx, args: captured.append(args),
        ):
            remaining = group.parse_args(
                MagicMock(), ["--demokey", "3", "system", "list-accounts"]
            )

        assert remaining == ["system", "list-accounts"]
        assert captured == [["--demokey", "3", "system", "list-accounts"]]


# ---------------------------------------------------------------------------
# import-deployments must preserve chain_id
# ---------------------------------------------------------------------------

class TestImportDeploymentsPreservesChainId:
    def test_chain_id_survives_import(self, tmp_path, monkeypatch):
        from dincli.cli import system as system_mod

        deployments = {
            "dinCoordinator": "0x" + "1" * 40,
            "dinToken": "0x" + "2" * 40,
            "dinValidatorStake": "0x" + "3" * 40,
            "dinModelRegistry": "0x" + "4" * 40,
        }
        deployments_path = tmp_path / "deployments.json"
        deployments_path.write_text(json.dumps(deployments))

        original = {
            "local": {
                "chain_id": 1337,
                "coordinator": "0xOLD",
                "token": "0xOLD",
                "stake": "0xOLD",
                "registry": "0xOLD",
                "representative": "0xREP",
            }
        }
        saved = {}
        monkeypatch.setattr(system_mod, "load_din_info", lambda: original)
        monkeypatch.setattr(system_mod, "save_din_info", lambda data: saved.update(data))

        ctx = SimpleNamespace(
            obj=SimpleNamespace(network="local", console=_DummyConsole())
        )
        system_mod.import_deployments(
            ctx=ctx, file=deployments_path, foundry=False, hardhat=False
        )

        assert saved["local"]["chain_id"] == 1337
        assert saved["local"]["representative"] == "0xREP"
        assert saved["local"]["coordinator"] == deployments["dinCoordinator"]


# ---------------------------------------------------------------------------
# Dependency declaration
# ---------------------------------------------------------------------------

class TestDependencyDeclaration:
    def test_click_is_declared(self):
        pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
        assert "click>=8.1.0" in pyproject.read_text()
