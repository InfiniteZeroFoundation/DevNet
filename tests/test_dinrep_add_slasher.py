from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from dincli.cli import dinrep
from dincli.main import app as main_app

SLASHER = "0x00000000000000000000000000000000000000Aa"


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.messages)


class DummyCoordinatorFunctions:
    def addSlasherContract(self, address):
        return ("addSlasherContract", address)


class DummyContextObj:
    def __init__(self):
        self.console = DummyConsole()
        self.coordinator_loads = 0
        self.account_loads = 0

    def get_en_w3_account_console(self):
        # Loads (and may decrypt) the wallet in the real DinContext.
        self.account_loads += 1
        return "local", None, SimpleNamespace(address=SLASHER), self.console

    def get_deployed_din_coordinator_contract(self):
        self.coordinator_loads += 1
        return SimpleNamespace(functions=DummyCoordinatorFunctions())


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_build_and_send_tx(*args, **kwargs):
        calls.append(args)

    monkeypatch.setattr(dinrep, "build_and_send_tx", fake_build_and_send_tx)
    return calls


def test_add_slasher_without_target_exits_before_loading_coordinator(sent):
    ctx = SimpleNamespace(obj=DummyContextObj())

    with pytest.raises(typer.Exit) as exc:
        dinrep.add_slasher(ctx, contract=None, task_coordinator_flag=False, task_auditor_flag=False)

    assert exc.value.exit_code == 1
    assert sent == []
    assert ctx.obj.coordinator_loads == 0
    assert ctx.obj.account_loads == 0  # usage error before any wallet unlock
    assert "No slasher contract given" in ctx.obj.console.text()


def test_add_slasher_with_explicit_contract_sends_add_slasher_contract(sent):
    ctx = SimpleNamespace(obj=DummyContextObj())

    dinrep.add_slasher(ctx, contract=SLASHER, task_coordinator_flag=False, task_auditor_flag=False)

    assert len(sent) == 1
    assert sent[0][1] == ("addSlasherContract", SLASHER)
    assert ctx.obj.coordinator_loads == 1
    assert ctx.obj.account_loads == 1


def test_dinrep_has_no_deploy_sub_app():
    # The constructor-based deploy commands could not deploy the proxied platform
    # contracts; deployment goes through foundry/script/DeployPlatform.s.sol.
    result = CliRunner().invoke(main_app, ["dinrep", "deploy", "--help"])

    assert result.exit_code != 0
    assert "No such command" in result.output
