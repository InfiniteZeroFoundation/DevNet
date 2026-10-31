from types import SimpleNamespace

import pytest
import typer

from dincli.cli.modelownerd import gi
from dincli.cli.utils import GIstatestrToIndex
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs


@pytest.fixture
def sent(monkeypatch):
    return record_txs(monkeypatch, gi)


def make_ctx(curr_gi, state, released=False, pool=0):
    coordinator = FakeContract("0xC0", GI=curr_gi, GIstate=GIstatestrToIndex(state),
                               registrationSlotsReleased=released)
    task_auditor = FakeContract("0xA0", giRewardPool=pool)
    return SimpleNamespace(obj=FakeCtxObj(coordinator=coordinator, auditor=task_auditor))


def test_release_slots_defaults_to_the_current_ended_gi(sent):
    gi.release_slots(make_ctx(3, "GIended"), model_id=0, gi=None)

    assert sent == [("releaseGIRegistrationSlots", (3,))]


def test_release_slots_accepts_an_earlier_gi(sent):
    gi.release_slots(make_ctx(3, "GIstarted"), model_id=0, gi=2)

    assert sent == [("releaseGIRegistrationSlots", (2,))]


@pytest.mark.parametrize("curr_gi, state, ref_gi", [
    (3, "GIstarted", None),  # current GI still running
    (3, "GIended", 4),       # future GI
    (0, "GenesisModelCreated", None),
])
def test_release_slots_refuses_a_gi_that_has_not_ended(sent, curr_gi, state, ref_gi):
    with pytest.raises(typer.Exit):
        gi.release_slots(make_ctx(curr_gi, state), model_id=0, gi=ref_gi)

    assert sent == []


def test_release_slots_skips_an_already_released_gi(sent):
    ctx = make_ctx(3, "GIended", released=True)

    gi.release_slots(ctx, model_id=0, gi=None)

    assert sent == []
    assert "already released" in ctx.obj.console.text()


def test_gi_start_refuses_an_unfunded_gi_and_names_the_command(sent):
    ctx = make_ctx(1, "GIended", pool=0)

    with pytest.raises(typer.Exit):
        gi.start(ctx, model_id=0, gi=None, threshold=None)

    assert sent == []
    assert "rewards deposit 0 --gi 2" in ctx.obj.console.text()
