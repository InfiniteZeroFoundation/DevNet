"""
`model-owner deploy task-coordinator` / `task-auditor` (task_061026_21 Part C, Deploy):

- `--model-id` defaults to DINModelRegistry.totalModels() for the coordinator,
  and to the coordinator's modelId() for the auditor;
- both deploys call setDinToken(din_info token) on the new contract;
- a missing `stake` (or `token`) din_info entry exits cleanly instead of
  raising NameError (or KeyError), before any transaction is sent.
"""
import time
from types import SimpleNamespace

import pytest
import typer

from dincli.cli.modelownerd import deploy

COORD_ADDR = "0x000000000000000000000000000000000000000C"
AUDITOR_ADDR = "0x000000000000000000000000000000000000000A"
STAKE_ADDR = "0x0000000000000000000000000000000000000001"
TOKEN_ADDR = "0x0000000000000000000000000000000000000002"


class DummyConsole:
    def __init__(self):
        self.messages = []

    def print(self, *args, **kwargs):
        self.messages.append(" ".join(str(a) for a in args))

    def text(self):
        return "\n".join(self.messages)


class Call(tuple):
    """A contract call as (name, *args); doubles as the tx passed to build_and_send_tx."""


def _contract(address=None):
    return SimpleNamespace(
        address=address,
        constructor=lambda *a: Call(("constructor", *a)),
        functions=SimpleNamespace(
            setDinToken=lambda addr: Call(("setDinToken", address, addr)),
            setDINTaskAuditorContract=lambda addr: Call(("setDINTaskAuditorContract", addr)),
        ),
    )


class DummyCtxObj:
    def __init__(self, total_models=3, coord_model_id=3):
        self.console = DummyConsole()
        self._total_models = total_models
        self.w3 = SimpleNamespace(eth=SimpleNamespace(
            contract=lambda address, abi: SimpleNamespace(functions=SimpleNamespace(
                modelId=lambda: SimpleNamespace(call=lambda: coord_model_id),
            )),
        ))

    def get_en_w3_account_console(self, model_id=None):
        return "local", self.w3, SimpleNamespace(address="0xowner"), self.console

    def get_deployed_din_registry_contract(self, verbose=True):
        return SimpleNamespace(functions=SimpleNamespace(
            totalModels=lambda: SimpleNamespace(call=lambda: self._total_models),
        ))

    def get_deployed_din_task_coordinator_contract(self, verbose=False, model_id=None, taskCoordinator_address=None):
        return _contract(taskCoordinator_address)


@pytest.fixture
def din_info(monkeypatch):
    info = {"local": {"stake": STAKE_ADDR, "token": TOKEN_ADDR}}
    monkeypatch.setattr(deploy, "load_din_info", lambda: info)
    return info["local"]


@pytest.fixture
def sent(monkeypatch, din_info):
    calls = []

    def fake_build_and_send_tx(ctx, fn, *args, **kwargs):
        calls.append(fn)
        if fn[0] == "constructor":
            # coordinator ctor has 2 args, auditor ctor 3
            return SimpleNamespace(contractAddress=COORD_ADDR if len(fn) == 3 else AUDITOR_ADDR)
        return SimpleNamespace(status=1)

    monkeypatch.setattr(deploy, "build_and_send_tx", fake_build_and_send_tx)
    monkeypatch.setattr(deploy, "get_contract_instance", lambda path, net, address=None: _contract(address))
    monkeypatch.setattr(deploy, "resolve_task_coordinator_address", lambda net, addr, console: COORD_ADDR)
    monkeypatch.setattr(deploy, "set_env_key", lambda *a, **kw: None)
    monkeypatch.setattr(time, "sleep", lambda _: None)
    return calls


def _ctx(**kw):
    return SimpleNamespace(obj=DummyCtxObj(**kw))


class TestCoordinatorDeploy:
    def test_model_id_defaults_to_total_models_with_warning(self, sent):
        ctx = _ctx(total_models=5)
        deploy.task_coordinator(ctx, artifact_path="c.json", model_id=None)
        assert sent[0] == ("constructor", STAKE_ADDR, 5)
        assert "totalModels() = 5" in ctx.obj.console.text()

    def test_explicit_model_id_skips_registry(self, sent):
        ctx = _ctx(total_models=5)
        deploy.task_coordinator(ctx, artifact_path="c.json", model_id=2)
        assert sent[0] == ("constructor", STAKE_ADDR, 2)
        assert "totalModels()" not in ctx.obj.console.text()

    def test_sets_din_token_on_new_coordinator(self, sent):
        deploy.task_coordinator(_ctx(), artifact_path="c.json", model_id=0)
        assert sent == [("constructor", STAKE_ADDR, 0), ("setDinToken", COORD_ADDR, TOKEN_ADDR)]

    def test_missing_stake_exits_before_any_tx(self, sent, din_info):
        del din_info["stake"]
        ctx = _ctx()
        with pytest.raises(typer.Exit) as exc:
            deploy.task_coordinator(ctx, artifact_path="c.json", model_id=0)
        assert exc.value.exit_code == 1
        assert sent == []
        assert "DinValidatorStake" in ctx.obj.console.text()


class TestAuditorDeploy:
    def test_model_id_defaults_to_coordinator_model_id(self, sent):
        deploy.task_auditor(_ctx(coord_model_id=4), artifact_path="a.json", task_coordinator=COORD_ADDR, model_id=None)
        assert sent[0] == ("constructor", STAKE_ADDR, COORD_ADDR, 4)

    def test_sets_din_token_then_links_coordinator(self, sent):
        deploy.task_auditor(_ctx(coord_model_id=0), artifact_path="a.json", task_coordinator=COORD_ADDR, model_id=0)
        assert sent == [
            ("constructor", STAKE_ADDR, COORD_ADDR, 0),
            ("setDinToken", AUDITOR_ADDR, TOKEN_ADDR),
            ("setDINTaskAuditorContract", AUDITOR_ADDR),
        ]

    def test_missing_token_exits_before_any_tx(self, sent, din_info):
        del din_info["token"]
        ctx = _ctx(coord_model_id=0)
        with pytest.raises(typer.Exit):
            deploy.task_auditor(ctx, artifact_path="a.json", task_coordinator=COORD_ADDR, model_id=0)
        assert sent == []
        assert "DinToken" in ctx.obj.console.text()

    def test_missing_stake_exits_before_any_tx(self, sent, din_info):
        del din_info["stake"]
        with pytest.raises(typer.Exit):
            deploy.task_auditor(_ctx(coord_model_id=0), artifact_path="a.json", task_coordinator=COORD_ADDR, model_id=0)
        assert sent == []
