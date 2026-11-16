"""Status lookup errors retain fallback values; process interruption must stop."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from rich.table import Table
from typer.testing import CliRunner

from dincli.cli import auditor

LOOKUPS = ("hasAuditedLM", "LMeligibleVote", "auditScores")


@pytest.fixture
def batch_context(monkeypatch):
    account = SimpleNamespace(address="0x" + "11" * 20)
    console = MagicMock()
    contract = MagicMock()
    functions = contract.functions
    functions.AuditorsBatchCount.return_value.call.return_value = 1
    functions.getAuditorsBatch.return_value.call.return_value = (
        0, [account.address], [0], bytes(32),
    )
    functions.getClientModels.return_value.call.return_value = [
        (account.address, bytes(32), 0, True, True, True, 10),
    ]
    for name in LOOKUPS:
        getattr(functions, name).return_value.call.return_value = True
    obj = MagicMock()
    obj.get_en_w3_account_console.return_value = ("local", None, account, console)
    obj.get_deployed_din_task_auditor_contract.return_value = contract
    obj.get_current_gi_and_state.return_value = (1, 0)
    obj.validate_gi_LTE_curr_GI.return_value = 1
    monkeypatch.setattr(auditor, "lock_batch_seed_if_pending", lambda *args: None)
    monkeypatch.setattr(auditor.time, "sleep", lambda seconds: None)
    return SimpleNamespace(obj=obj), functions, console


@pytest.mark.parametrize("failed", [None, *LOOKUPS])
def test_registered_command_preserves_status_and_rpc_fallback(batch_context, failed):
    ctx, functions, console = batch_context
    if failed:
        getattr(functions, failed).return_value.call.side_effect = RuntimeError("RPC unavailable")
    result = CliRunner().invoke(
        auditor.lms_evaluation_app, ["show-batch", "1"], obj=ctx.obj,
    )
    assert result.exit_code == 0, result.exception
    tables = [call.args[0] for call in console.print.call_args_list if isinstance(call.args[0], Table)]
    statuses = [column._cells[0] for column in tables[-1].columns[5:8]]
    assert statuses == [str(name != failed) for name in LOOKUPS]
    for name in LOOKUPS:
        getattr(functions, name).return_value.call.assert_called_once()


@pytest.mark.parametrize("lookup", LOOKUPS)
@pytest.mark.parametrize("during", ["rpc", "sleep"])
@pytest.mark.parametrize("signal", [KeyboardInterrupt, SystemExit])
def test_interruption_propagates(batch_context, monkeypatch, lookup, during, signal):
    ctx, functions, _ = batch_context
    if during == "rpc":
        getattr(functions, lookup).return_value.call.side_effect = signal()
    else:
        # One initial batch-fetch sleep, then one after each status lookup.
        calls = iter([None] * (LOOKUPS.index(lookup) + 1) + [signal()])

        def sleep(seconds):
            effect = next(calls)
            if effect is not None:
                raise effect

        monkeypatch.setattr(auditor.time, "sleep", sleep)
    with pytest.raises(signal):
        auditor.show_batch(ctx, model_id=1, gi=None, batch=None)
    for name in LOOKUPS[LOOKUPS.index(lookup) + 1:]:
        getattr(functions, name).return_value.call.assert_not_called()


def test_registered_command_aborts_on_interrupt(batch_context):
    ctx, functions, _ = batch_context
    functions.hasAuditedLM.return_value.call.side_effect = KeyboardInterrupt()
    result = CliRunner().invoke(
        auditor.lms_evaluation_app, ["show-batch", "1"], obj=ctx.obj,
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    functions.LMeligibleVote.return_value.call.assert_not_called()
