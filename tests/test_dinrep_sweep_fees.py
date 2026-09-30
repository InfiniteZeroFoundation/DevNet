from decimal import Decimal
from types import SimpleNamespace

import pytest
import typer
from typer.testing import CliRunner

from dincli.cli import dinrep
from dincli.main import app as main_app

OWNER = "0x00000000000000000000000000000000000000Aa"
OTHER = "0x00000000000000000000000000000000000000Bb"
ROUTER = "0x00000000000000000000000000000000000000Cc"
TREASURY = "0x00000000000000000000000000000000000000Dd"
ZERO = "0x0000000000000000000000000000000000000000"


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.messages)


class DummyCall:
    def __init__(self, value):
        self.value = value

    def call(self):
        return self.value


class DummyEth:
    def __init__(self, balance):
        self.balance = balance
        self.balance_calls = []

    def get_balance(self, address):
        self.balance_calls.append(address)
        return self.balance


class DummyWeb3:
    def __init__(self, balance):
        self.eth = DummyEth(balance)

    def from_wei(self, value, unit):
        assert unit == "ether"
        return Decimal(value) / Decimal(10**18)


class DummySweepableFunctions:
    def __init__(self, owner, fee_router):
        self._owner = owner
        self._fee_router = fee_router

    def owner(self):
        return DummyCall(self._owner)

    def feeRouter(self):
        return DummyCall(self._fee_router)

    def sweepFeesToRouter(self):
        return "sweepFeesToRouter"


class DummySweepable:
    """Stands in for DINModelRegistry / DinCoordinator — same sweep surface."""

    def __init__(self, address, owner, fee_router):
        self.address = address
        self.functions = DummySweepableFunctions(owner, fee_router)


class DummyRouterFunctions:
    def __init__(self, split, fee_sources, fee_source_calls):
        self._split = split
        self._fee_sources = fee_sources
        self._fee_source_calls = fee_source_calls

    def feeSources(self, address):
        self._fee_source_calls.append(address)
        return DummyCall(address in self._fee_sources)

    def ethSplit(self):
        return DummyCall(self._split)

    def treasury(self):
        return DummyCall(TREASURY)


class DummyContextObj:
    def __init__(self, balance, owner, fee_router):
        self.console = DummyConsole()
        self.w3 = DummyWeb3(balance)
        self.account = SimpleNamespace(address=OWNER)
        self.registry = DummySweepable("0xRegistry", owner, fee_router)
        self.coordinator = DummySweepable("0xCoordinator", owner, fee_router)

    def get_en_w3_account_console(self):
        return "local", self.w3, self.account, self.console

    def get_deployed_din_registry_contract(self):
        return self.registry

    def get_deployed_din_coordinator_contract(self):
        return self.coordinator


# (command function, ctx attribute holding the contract it must sweep, contract name)
TARGETS = [
    pytest.param(dinrep.sweep_registry_fees, "registry", "DINModelRegistry", id="registry"),
    pytest.param(dinrep.sweep_coordinator_fees, "coordinator", "DinCoordinator", id="coordinator"),
]


@pytest.fixture
def harness(monkeypatch):
    sent = []
    prompts = []
    router_loads = []
    state = SimpleNamespace(sent=sent, prompts=prompts, router_loads=router_loads, confirm=True,
                            split=(9500, 500, 0, 0),
                            # Router has authorised both dummy contracts unless a test removes one.
                            fee_sources={"0xRegistry", "0xCoordinator"}, fee_source_calls=[])

    def fake_build_and_send_tx(*args, **kwargs):
        sent.append(args)
        return SimpleNamespace(transactionHash=bytes.fromhex("56" * 32))

    def fake_get_contract_instance(artifact_path, network, address=None):
        router_loads.append((artifact_path, network, address))
        return SimpleNamespace(
            functions=DummyRouterFunctions(state.split, state.fee_sources, state.fee_source_calls)
        )

    def fake_confirm(text, *args, **kwargs):
        prompts.append(text)
        return state.confirm

    monkeypatch.setattr(dinrep, "build_and_send_tx", fake_build_and_send_tx)
    monkeypatch.setattr(dinrep, "get_contract_instance", fake_get_contract_instance)
    monkeypatch.setattr(dinrep.typer, "confirm", fake_confirm)
    return state


def make_ctx(balance=10**18, owner=OWNER, fee_router=ROUTER):
    return SimpleNamespace(obj=DummyContextObj(balance, owner, fee_router))


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_rejects_non_owner_wallet(harness, command, target, name):
    ctx = make_ctx(owner=OTHER)

    with pytest.raises(typer.Exit) as exc:
        command(ctx, yes=True)

    assert exc.value.exit_code == 1
    assert harness.sent == []
    assert "not the DIN-Representative (owner) wallet" in ctx.obj.console.text()
    assert name in ctx.obj.console.text()


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_exits_when_fee_router_unset(harness, command, target, name):
    ctx = make_ctx(fee_router=ZERO)

    with pytest.raises(typer.Exit) as exc:
        command(ctx, yes=True)

    assert exc.value.exit_code == 1
    assert harness.sent == []
    assert "DeployPlatform.s.sol" in ctx.obj.console.text()


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_exits_when_not_a_fee_source(harness, command, target, name):
    ctx = make_ctx()
    target_address = getattr(ctx.obj, target).address
    harness.fee_sources.discard(target_address)

    with pytest.raises(typer.Exit) as exc:
        command(ctx, yes=False)

    assert exc.value.exit_code == 1
    assert harness.sent == []
    assert harness.prompts == []
    # The router was asked about exactly the contract being swept.
    assert harness.fee_source_calls == [target_address]
    out = ctx.obj.console.text()
    assert "not an authorised fee source" in out
    assert f"addFeeSource({target_address})" in out
    # Fails before the preview, not after it.
    assert "Treasury (" not in out


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_zero_balance_sends_nothing_and_does_not_prompt(harness, command, target, name):
    ctx = make_ctx(balance=0)

    command(ctx, yes=False)

    assert harness.sent == []
    assert harness.prompts == []
    assert "No accumulated fees to sweep" in ctx.obj.console.text()


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_declined_confirmation_sends_no_tx(harness, command, target, name):
    ctx = make_ctx()
    harness.confirm = False

    with pytest.raises(typer.Exit) as exc:
        command(ctx, yes=False)

    assert exc.value.exit_code == 0
    assert len(harness.prompts) == 1
    assert harness.sent == []
    assert "Aborted. No transaction sent." in ctx.obj.console.text()


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_confirmed_sends_one_tx(harness, command, target, name):
    ctx = make_ctx()

    command(ctx, yes=False)

    assert len(harness.prompts) == 1
    assert len(harness.sent) == 1
    assert harness.sent[0][1] == "sweepFeesToRouter"


@pytest.mark.parametrize("command, target, name", TARGETS)
def test_sweep_yes_skips_prompt_and_previews_split(harness, command, target, name):
    ctx = make_ctx(balance=10**18)

    command(ctx, yes=True)

    assert harness.prompts == []
    assert len(harness.sent) == 1
    assert harness.sent[0][1] == "sweepFeesToRouter"
    # The swept contract's own balance is what gets previewed.
    assert ctx.obj.w3.eth.balance_calls == [getattr(ctx.obj, target).address]
    # The router is loaded from the bundled DinFeeRouter ABI at the wired address.
    artifact_path, _, address = harness.router_loads[0]
    assert artifact_path.endswith("DinFeeRouter.json")
    assert address == ROUTER
    # The fee-source check asked about the swept contract, and passed.
    assert harness.fee_source_calls == [getattr(ctx.obj, target).address]
    out = ctx.obj.console.text()
    assert f"Treasury ({TREASURY}): 0.05 ETH" in out
    assert "Validator pool: 0.95 ETH" in out


def test_sweep_split_matches_router_rounding(harness):
    """publicGoods absorbs rounding dust, exactly as DinFeeRouter.routeFeeETH does."""
    ctx = make_ctx(balance=7)
    harness.split = (3333, 3333, 3333, 1)

    dinrep.sweep_registry_fees(ctx, yes=True)

    out = ctx.obj.console.text()
    # 7 * 3333 // 10000 == 2 wei for each of the first three buckets; public goods gets 7 - 6.
    assert "Treasury" in out and "2E-18 ETH" in out
    assert "Public goods: 1E-18 ETH" in out


def test_dinrep_registry_help_lists_sweep_and_not_dead_commands():
    result = CliRunner().invoke(main_app, ["dinrep", "registry", "--help"])

    assert result.exit_code == 0
    assert "sweep-fees" in result.output
    assert "withdraw-fees" not in result.output
    assert "set-dao-admin" not in result.output


def test_dinrep_coordinator_help_lists_sweep():
    result = CliRunner().invoke(main_app, ["dinrep", "coordinator", "--help"])

    assert result.exit_code == 0
    assert "sweep-fees" in result.output
