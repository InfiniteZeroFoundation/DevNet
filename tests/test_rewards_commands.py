from types import SimpleNamespace

import pytest
import typer

from dincli.cli import dintoken, rewards
from dincli.cli.modelownerd import rewards as owner_rewards
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs

ZERO = "0x0000000000000000000000000000000000000000"
DIN = 10**18


@pytest.fixture
def sent(monkeypatch):
    return record_txs(monkeypatch, rewards, owner_rewards, dintoken)


def make_ctx(*, gi=3, pool=0, din_token="0xD1", balance=100 * DIN, settled=True,
             claimed=False, claimable=0, registered=True, emission_funded=False, emission_amount=5 * DIN):
    coordinator = FakeContract("0xC0", GI=gi, GIstate=0)
    auditor = FakeContract(
        "0xA0",
        dinToken=din_token,
        giRewardPool=pool,
        giRewardSnapshot=(1, 2, 3, 4, settled),
        rewardClaimed=claimed,
        claimable=claimable,
    )
    token = FakeContract("0xD1", balanceOf=balance)
    registry = FakeContract("0xR0", getModelIdByTaskAuditor=(registered, 7))
    emission = FakeContract("0xE0", giEmissionFunded=emission_funded, emissionForCurrentEpoch=emission_amount)
    return SimpleNamespace(obj=FakeCtxObj(coordinator=coordinator, auditor=auditor, token=token,
                                          registry=registry, emission=emission))


# ── model-owner rewards deposit ─────────────────────────────────────────────

def test_deposit_approves_then_deposits_into_next_gi_by_default(sent):
    ctx = make_ctx(gi=3)

    owner_rewards.deposit(ctx, model_id=0, amount=1.5, gi=None)

    assert sent == [("approve", ("0xA0", 15 * DIN // 10)), ("depositRewards", (4, 15 * DIN // 10))]


def test_deposit_accepts_the_current_gi(sent):
    ctx = make_ctx(gi=3)

    owner_rewards.deposit(ctx, model_id=0, amount=2, gi=3)

    assert sent[-1] == ("depositRewards", (3, 2 * DIN))


def test_deposit_rejects_a_past_gi_before_any_tx(sent):
    ctx = make_ctx(gi=3)

    with pytest.raises(typer.Exit):
        owner_rewards.deposit(ctx, model_id=0, amount=1, gi=2)

    assert sent == []


def test_deposit_refuses_when_task_auditor_has_no_din_token(sent):
    ctx = make_ctx(din_token=ZERO)

    with pytest.raises(typer.Exit):
        owner_rewards.deposit(ctx, model_id=0, amount=1, gi=None)

    assert sent == []
    assert "setDinToken" in ctx.obj.console.text()


def test_deposit_refuses_more_than_the_balance(sent):
    ctx = make_ctx(balance=DIN)

    with pytest.raises(typer.Exit):
        owner_rewards.deposit(ctx, model_id=0, amount=2, gi=None)

    assert sent == []


# ── model-owner rewards fund-emission ───────────────────────────────────────

def test_fund_emission_calls_fund_gi_with_the_task_auditor(sent):
    ctx = make_ctx(gi=0)

    owner_rewards.fund_emission(ctx, model_id=0, gi=None)

    assert sent == [("fundGI", (1, "0xA0"))]


@pytest.mark.parametrize("kwargs, message", [
    ({"registered": False}, "UnregisteredTaskAuditor"),
    ({"emission_funded": True}, "GIAlreadyFunded"),
    ({"emission_amount": 0}, "EmissionExhausted"),
])
def test_fund_emission_fails_fast(sent, kwargs, message):
    ctx = make_ctx(**kwargs)

    with pytest.raises(typer.Exit):
        owner_rewards.fund_emission(ctx, model_id=0, gi=None)

    assert sent == []
    assert message in ctx.obj.console.text()


# ── rewards claim / withdraw ────────────────────────────────────────────────

def test_claim_sends_claim_reward(sent):
    ctx = make_ctx(claimable=3 * DIN)

    rewards.claim(ctx, model_id=0, gi=2)

    assert sent == [("claimReward", (2,))]


def test_claim_refuses_an_unsettled_gi(sent):
    ctx = make_ctx(settled=False)

    with pytest.raises(typer.Exit):
        rewards.claim(ctx, model_id=0, gi=2)

    assert sent == []


def test_claim_skips_an_already_claimed_gi(sent):
    ctx = make_ctx(claimed=True)

    rewards.claim(ctx, model_id=0, gi=2)

    assert sent == []
    assert "already claimed" in ctx.obj.console.text()


def test_withdraw_sends_claim_rewards(sent):
    ctx = make_ctx(claimable=3 * DIN)

    rewards.withdraw(ctx, model_id=0)

    assert sent == [("claimRewards", ())]


def test_withdraw_refuses_a_zero_balance(sent):
    ctx = make_ctx(claimable=0)

    with pytest.raises(typer.Exit):
        rewards.withdraw(ctx, model_id=0)

    assert sent == []


@pytest.mark.parametrize("path", [
    ["rewards", "claim"],
    ["rewards", "withdraw"],
    ["model-owner", "rewards", "deposit"],
    ["model-owner", "rewards", "fund-emission"],
    ["model-owner", "gi", "release-slots"],
    ["model-owner", "disputes", "resolve-test-data"],
    ["model-owner", "disputes", "reassign-test-data"],
    ["model-owner", "disputes", "close-expired"],
    ["model-owner", "disputes", "resolve-aggregation"],
    ["model-owner", "disputes", "settle-recomputation"],
    ["model-owner", "disputes", "expire"],
    ["auditor", "register-encryption-key"],
    ["auditor", "dispute-test-data"],
    ["aggregator", "dispute"],
    ["aggregator", "claim-dispute-bond"],
])
def test_command_is_registered(path):
    from typer.testing import CliRunner

    from dincli.main import app as main_app

    result = CliRunner().invoke(main_app, [*path, "--help"])

    assert result.exit_code == 0, result.output
