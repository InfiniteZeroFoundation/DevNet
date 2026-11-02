"""
Regression tests for the task_auditor model-ID guard (PR No. 261 / issue No. 223 TP-3).

Before sending the deployment transaction, task_auditor() reads the coordinator's
immutable modelId() and rejects a mismatch. Both IDs select per-model stake floors
and pairing is one-shot, so a mismatched deploy can't be corrected without a full
redeployment.
"""
import time
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
    monkeypatch.setattr(
        deploy, "get_contract_instance",
        lambda path, net: SimpleNamespace(constructor=lambda *a: "ctor"),
    )
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


@pytest.fixture
def sent(monkeypatch):
    calls = []

    def fake_build_and_send_tx(*args, **kwargs):
        calls.append(args)
        return SimpleNamespace(contractAddress=AUDITOR_ADDR)

    monkeypatch.setattr(deploy, "build_and_send_tx", fake_build_and_send_tx)
    return calls


class TestModelIdGuard:
    def test_mismatch_sends_no_transaction(self, sent):
        ctx = SimpleNamespace(obj=DummyCtxObj(coord_model_id=0))

        with pytest.raises(typer.Exit) as exc:
            deploy.task_auditor(
                ctx,
                artifact_path="dummy.json",
                task_coordinator=COORD_ADDR,
                model_id=1,
            )

        assert exc.value.exit_code == 1
        assert sent == [], "No transaction must be sent on a model-ID mismatch"
        assert any(
            "does not match" in m or "mismatch" in m.lower()
            for m in ctx.obj.console.messages
        ), f"Expected mismatch error in output, got: {ctx.obj.console.messages}"

    def test_match_sends_deployment_transaction(self, sent):
        ctx = SimpleNamespace(obj=DummyCtxObj(coord_model_id=1))

        deploy.task_auditor(
            ctx,
            artifact_path="dummy.json",
            task_coordinator=COORD_ADDR,
            model_id=1,
        )

        assert len(sent) >= 1, "Deployment transaction must be sent when model IDs match"
