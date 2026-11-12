"""`auditor register` / `aggregator register` exit non-zero when registration
fails (a reverted or refused tx, e.g. TA_DualRoleNotAllowed, or too little
stake), so scripts and the integration suite can tell a refusal from success."""
from types import SimpleNamespace

import pytest
import typer

from dincli.cli import aggregator, auditor
from tests._cli_fakes import DummyConsole, FakeContract

ADDR = "0x000000000000000000000000000000000000A11c"
BIG = 10**30


class _Ctx:
    def __init__(self, stake):
        self.console = DummyConsole()
        self.coordinator = FakeContract("0xC", isDINAggregator=False)
        self.auditor = FakeContract("0xA", isRegisteredAuditor=False)
        self.stake = FakeContract("0xS", getStake=stake)

    def get_en_w3_account_console(self, model_id=None):
        return "local", None, SimpleNamespace(address=ADDR), self.console

    def get_deployed_din_task_coordinator_contract(self, *a, **k):
        return self.coordinator

    def get_deployed_din_task_auditor_contract(self, *a, **k):
        return self.auditor

    def get_deployed_din_coordinator_contract(self, *a, **k):
        return FakeContract("0xD")

    def get_deployed_din_stake_contract(self, *a, **k):
        return self.stake

    def get_current_gi_and_state(self, *a, **k):
        return 1, 0

    def validate_gi_ET_curr_GI(self, gi, curr):
        return curr

    def validate_GIstate_ET_given_GIstate(self, *a, **k):
        pass


@pytest.mark.parametrize("module", [auditor, aggregator])
@pytest.mark.parametrize("receipt,expect_exit", [(None, True), (SimpleNamespace(status=1), False)])
def test_failed_tx_exits_1(monkeypatch, module, receipt, expect_exit):
    monkeypatch.setattr(module, "build_and_send_tx", lambda *a, **k: receipt)
    ctx = SimpleNamespace(obj=_Ctx(stake=BIG))
    if expect_exit:
        with pytest.raises(typer.Exit) as exc:
            module.register(ctx, model_id=0, gi=None)
        assert exc.value.exit_code == 1
    else:
        module.register(ctx, model_id=0, gi=None)


@pytest.mark.parametrize("module", [auditor, aggregator])
def test_insufficient_stake_exits_1(monkeypatch, module):
    sent = []
    monkeypatch.setattr(module, "build_and_send_tx", lambda *a, **k: sent.append(a))
    with pytest.raises(typer.Exit) as exc:
        module.register(SimpleNamespace(obj=_Ctx(stake=0)), model_id=0, gi=None)
    assert exc.value.exit_code == 1
    assert sent == []
