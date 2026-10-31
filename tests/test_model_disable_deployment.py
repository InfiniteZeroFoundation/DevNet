"""Local constructor compatibility checks; no chain or wallet used."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from web3.exceptions import ContractLogicError

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


@pytest.fixture
def auditor_command(monkeypatch):
    contract = Mock()
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
    write_env = Mock()
    sleep = Mock()
    monkeypatch.setattr(deploy, "set_env_key", write_env)
    monkeypatch.setattr(deploy.time, "sleep", sleep)
    return SimpleNamespace(
        contract=contract, paired=paired, w3=w3, ctx=ctx, send=send,
        write_env=write_env, sleep=sleep,
    )


def assert_no_deployment(command):
    command.contract.constructor.assert_not_called()
    command.send.assert_not_called()
    command.write_env.assert_not_called()
    command.ctx.obj.get_deployed_din_task_coordinator_contract.assert_not_called()
    command.sleep.assert_not_called()


@pytest.mark.parametrize("with_registry", [False, True])
def test_auditor_command_checks_pair_and_deploys(auditor_command, with_registry):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if with_registry else ())
    command.contract.abi = artifact(*types).abi

    deploy.task_auditor(command.ctx, "artifact.json", 7, "coordinator")

    expected = ["stake", "coordinator", 7] + (["registry"] if with_registry else [])
    command.contract.constructor.assert_called_once_with(*expected)
    command.paired.functions.modelId.assert_called_once_with()
    command.paired.functions.modelId.return_value.call.assert_called_once_with()
    assert command.w3.eth.contract.call_args.kwargs["address"] == "coordinator"
    assert command.send.call_count == 2
    assert command.send.call_args_list[0].args[1] is command.contract.constructor.return_value
    setter = command.ctx.obj.get_deployed_din_task_coordinator_contract.return_value
    setter.functions.setDINTaskAuditorContract.assert_called_once_with("auditor")
    assert command.send.call_args_list[1].args[1] is setter.functions.setDINTaskAuditorContract.return_value
    command.write_env.assert_called_once_with(
        "LOCAL_coordinator_DINTaskAuditor_Contract_Address", "auditor",
    )
    command.sleep.assert_called_once_with(10)


@pytest.mark.parametrize("with_registry", [False, True])
def test_auditor_command_rejects_model_id_mismatch(auditor_command, with_registry):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if with_registry else ())
    command.contract.abi = artifact(*types).abi

    with pytest.raises(typer.BadParameter, match="match the paired"):
        deploy.task_auditor(command.ctx, "artifact.json", 8, "coordinator")

    assert_no_deployment(command)


@pytest.mark.parametrize("with_registry", [False, True])
def test_auditor_command_reports_model_id_revert(auditor_command, with_registry):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if with_registry else ())
    command.contract.abi = artifact(*types).abi
    revert = ContractLogicError("execution reverted")
    command.paired.functions.modelId.return_value.call.side_effect = revert

    with pytest.raises(typer.BadParameter) as caught:
        deploy.task_auditor(command.ctx, "artifact.json", 7, "coordinator")

    assert str(caught.value) == (
        "Cannot read modelId() from the paired coordinator; verify the address "
        "and that it is a compatible task coordinator."
    )
    assert caught.value.__cause__ is revert
    assert_no_deployment(command)


@pytest.mark.parametrize("with_registry", [False, True])
@pytest.mark.parametrize("error_type", [ConnectionError, ValueError])
def test_auditor_command_preserves_unrelated_read_errors(auditor_command, with_registry, error_type):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if with_registry else ())
    command.contract.abi = artifact(*types).abi
    error = error_type("modelId read failed")
    command.paired.functions.modelId.return_value.call.side_effect = error

    with pytest.raises(error_type) as caught:
        deploy.task_auditor(command.ctx, "artifact.json", 7, "coordinator")

    assert caught.value is error
    assert_no_deployment(command)


def test_auditor_command_does_not_wrap_contract_creation_error(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address", "uint256").abi
    error = ContractLogicError("contract creation failed")
    command.w3.eth.contract.side_effect = error

    with pytest.raises(ContractLogicError) as caught:
        deploy.task_auditor(command.ctx, "artifact.json", 7, "coordinator")

    assert caught.value is error
    assert_no_deployment(command)


def test_legacy_auditor_deploys_without_model_id_read(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address").abi
    command.paired.functions.modelId.return_value.call.side_effect = AssertionError(
        "legacy deployment must not read modelId"
    )

    deploy.task_auditor(command.ctx, "artifact.json", None, "coordinator")

    command.contract.constructor.assert_called_once_with("stake", "coordinator")
    command.w3.eth.contract.assert_not_called()
    command.paired.functions.modelId.assert_not_called()
    assert command.send.call_count == 2
    command.write_env.assert_called_once_with(
        "LOCAL_coordinator_DINTaskAuditor_Contract_Address", "auditor",
    )
