"""Local constructor compatibility checks; no chain or wallet used."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer

from dincli.cli.modelownerd import deploy


def artifact(*types):
    return SimpleNamespace(abi=[{"type": "constructor", "inputs": [
        {"type": kind} for kind in types
    ]}])


@pytest.mark.parametrize("role,types,expected", [
    ("coordinator", ("address",), ["stake"]),
    ("coordinator", ("address", "uint256"), ["stake", 0]),
    ("auditor", ("address", "address"), ["stake", "coordinator"]),
    ("auditor", ("address", "address", "uint256"), ["stake", "coordinator", 0]),
    ("auditor", ("address", "address", "uint256", "address"),
     ["stake", "coordinator", 0, "registry"]),
])
def test_supported_constructor_shapes(role, types, expected):
    assert deploy._task_constructor_args(
        artifact(*types), role, "stake", coordinator="coordinator",
        model_id=0, registry="registry",
    ) == expected


@pytest.mark.parametrize("model_id", [None, -1, 2**256])
def test_current_artifact_requires_valid_model_id(model_id):
    with pytest.raises(typer.BadParameter, match="--model-id"):
        deploy._task_constructor_args(artifact("address", "uint256"),
                                      "coordinator", "stake", model_id=model_id)


def test_new_auditor_requires_configured_registry():
    with pytest.raises(typer.BadParameter, match="canonical platform registry"):
        deploy._task_constructor_args(artifact("address", "address", "uint256", "address"),
                                      "auditor", "stake", model_id=0)


@pytest.mark.parametrize("types", [(), ("uint256",), ("address", "address", "address")])
def test_unknown_signature_rejected(types):
    with pytest.raises(typer.BadParameter, match="Unsupported"):
        deploy._task_constructor_args(artifact(*types), "auditor", "stake", model_id=0)


def test_auditor_command_supplies_canonical_registry_and_checks_pair(monkeypatch):
    contract = Mock(abi=artifact("address", "address", "uint256", "address").abi)
    paired = Mock()
    paired.functions.modelId.return_value.call.return_value = 7
    w3 = Mock()
    w3.eth.contract.return_value = paired
    obj = Mock()
    obj.get_en_w3_account_console.return_value = ("local", w3, Mock(), Mock())
    ctx = SimpleNamespace(obj=obj)
    monkeypatch.setattr(deploy, "get_contract_instance", lambda *a: contract)
    monkeypatch.setattr(deploy, "load_din_info", lambda: {"local": {"stake": "stake", "registry": "registry"}})
    monkeypatch.setattr(deploy, "resolve_task_coordinator_address", lambda *a: "coordinator")
    send = Mock(return_value=SimpleNamespace(contractAddress="auditor"))
    monkeypatch.setattr(deploy, "build_and_send_tx", send)
    monkeypatch.setattr(deploy, "set_env_key", Mock())
    monkeypatch.setattr(deploy.time, "sleep", Mock())
    deploy.task_auditor(ctx, "artifact.json", 7, "coordinator")
    contract.constructor.assert_called_once_with("stake", "coordinator", 7, "registry")
    assert send.call_count == 2
    contract.constructor.reset_mock()
    send.reset_mock()
    with pytest.raises(typer.BadParameter, match="match the paired"):
        deploy.task_auditor(ctx, "artifact.json", 8, "coordinator")
    contract.constructor.assert_not_called()
    send.assert_not_called()
