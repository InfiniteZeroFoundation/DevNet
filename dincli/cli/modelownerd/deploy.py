import os
import time
from typing import Optional
import typer
from web3.exceptions import BadFunctionCallOutput, ContractLogicError

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.utils import (build_and_send_tx, load_din_info,
                              resolve_task_coordinator_address, set_env_key)

_COORDINATOR_DEPLOYMENT_ABI = [
    {"type": "function", "name": "modelId", "inputs": [],
     "outputs": [{"type": "uint256"}], "stateMutability": "view"},
    {"type": "function", "name": "taskProtocolVersion", "inputs": [],
     "outputs": [{"type": "uint256"}], "stateMutability": "pure"},
]


def _task_constructor_signature(contract, role):
    """Support explicit released task signatures; refuse unknown custom shapes."""
    constructors = [item for item in contract.abi if item.get("type") == "constructor"]
    signature = (
        tuple(item["type"] for item in constructors[0]["inputs"])
        if len(constructors) == 1 else ()
    )
    supported = {
        "coordinator": {("address",), ("address", "uint256")},
        "auditor": {("address", "address"), ("address", "address", "uint256"),
                    ("address", "address", "uint256", "address")},
    }
    if signature not in supported[role]:
        raise typer.BadParameter(f"Unsupported {role} constructor signature: {signature}")
    return signature


def _task_constructor_args(contract, role, stake, *, coordinator=None,
                           model_id=None, registry=None):
    signature = _task_constructor_signature(contract, role)
    args = [stake] if role == "coordinator" else [stake, coordinator]
    if "uint256" in signature:
        if model_id is None or model_id < 0 or model_id >= 2**256:
            raise typer.BadParameter("This artifact requires --model-id in the uint256 range")
        args.append(model_id)
    if role == "auditor" and len(signature) == 4:
        if not registry:
            raise typer.BadParameter("Configure the canonical platform registry for this network before deployment")
        args.append(registry)
    return args


def _require_din_info_address(effective_network, key, label, console):
    """Return din_info[network][key], or exit with a clear message if it's missing."""
    address = load_din_info().get(effective_network, {}).get(key)
    if not address:
        console.print(
            f"[bold red]Error:[/bold red] no {label} address ('{key}') in din_info for network "
            f"'{effective_network}'. Run `dincli system import-deployments` (or configure the network) first."
        )
        raise typer.Exit(1)
    return address


def _default_model_id_from_registry(ctx, console):
    """The ID the registry's next approval will assign: DINModelRegistry.totalModels() (0-based)."""
    registry = ctx.obj.get_deployed_din_registry_contract(verbose=False)
    model_id = registry.functions.totalModels().call()
    console.print(
        f"[yellow]⚠ --model-id not given; using DINModelRegistry.totalModels() = {model_id}, the ID the next "
        "approval assigns. This only holds if no other registration request is approved before yours.[/yellow]"
    )
    return model_id


def _set_din_token(ctx, contract, din_token_address, label):
    """Point a freshly deployed task contract at the platform DinToken (rewards and bonds need it)."""
    build_and_send_tx(
        ctx,
        contract.functions.setDinToken(din_token_address),
        f"Setting DinToken {din_token_address} on {label}",
        f"DinToken set on {label}",
        f"Failed to set DinToken on {label}",
    )


# Deploy sub-app (for 'dincli modelowner deploy ...')
deploy_app = typer.Typer(help="Deploy task-level smart contracts")

@deploy_app.command()
def task_coordinator(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Task coordinator artifact JSON (Foundry or Hardhat)."),
    model_id: Optional[int] = typer.Option(None, "--model-id", help="Anticipated registry ID (default: DINModelRegistry.totalModels())."),
):
    """
    Deploy the DINTaskCoordinator contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskCoordinator_contract = get_contract_instance(artifact_path, effective_network)

    # Resolve DINValidatorStake address
    din_validator_stake_address = _require_din_info_address(
        effective_network, "stake", "DinValidatorStake", console
    )

    signature = _task_constructor_signature(DINTaskCoordinator_contract, "coordinator")
    din_token_address = None
    if "uint256" in signature:
        din_token_address = _require_din_info_address(effective_network, "token", "DinToken", console)
        if model_id is None:
            model_id = _default_model_id_from_registry(ctx, console)

    console.print(f"[bold green]Deploying DINTaskCoordinator on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake:[/cyan] {din_validator_stake_address}")

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskCoordinator_contract.constructor(*_task_constructor_args(
            DINTaskCoordinator_contract, "coordinator", din_validator_stake_address,
            model_id=model_id,
        )),
        "Deploying DINTaskCoordinator",
        "DINTaskCoordinator contract deployed successfully",
        "Failed to deploy DINTaskCoordinator"
    )

    dintaskcoordinator_contract_address = tx_receipt.contractAddress

    console.print(f"[bold green]✓ DINTaskCoordinator contract deployed at:[/bold green] {dintaskcoordinator_contract_address}")

    set_env_key(effective_network.upper()+"_DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
    console.print(f"[green]✓ Saved DINTaskCoordinator address to {os.getcwd()}/.env as {effective_network.upper()}_DINTaskCoordinator_Contract_Address[/green]")

    if din_token_address:
        deployed = get_contract_instance(artifact_path, effective_network, dintaskcoordinator_contract_address)
        _set_din_token(ctx, deployed, din_token_address, "DINTaskCoordinator")

@deploy_app.command()
def task_auditor(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Task auditor artifact JSON (Foundry or Hardhat)."),
    model_id: Optional[int] = typer.Option(None, "--model-id", help="Model ID (default: paired coordinator modelId()); must match paired coordinator."),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
):
    """
    Deploy the DINTaskAuditor contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskAuditor_contract = get_contract_instance(artifact_path, effective_network)

    din_info = load_din_info()
    din_validator_stake_address = _require_din_info_address(
        effective_network, "stake", "DinValidatorStake", console
    )

    # Resolve DINTaskCoordinator address
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator, console
    )

    signature = _task_constructor_signature(DINTaskAuditor_contract, "auditor")
    registry_address = din_info.get(effective_network, {}).get("registry")
    if len(signature) == 4 and not registry_address:
        raise typer.BadParameter("Configure the canonical platform registry for this network before deployment")
    din_token_address = None
    if "uint256" in signature:
        if model_id is not None and (model_id < 0 or model_id >= 2**256):
            raise typer.BadParameter("This artifact requires --model-id in the uint256 range")
        din_token_address = _require_din_info_address(effective_network, "token", "DinToken", console)

    paired = w3.eth.contract(address=task_coordinator_address, abi=_COORDINATOR_DEPLOYMENT_ABI)
    if "uint256" in signature:
        # IDs select stake floors; both IDs and the one-shot pairing are immutable.
        try:
            paired_model_id = paired.functions.modelId().call()
        except (ContractLogicError, BadFunctionCallOutput) as exc:
            raise typer.BadParameter(
                "Cannot read modelId() from the paired coordinator; verify the address "
                "and that it is a compatible task coordinator."
            ) from exc
        if model_id is None:
            model_id = paired_model_id
            console.print(f"[cyan]--model-id not given; using the coordinator's modelId() = {model_id}[/cyan]")
        if paired_model_id != model_id:
            raise typer.BadParameter("--model-id must match the paired coordinator modelId()")

    constructor_args = _task_constructor_args(
        DINTaskAuditor_contract, "auditor", din_validator_stake_address,
        coordinator=task_coordinator_address, model_id=model_id, registry=registry_address,
    )

    if not w3.eth.get_code(task_coordinator_address):
        raise typer.BadParameter("The paired coordinator has no deployed code; verify --taskCoordinator")
    try:
        coordinator_version = paired.functions.taskProtocolVersion().call()
    except (ContractLogicError, BadFunctionCallOutput):
        # Released legacy coordinators have no version getter. Transport/RPC
        # failures still propagate, rather than silently taking the legacy path.
        coordinator_version = 0
    auditor_version = 1 if len(constructor_args) == 4 else 0
    if coordinator_version not in (0, 1) or coordinator_version != auditor_version:
        raise typer.BadParameter(
            "Incompatible task contract generations: coordinator protocol version "
            f"{coordinator_version}, auditor protocol version {auditor_version}. "
            "Deploy a matching task pair; auditor pairing is one-shot."
        )

    if len(constructor_args) == 2:
        # The pre-model-ID auditor also lacks the reward-pool interface used by
        # later coordinators. Keep the two released legacy families separate.
        try:
            paired.functions.modelId().call()
        except (ContractLogicError, BadFunctionCallOutput):
            pass
        else:
            raise typer.BadParameter(
                "Incompatible task contract generations: a coordinator with modelId() "
                "requires an auditor with a model ID. Deploy a matching task pair."
            )

    console.print(f"[bold green]Deploying DINTaskAuditor on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake address:[/cyan] {din_validator_stake_address}")
    console.print(f"[cyan]Using DINTaskCoordinator address:[/cyan] {task_coordinator_address}")

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskAuditor_contract.constructor(*constructor_args),
        "Deploying DINTaskAuditor",
        "DINTaskAuditor contract deployed successfully",
        "Failed to deploy DINTaskAuditor"
    )

    dintaskauditor_contract_address = tx_receipt.contractAddress

    console.print(f"[bold green]✓ DINTaskAuditor contract deployed at:[/bold green] {dintaskauditor_contract_address}")

    set_env_key(effective_network.upper() + "_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address", dintaskauditor_contract_address)
    console.print(f"[green]✓ Saved DINTaskAuditor address to {os.getcwd()}/.env as {effective_network.upper()}_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address[/green]")

    if din_token_address:
        deployed = get_contract_instance(artifact_path, effective_network, dintaskauditor_contract_address)
        _set_din_token(ctx, deployed, din_token_address, "DINTaskAuditor")

    # Set DINTaskAuditor in DINTaskCoordinator
    console.print("[cyan]Setting DINTaskAuditor in DINTaskCoordinator...[/cyan]")

    DINTaskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(verbose=True, model_id=None, taskCoordinator_address=task_coordinator_address)

    time.sleep(10)

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskCoordinator_contract.functions.setDINTaskAuditorContract(dintaskauditor_contract_address),
        "Setting DINTaskAuditor in DINTaskCoordinator",
        "DINTaskAuditor contract set in DINTaskCoordinator",
        "Failed to set DINTaskAuditor in DINTaskCoordinator"
    )

