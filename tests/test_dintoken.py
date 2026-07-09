from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from dincli.cli import dintoken
from dincli.main import app as main_app


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(args)


class DummyEth:
    def get_balance(self, address):
        return 3 * 10**18


class DummyWeb3:
    eth = DummyEth()

    def to_wei(self, amount, unit):
        assert unit == "ether"
        return int(amount * 10**18)


class DummyCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class DummyTokenFunctions:
    def __init__(self, token):
        self.token = token

    def balanceOf(self, address):
        self.token.balance_of_calls.append(address)
        return DummyCall(self.token.balance)

    def approve(self, address, amount):
        self.token.approvals.append((address, amount))
        return ("approve", address, amount)


class DummyStakeFunctions:
    def __init__(self, stake):
        self.stake = stake

    def stake(self, amount):
        self.stake.stakes.append(amount)
        return ("stake", amount)

    def getStake(self, address):
        self.stake.get_stake_calls.append(address)
        return DummyCall(self.stake.current_stake)


class DummyCoordinatorFunctions:
    def __init__(self, coordinator):
        self.coordinator = coordinator

    def depositAndMint(self):
        self.coordinator.deposit_calls += 1
        return "depositAndMint"


class DummyToken:
    def __init__(self, balance):
        self.balance = balance
        self.approvals = []
        self.balance_of_calls = []
        self.functions = DummyTokenFunctions(self)


class DummyStake:
    address = "0xStake"

    def __init__(self, current_stake=0):
        self.current_stake = current_stake
        self.stakes = []
        self.get_stake_calls = []
        self.functions = DummyStakeFunctions(self)


class DummyCoordinator:
    def __init__(self):
        self.deposit_calls = 0
        self.functions = DummyCoordinatorFunctions(self)


class DummyContextObj:
    def __init__(self, token_balance=100 * 10**18, current_stake=12 * 10**18):
        self.console = DummyConsole()
        self.w3 = DummyWeb3()
        self.account = SimpleNamespace(address="0xAccount")
        self.token = DummyToken(token_balance)
        self.stake = DummyStake(current_stake)
        self.coordinator = DummyCoordinator()

    def get_en_w3_account_console(self):
        return "local", self.w3, self.account, self.console

    def get_deployed_din_token_contract(self):
        return self.token

    def get_deployed_din_stake_contract(self):
        return self.stake

    def get_deployed_din_coordinator_contract(self):
        return self.coordinator


def make_ctx(**kwargs):
    return SimpleNamespace(obj=DummyContextObj(**kwargs))


def test_buy_sends_eth_value(monkeypatch):
    ctx = make_ctx()
    sent_transactions = []

    def fake_build_and_send_tx(*args, **kwargs):
        sent_transactions.append((args, kwargs))
        return SimpleNamespace(transactionHash=bytes.fromhex("12" * 32))

    monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)

    dintoken.buy_dintokens(ctx, 1.5)

    assert ctx.obj.coordinator.deposit_calls == 1
    assert sent_transactions[0][0][1] == "depositAndMint"
    assert sent_transactions[0][1]["tx_params"] == {"value": 1500000000000000000}


def test_stake_uses_requested_amount(monkeypatch):
    ctx = make_ctx()
    sent_transactions = []

    def fake_build_and_send_tx(*args, **kwargs):
        sent_transactions.append((args, kwargs))
        return SimpleNamespace(transactionHash=bytes.fromhex("34" * 32))

    monkeypatch.setattr(dintoken, "build_and_send_tx", fake_build_and_send_tx)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    dintoken.stake_dintokens(ctx, 12)

    stake_amount = 12 * 10**18
    assert ctx.obj.token.approvals == [("0xStake", stake_amount)]
    assert ctx.obj.stake.stakes == [stake_amount]
    assert sent_transactions[0][0][1] == ("approve", "0xStake", stake_amount)
    assert sent_transactions[1][0][1] == ("stake", stake_amount)


def test_stake_exits_when_balance_is_insufficient(monkeypatch):
    ctx = make_ctx(token_balance=11 * 10**18)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    with pytest.raises(typer.Exit):
        dintoken.stake_dintokens(ctx, 12)

    assert ctx.obj.token.approvals == []
    assert ctx.obj.stake.stakes == []


def test_stake_exits_when_amount_is_below_minimum(monkeypatch):
    ctx = make_ctx(token_balance=100 * 10**18)
    monkeypatch.setattr(dintoken.time, "sleep", lambda seconds: None)

    with pytest.raises(typer.Exit):
        dintoken.stake_dintokens(ctx, 9)

    assert ctx.obj.token.approvals == []
    assert ctx.obj.stake.stakes == []


def test_read_stake_reads_active_account_stake():
    ctx = make_ctx(current_stake=15 * 10**18)

    dintoken.read_dintoken_stake(ctx)

    assert ctx.obj.stake.get_stake_calls == ["0xAccount"]


def test_top_level_dintoken_help_exposes_commands():
    result = CliRunner().invoke(main_app, ["dintoken", "--help"])

    assert result.exit_code == 0
    assert "buy" in result.output
    assert "stake" in result.output
    assert "read-stake" in result.output


@pytest.mark.parametrize("path", [["aggregator", "dintoken", "--help"], ["auditor", "dintoken", "--help"]])
def test_legacy_role_dintoken_help_exposes_commands(path):
    result = CliRunner().invoke(main_app, path)

    assert result.exit_code == 0
    assert "buy" in result.output
    assert "stake" in result.output
    assert "read-stake" in result.output
