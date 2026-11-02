"""
Regression tests for the task_auditor model-ID guard (PR No. 261 / issue No. 223 TP-3).

Before sending the deployment transaction, task_auditor() reads the coordinator's
immutable modelId() and rejects a mismatch. Both IDs select per-model stake floors
and pairing is one-shot, so a mismatched deploy can't be corrected without a full
redeployment.
"""
import time
from unittest.mock import Mock
from types import SimpleNamespace

import pytest
import typer

from dincli.cli.modelownerd import deploy

COORD_ADDR  = "0x000000000000000000000000000000000000000C"
AUDITOR_ADDR = "0x000000000000000000000000000000000000000A"
STAKE_ADDR  = "0x0000000000000000000000000000000000000001"


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.messages)


def _make_w3(coord_model_id: int):
    """Return a minimal web3 mock whose eth.contract().functions.modelId().call() returns coord_model_id."""
    def _contract(address, abi):
        return SimpleNamespace(
            functions=SimpleNamespace(
                modelId=lambda: SimpleNamespace(call=lambda: coord_model_id),
            )
        )
    return SimpleNamespace(eth=SimpleNamespace(contract=_contract))


class DummyCtxObj:
    def __init__(self, coord_model_id: int):
        self.console = DummyConsole()
        self._w3 = _make_w3(coord_model_id)

    def get_en_w3_account_console(self):
        return "local", self._w3, SimpleNamespace(address=COORD_ADDR), self.console

    def get_deployed_din_task_coordinator_contract(self, verbose=False, model_id=None, taskCoordinator_address=None):
        return SimpleNamespace(
            functions=SimpleNamespace(
                setDINTaskAuditorContract=lambda addr: ("set", addr),
            )
        )


@pytest.fixture(autouse=True)
def _patch_deploy(monkeypatch):
    """Stub out I/O so tests run without real artifacts, chain, or filesystem."""
    contract = SimpleNamespace(
        abi=[{"type": "constructor", "inputs": [
            {"type": kind} for kind in ("address", "address", "uint256")
        ]}],
        constructor=Mock(return_value="ctor"),
    )
    monkeypatch.setattr(deploy, "get_contract_instance", lambda path, net: contract)
    monkeypatch.setattr(
        deploy, "load_din_info",
        lambda: {"local": {"stake": STAKE_ADDR}},
    )
    monkeypatch.setattr(
        deploy, "resolve_task_coordinator_address",
        lambda net, addr, console: COORD_ADDR,
    )
    monkeypatch.setattr(deploy, "set_env_key", lambda *a, **kw: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    return contract


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_build_and_send_tx(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(contractAddress=AUDITOR_ADDR)

    monkeypatch.setattr(deploy, "build_and_send_tx", fake_build_and_send_tx)
    return calls


class TestModelIdGuard:
    def test_mismatch_sends_no_transaction(self, sent, _patch_deploy):
        ctx = SimpleNamespace(obj=DummyCtxObj(coord_model_id=0))

        with pytest.raises(typer.BadParameter, match="match the paired coordinator") as exc:
            deploy.task_auditor(
                ctx,
                artifact_path="dummy.json",
                task_coordinator=COORD_ADDR,
                model_id=1,
            )

        assert "--model-id" in str(exc.value)
        assert sent == [], "No transaction must be sent on a model-ID mismatch"
        _patch_deploy.constructor.assert_not_called()


    def test_match_sends_deployment_transaction(self, sent, _patch_deploy):
        ctx = SimpleNamespace(obj=DummyCtxObj(coord_model_id=1))

        deploy.task_auditor(
            ctx,
            artifact_path="dummy.json",
            task_coordinator=COORD_ADDR,
            model_id=1,
        )

        _patch_deploy.constructor.assert_called_once_with(STAKE_ADDR, COORD_ADDR, 1)
        assert len(sent) == 2, "Matching IDs deploy the auditor and pair it"
        assert sent[0][1] == "ctor"
        assert sent[1][1] == ("set", AUDITOR_ADDR)
