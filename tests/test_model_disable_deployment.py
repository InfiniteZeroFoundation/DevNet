"""Local constructor compatibility checks; no chain or wallet used."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import typer
from web3.exceptions import BadFunctionCallOutput, ContractLogicError

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
    w3.eth.get_code.return_value = b"\x60"
    paired.functions.taskProtocolVersion.return_value.call.side_effect = (
        lambda: 1 if len(contract.abi[0]["inputs"]) == 4 else 0
    )
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
    command.paired.functions.taskProtocolVersion.return_value.call.assert_called_once_with()
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
@pytest.mark.parametrize("error_type", [ContractLogicError, BadFunctionCallOutput])
def test_auditor_command_reports_model_id_revert(auditor_command, with_registry, error_type):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if with_registry else ())
    command.contract.abi = artifact(*types).abi
    revert = error_type("incompatible getter")
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


def test_legacy_auditor_deploys_when_model_id_getter_is_absent(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address").abi
    command.paired.functions.modelId.return_value.call.side_effect = ContractLogicError("no getter")

    deploy.task_auditor(command.ctx, "artifact.json", None, "coordinator")

    command.contract.constructor.assert_called_once_with("stake", "coordinator")
    command.w3.eth.contract.assert_called_once()
    command.paired.functions.taskProtocolVersion.return_value.call.assert_called_once_with()
    command.paired.functions.modelId.return_value.call.assert_called_once_with()
    assert command.send.call_count == 2
    command.write_env.assert_called_once_with(
        "LOCAL_coordinator_DINTaskAuditor_Contract_Address", "auditor",
    )


@pytest.mark.parametrize("role", ["coordinator", "auditor"])
@pytest.mark.parametrize("config", [{}, {"local": {}}])
def test_missing_stake_sends_no_transaction(auditor_command, monkeypatch, role, config):
    command = auditor_command
    monkeypatch.setattr(deploy, "load_din_info", lambda: config)
    command.contract.abi = artifact("address", "uint256").abi

    with pytest.raises(typer.BadParameter, match="platform stake"):
        if role == "coordinator":
            deploy.task_coordinator(command.ctx, artifact_path="artifact.json", model_id=7)
        else:
            deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                                task_coordinator="coordinator")

    assert_no_deployment(command)


def test_missing_registry_sends_no_transaction(auditor_command, monkeypatch):
    command = auditor_command
    command.contract.abi = artifact("address", "address", "uint256", "address").abi
    monkeypatch.setattr(deploy, "load_din_info", lambda: {"local": {"stake": "stake"}})

    with pytest.raises(typer.BadParameter, match="canonical platform registry"):
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                            task_coordinator="coordinator")

    command.w3.eth.contract.assert_not_called()
    assert_no_deployment(command)


@pytest.mark.parametrize("types,model_id,expected", [
    (("address",), None, ("stake",)),
    (("address", "uint256"), 0, ("stake", 0)),
    (("address", "uint256"), 2**256 - 1, ("stake", 2**256 - 1)),
])
def test_coordinator_command_deploys_supported_shapes(auditor_command, types, model_id, expected):
    command = auditor_command
    command.contract.abi = artifact(*types).abi

    deploy.task_coordinator(command.ctx, artifact_path="artifact.json", model_id=model_id)

    command.contract.constructor.assert_called_once_with(*expected)
    command.send.assert_called_once()
    assert command.send.call_args.args[1] is command.contract.constructor.return_value
    command.write_env.assert_called_once_with("LOCAL_DINTaskCoordinator_Contract_Address", "auditor")
    command.w3.eth.contract.assert_not_called()


@pytest.mark.parametrize("model_id", [None, -1, 2**256])
@pytest.mark.parametrize("role", ["coordinator", "auditor"])
def test_invalid_id_sends_no_transaction(auditor_command, role, model_id):
    command = auditor_command
    types = ("address", "uint256") if role == "coordinator" else ("address", "address", "uint256", "address")
    command.contract.abi = artifact(*types).abi

    with pytest.raises(typer.BadParameter, match="--model-id"):
        if role == "coordinator":
            deploy.task_coordinator(command.ctx, artifact_path="artifact.json", model_id=model_id)
        else:
            deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=model_id,
                                task_coordinator="coordinator")

    command.w3.eth.contract.assert_not_called()
    assert_no_deployment(command)


@pytest.mark.parametrize("types,version", [
    (("address", "address"), 1),
    (("address", "address", "uint256"), 1),
    (("address", "address", "uint256", "address"), 0),
    (("address", "address", "uint256", "address"), 2),
    (("address", "address", "uint256"), 2),
])
def test_incompatible_generations_send_no_transaction(auditor_command, types, version):
    command = auditor_command
    command.contract.abi = artifact(*types).abi
    command.paired.functions.taskProtocolVersion.return_value.call.side_effect = None
    command.paired.functions.taskProtocolVersion.return_value.call.return_value = version

    with pytest.raises(typer.BadParameter, match="Incompatible task contract generations"):
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                            task_coordinator="coordinator")

    assert_no_deployment(command)


@pytest.mark.parametrize("error_type", [ContractLogicError, BadFunctionCallOutput])
@pytest.mark.parametrize("guarded", [False, True])
def test_missing_version_getter_only_allows_legacy_pairs(auditor_command, error_type, guarded):
    command = auditor_command
    types = ("address", "address", "uint256") + (("address",) if guarded else ())
    command.contract.abi = artifact(*types).abi
    command.paired.functions.taskProtocolVersion.return_value.call.side_effect = error_type("no getter")

    if guarded:
        with pytest.raises(typer.BadParameter, match="Incompatible task contract generations"):
            deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                                task_coordinator="coordinator")
        assert_no_deployment(command)
    else:
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                            task_coordinator="coordinator")
        command.contract.constructor.assert_called_once_with("stake", "coordinator", 7)
        assert command.send.call_count == 2


@pytest.mark.parametrize("error_type", [ConnectionError, ValueError])
def test_version_read_rpc_errors_do_not_fall_back_to_legacy(auditor_command, error_type):
    command = auditor_command
    command.contract.abi = artifact("address", "address", "uint256").abi
    error = error_type("RPC failure")
    command.paired.functions.taskProtocolVersion.return_value.call.side_effect = error

    with pytest.raises(error_type) as caught:
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=7,
                            task_coordinator="coordinator")

    assert caught.value is error
    assert_no_deployment(command)


def test_legacy_auditor_rejects_coordinator_without_code(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address").abi
    command.w3.eth.get_code.return_value = b""

    with pytest.raises(typer.BadParameter, match="no deployed code"):
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=None,
                            task_coordinator="coordinator")

    command.paired.functions.taskProtocolVersion.assert_not_called()
    assert_no_deployment(command)


def test_two_argument_auditor_rejects_previous_model_id_coordinator(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address").abi
    command.paired.functions.modelId.return_value.call.return_value = 7

    with pytest.raises(typer.BadParameter, match="requires an auditor with a model ID"):
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=None,
                            task_coordinator="coordinator")

    assert_no_deployment(command)


def test_legacy_capability_rpc_error_does_not_deploy(auditor_command):
    command = auditor_command
    command.contract.abi = artifact("address", "address").abi
    command.paired.functions.modelId.return_value.call.side_effect = ConnectionError("RPC failure")

    with pytest.raises(ConnectionError):
        deploy.task_auditor(command.ctx, artifact_path="artifact.json", model_id=None,
                            task_coordinator="coordinator")

    assert_no_deployment(command)
