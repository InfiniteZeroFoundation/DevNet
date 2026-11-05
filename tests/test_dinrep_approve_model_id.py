from types import SimpleNamespace

import pytest
import typer

from dincli.cli import dinrep
from tests._cli_fakes import FakeContract, FakeCtxObj, record_txs

COORDINATOR = "0x00000000000000000000000000000000000000C0"
AUDITOR = "0x00000000000000000000000000000000000000A0"
# modelRequests getter: (requester, isOpenSource, manifestCID, taskCoordinator,
# taskAuditor, feePaid, processed, approved, createdAt)
REQUEST = ("0xOwner", True, b"\x00" * 32, COORDINATOR, AUDITOR, 0, False, False, 0)


@pytest.fixture
def sent(monkeypatch):
    return record_txs(monkeypatch, dinrep)


def make_ctx(monkeypatch, *, total_models, coordinator_model_id, auditor_model_id):
    task_contracts = {
        COORDINATOR: FakeContract(COORDINATOR, modelId=coordinator_model_id),
        AUDITOR: FakeContract(AUDITOR, modelId=auditor_model_id),
    }
    monkeypatch.setattr(dinrep, "get_contract_instance", lambda abi, network, address: task_contracts[address])
    registry = FakeContract("0xR0", modelRequests=REQUEST, totalModels=total_models)
    return SimpleNamespace(obj=FakeCtxObj(registry=registry))


def test_approve_sends_when_both_model_ids_match(monkeypatch, sent):
    ctx = make_ctx(monkeypatch, total_models=4, coordinator_model_id=4, auditor_model_id=4)

    dinrep.approve_registration_request(ctx, request_id=7, force=False)

    assert sent == [("approveModel", (7,))]


@pytest.mark.parametrize("coordinator_model_id, auditor_model_id, named", [
    (3, 4, "DINTaskCoordinator"),
    (4, 0, "DINTaskAuditor"),
])
def test_approve_refuses_a_model_id_mismatch(monkeypatch, sent, coordinator_model_id, auditor_model_id, named):
    ctx = make_ctx(monkeypatch, total_models=4, coordinator_model_id=coordinator_model_id,
                   auditor_model_id=auditor_model_id)

    with pytest.raises(typer.Exit):
        dinrep.approve_registration_request(ctx, request_id=7, force=False)

    assert sent == []
    assert named in ctx.obj.console.text()
    assert "--force" in ctx.obj.console.text()


def test_force_approves_despite_a_mismatch(monkeypatch, sent):
    ctx = make_ctx(monkeypatch, total_models=4, coordinator_model_id=3, auditor_model_id=3)

    dinrep.approve_registration_request(ctx, request_id=7, force=True)

    assert sent == [("approveModel", (7,))]
