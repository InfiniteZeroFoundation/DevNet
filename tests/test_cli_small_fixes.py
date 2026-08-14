"""Tests for PR 8 — the small CLI bundle.

No chain writes. Mocks are used for every web3/account interaction, and the
only CLI flows that go through Typer are the system commands, whose config and
wallet paths are patched to a temp dir.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from eth_account import Account
from typer.testing import CliRunner

from dincli.cli import aggregator, auditor, system, utils
from dincli.cli.utils import ReadResult
from dincli.main import app

runner = CliRunner()

REPO_ROOT = Path(__file__).resolve().parents[1]


# ------------------------------------------------------------------ #
#  Shared helpers                                                     #
# ------------------------------------------------------------------ #

def _printed_texts(console):
    """Flatten every argument passed to a console.print mock."""
    texts = []
    for call in console.print.call_args_list:
        texts.append(" ".join(str(arg) for arg in call.args))
    return texts


def _make_tx_receipt(status=1):
    receipt = MagicMock()
    receipt.status = status
    receipt.transactionHash.hex.return_value = "0x" + "ab" * 32
    return receipt


def _make_stake_ctx(token_balance):
    """Build a ctx.obj for aggregator/auditor stake() with mocked contracts."""
    token = MagicMock()
    stake = MagicMock()
    stake.address = "0xStake"

    token.functions.balanceOf.return_value.call.return_value = token_balance
    token.functions.approve.return_value.build_transaction.return_value = {}
    stake.functions.stake.return_value.build_transaction.return_value = {}

    w3 = MagicMock()
    w3.eth.get_balance.return_value = 3 * 10**18
    w3.eth.estimate_gas.return_value = 100_000
    w3.eth.send_raw_transaction.return_value = b"tx"
    w3.eth.wait_for_transaction_receipt.return_value = _make_tx_receipt()

    account = MagicMock()
    account.address = "0x" + "11" * 20
    account.sign_transaction.return_value.raw_transaction = b"raw"

    console = MagicMock()

    obj = MagicMock()
    obj.get_en_w3_account_console.return_value = ("local", w3, account, console)
    obj.get_deployed_din_token_contract.return_value = token
    obj.get_deployed_din_stake_contract.return_value = stake
    obj.get_tx_params.return_value = {}

    return SimpleNamespace(obj=obj), token, stake, w3, account, console


def _make_buy_ctx(balance_sequence):
    """Build a ctx.obj for buy() with a scripted token balanceOf."""
    token = MagicMock()
    coordinator = MagicMock()

    token.functions.balanceOf.return_value.call.side_effect = balance_sequence
    coordinator.functions.depositAndMint.return_value.build_transaction.return_value = {}

    w3 = MagicMock()
    w3.eth.get_balance.return_value = 3 * 10**18
    w3.eth.estimate_gas.return_value = 100_000
    w3.eth.send_raw_transaction.return_value = b"tx"
    w3.eth.wait_for_transaction_receipt.return_value = _make_tx_receipt()

    account = MagicMock()
    account.address = "0x" + "11" * 20
    account.sign_transaction.return_value.raw_transaction = b"raw"

    console = MagicMock()

    obj = MagicMock()
    obj.get_en_w3_account_console.return_value = ("local", w3, account, console)
    obj.get_deployed_din_token_contract.return_value = token
    obj.get_deployed_din_coordinator_contract.return_value = coordinator
    obj.get_tx_params.return_value = {}

    return SimpleNamespace(obj=obj), token, w3, console


def _patch_config_paths(monkeypatch, tmp_path):
    """Patch both bound copies of the config/wallet path constants."""
    config_file = tmp_path / "config.json"
    wallet_file = tmp_path / "wallet.json"

    monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(utils, "CONFIG_FILE", config_file)
    monkeypatch.setattr(utils, "WALLET_FILE", wallet_file)

    monkeypatch.setattr(system, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(system, "CONFIG_FILE", config_file)
    monkeypatch.setattr(system, "WALLET_FILE", wallet_file)

    return config_file, wallet_file


# ------------------------------------------------------------------ #
#  A — read_after_write helper                                        #
# ------------------------------------------------------------------ #

class TestReadAfterWrite:
    def test_first_read_increased_no_sleep(self, monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr(utils.time, "sleep", sleep)
        read_fn = MagicMock(return_value=150 * 10**18)

        result = utils.read_after_write(read_fn, baseline=100 * 10**18)

        assert result == ReadResult(150 * 10**18, True, True)
        sleep.assert_not_called()

    def test_increase_on_later_attempt(self, monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr(utils.time, "sleep", sleep)
        read_fn = MagicMock(side_effect=[100 * 10**18, 100 * 10**18, 200 * 10**18])

        result = utils.read_after_write(read_fn, baseline=100 * 10**18)

        assert result == ReadResult(200 * 10**18, True, True)
        assert sleep.call_count == 2

    def test_reads_succeed_but_never_exceed(self, monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr(utils.time, "sleep", sleep)
        read_fn = MagicMock(side_effect=[100 * 10**18, 90 * 10**18, 80 * 10**18, 70 * 10**18, 60 * 10**18])

        result = utils.read_after_write(read_fn, baseline=100 * 10**18)

        assert result == ReadResult(60 * 10**18, False, True)
        assert sleep.call_count == 4

    def test_every_read_raises(self, monkeypatch):
        sleep = MagicMock()
        monkeypatch.setattr(utils.time, "sleep", sleep)
        read_fn = MagicMock(side_effect=Exception("rpc down"))

        result = utils.read_after_write(read_fn, baseline=100 * 10**18)

        assert result == ReadResult(100 * 10**18, False, False)
        assert sleep.call_count == 4

    def test_attempts_below_one_raises(self):
        with pytest.raises(ValueError):
            utils.read_after_write(MagicMock(), baseline=0, attempts=0)

    def test_keyboard_interrupt_propagates(self, monkeypatch):
        monkeypatch.setattr(utils.time, "sleep", MagicMock())
        read_fn = MagicMock(side_effect=KeyboardInterrupt)

        with pytest.raises(KeyboardInterrupt):
            utils.read_after_write(read_fn, baseline=0)


# ------------------------------------------------------------------ #
#  B — stake() honors amount (aggregator and auditor)                 #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("module", [aggregator, auditor])
class TestStakeAmount:
    def test_stake_25_uses_requested_amount(self, monkeypatch, module):
        monkeypatch.setattr(module.time, "sleep", lambda *_: None)
        ctx, token, stake, w3, account, console = _make_stake_ctx(100 * 10**18)

        module.stake(ctx, 25)

        stake_amount = 25 * 10**18
        assert all(
            call.args == (stake.address, stake_amount)
            for call in token.functions.approve.call_args_list
        )
        assert all(
            call.args == (stake_amount,)
            for call in stake.functions.stake.call_args_list
        )

    def test_stake_25_with_20_balance_is_refused(self, monkeypatch, module):
        monkeypatch.setattr(module.time, "sleep", lambda *_: None)
        ctx, token, stake, w3, account, console = _make_stake_ctx(20 * 10**18)

        with pytest.raises(Exception) as exc_info:
            module.stake(ctx, 25)
        assert type(exc_info.value).__name__ == "Exit"

        token.functions.approve.assert_not_called()
        stake.functions.stake.assert_not_called()
        w3.eth.estimate_gas.assert_not_called()
        account.sign_transaction.assert_not_called()
        w3.eth.send_raw_transaction.assert_not_called()

    def test_below_minimum_builds_nothing(self, monkeypatch, module):
        monkeypatch.setattr(module.time, "sleep", lambda *_: None)
        ctx, token, stake, w3, account, console = _make_stake_ctx(100 * 10**18)

        with pytest.raises(Exception) as exc_info:
            module.stake(ctx, 9)
        assert type(exc_info.value).__name__ == "Exit"

        token.functions.approve.assert_not_called()
        stake.functions.stake.assert_not_called()
        w3.eth.estimate_gas.assert_not_called()
        account.sign_transaction.assert_not_called()
        w3.eth.send_raw_transaction.assert_not_called()

    def test_stake_10_documented_path_unchanged(self, monkeypatch, module):
        monkeypatch.setattr(module.time, "sleep", lambda *_: None)
        ctx, token, stake, w3, account, console = _make_stake_ctx(10 * 10**18)

        module.stake(ctx, 10)

        stake_amount = 10 * 10**18
        assert all(
            call.args == (stake.address, stake_amount)
            for call in token.functions.approve.call_args_list
        )
        assert all(
            call.args == (stake_amount,)
            for call in stake.functions.stake.call_args_list
        )


# ------------------------------------------------------------------ #
#  A callers — buy() retry rendering (aggregator and auditor)         #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("module,label", [(aggregator, "Aggregator"), (auditor, "Auditor")])
class TestBuyRetry:
    def _patch_helper(self, monkeypatch, module, result):
        helper = MagicMock(return_value=result)
        monkeypatch.setattr(module, "read_after_write", helper)
        return helper

    def test_settled_prints_new_balance(self, monkeypatch, module, label):
        baseline = 100 * 10**18
        ctx, token, w3, console = _make_buy_ctx([baseline, baseline])
        helper = self._patch_helper(monkeypatch, module, ReadResult(150 * 10**18, True, True))

        module.buy(ctx, 1.0)

        assert helper.call_count == 1
        assert helper.call_args.kwargs["baseline"] == baseline
        texts = " ".join(_printed_texts(console))
        assert f"{label} DINToken balance:" in texts
        assert "150" in texts
        assert "purchase failed" not in texts
        assert "transaction failed" not in texts

    def test_unsettled_observed_prints_last_and_lag_note(self, monkeypatch, module, label):
        baseline = 100 * 10**18
        ctx, token, w3, console = _make_buy_ctx([baseline, baseline])
        helper = self._patch_helper(monkeypatch, module, ReadResult(120 * 10**18, False, True))

        module.buy(ctx, 1.0)

        texts = " ".join(_printed_texts(console))
        assert f"{label} DINToken balance:" in texts
        assert "120" in texts
        assert "lagging" in texts
        assert "Pre-purchase balance was" not in texts
        assert "purchase failed" not in texts
        assert "transaction failed" not in texts

    def test_unobserved_prints_pre_write_balance(self, monkeypatch, module, label):
        baseline = 100 * 10**18
        ctx, token, w3, console = _make_buy_ctx([baseline, baseline])
        helper = self._patch_helper(monkeypatch, module, ReadResult(baseline, False, False))

        module.buy(ctx, 1.0)

        texts = " ".join(_printed_texts(console))
        assert "Pre-purchase balance was" in texts
        assert "100" in texts
        assert "your balance is" not in texts
        assert "purchase failed" not in texts
        assert "transaction failed" not in texts


# ------------------------------------------------------------------ #
#  C — demo mode                                                      #
# ------------------------------------------------------------------ #

class TestDemoMode:
    def test_account_path_warns_about_public_key(self, monkeypatch, tmp_path):
        config_file, _ = _patch_config_paths(monkeypatch, tmp_path)
        config_file.write_text('{"demo_mode": true}', encoding="utf-8")
        key = "0x" + Account.create().key.hex()
        monkeypatch.setattr(system, "get_demo_private_key", lambda index: key)

        result = runner.invoke(app, ["--network", "local", "system", "connect-wallet", "--account", "0"])

        assert result.exit_code == 0
        assert "unencrypted on disk" in result.output
        assert "publicly known Hardhat development key" in result.output

    def test_pasted_key_path_does_not_call_it_public(self, monkeypatch, tmp_path):
        config_file, _ = _patch_config_paths(monkeypatch, tmp_path)
        config_file.write_text('{"demo_mode": true}', encoding="utf-8")
        key = "0x" + Account.create().key.hex()

        result = runner.invoke(app, ["--network", "local", "system", "connect-wallet", key])

        assert result.exit_code == 0
        assert "unencrypted on disk" in result.output
        assert "publicly known Hardhat development key" not in result.output

    def test_configure_demo_defaults_to_no(self, monkeypatch, tmp_path):
        config_file, _ = _patch_config_paths(monkeypatch, tmp_path)

        result = runner.invoke(app, ["--network", "local", "system", "configure-demo"])

        assert result.exit_code == 0
        assert "disabled" in result.output
        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert saved["demo_mode"] is False


# ------------------------------------------------------------------ #
#  D — python floor                                                  #
# ------------------------------------------------------------------ #

class TestPythonFloor:
    def test_pyproject_requires_python_and_version(self):
        text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        import tomllib

        data = tomllib.loads(text)

        assert data["project"]["requires-python"] == ">=3.10"
        assert data["project"]["version"] == "0.1.0"


# ------------------------------------------------------------------ #
#  E — password env lookups are silent when optional                 #
# ------------------------------------------------------------------ #

class TestPasswordEnvLookups:
    def _make_env_without_password(self, tmp_path):
        (tmp_path / ".env").write_text("OTHER_KEY=value\n", encoding="utf-8")

    def test_get_password_is_silent_without_env_key(self, monkeypatch, tmp_path):
        self._make_env_without_password(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
        console = MagicMock()
        monkeypatch.setattr(utils, "console", console)

        result = utils._get_password(prompt=False)

        assert result == ""
        texts = " ".join(_printed_texts(console))
        assert "❌" not in texts
        assert texts.count("DIN_WALLET_PASSWORD not found in environment") == 1

    def test_cache_password_is_silent_without_env_key(self, monkeypatch, tmp_path):
        self._make_env_without_password(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
        console = MagicMock()
        monkeypatch.setattr(utils, "console", console)

        utils._cache_password_if_needed("test-password")

        texts = " ".join(_printed_texts(console))
        assert "❌" not in texts

    def test_pair_does_not_duplicate_informational_line(self, monkeypatch, tmp_path):
        self._make_env_without_password(tmp_path)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
        console = MagicMock()
        monkeypatch.setattr(utils, "console", console)

        utils._get_password(prompt=False)
        utils._cache_password_if_needed("test-password")

        texts = " ".join(_printed_texts(console))
        assert texts.count("DIN_WALLET_PASSWORD not found in environment") == 1
        assert "❌" not in texts

    def test_fallback_chain_still_works(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(utils, "CONFIG_DIR", tmp_path)
        console = MagicMock()
        monkeypatch.setattr(utils, "console", console)

        monkeypatch.setenv("DIN_WALLET_PASSWORD", "from-env")
        assert utils._get_password(prompt=False) == "from-env"
        monkeypatch.delenv("DIN_WALLET_PASSWORD")

        session_file = tmp_path / ".session"
        session_file.write_text("from-session", encoding="utf-8")
        os.chmod(session_file, 0o600)
        assert utils._get_password(prompt=False) == "from-session"
