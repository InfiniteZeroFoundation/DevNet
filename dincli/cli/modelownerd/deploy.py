import os
import time
from typing import Optional

import typer

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.utils import (build_and_send_tx, get_env_key, load_din_info,
                              resolve_task_coordinator_address, set_env_key)

_MODEL_ID_ABI = [
    {"inputs": [], "name": "modelId", "outputs": [{"name": "", "type": "uint256"}],
     "stateMutability": "view", "type": "function"},
]

# Deploy sub-app (for 'dincli modelowner deploy ...')
deploy_app = typer.Typer(help="Deploy task-level smart contracts")


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

@deploy_app.command()
def task_coordinator(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskCoordinator contract artifact JSON (Foundry format)."),
    model_id: Optional[int] = typer.Option(
        None, "--model-id",
        help="Model ID DinModelRegistry will assign to this model (default: DINModelRegistry.totalModels()).",
    ),
):
    """
    Deploy the DINTaskCoordinator contract and set its DinToken.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskCoordinator_contract = get_contract_instance(artifact_path, effective_network)

    din_validator_stake_address = _require_din_info_address(effective_network, "stake", "DinValidatorStake", console)
    din_token_address = _require_din_info_address(effective_network, "token", "DinToken", console)
    if model_id is None:
        model_id = _default_model_id_from_registry(ctx, console)

    console.print(f"[bold green]Deploying DINTaskCoordinator on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake:[/cyan] {din_validator_stake_address}")
    console.print(f"[cyan]Model ID:[/cyan] {model_id}")

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskCoordinator_contract.constructor(din_validator_stake_address, model_id),
        "Deploying DINTaskCoordinator",
        "DINTaskCoordinator contract deployed successfully",
        "Failed to deploy DINTaskCoordinator"
    )
    
    dintaskcoordinator_contract_address = tx_receipt.contractAddress
    
    console.print(f"[bold green]✓ DINTaskCoordinator contract deployed at:[/bold green] {dintaskcoordinator_contract_address}")
    
    set_env_key(effective_network.upper()+"_DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
    console.print(f"[green]✓ Saved DINTaskCoordinator address to {os.getcwd()}/.env as {effective_network.upper()}_DINTaskCoordinator_Contract_Address[/green]")

    deployed_coordinator = get_contract_instance(artifact_path, effective_network, dintaskcoordinator_contract_address)
    _set_din_token(ctx, deployed_coordinator, din_token_address, "DINTaskCoordinator")

@deploy_app.command()
def task_auditor(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskAuditor contract artifact JSON (Foundry format)."),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    model_id: Optional[int] = typer.Option(
        None, "--model-id",
        help="Model ID DinModelRegistry will assign to this model (default: the coordinator's modelId()).",
    ),
):
    """
    Deploy the DINTaskAuditor contract, link it to the coordinator and set its DinToken.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskAuditor_contract = get_contract_instance(artifact_path, effective_network)

    din_validator_stake_address = _require_din_info_address(effective_network, "stake", "DinValidatorStake", console)
    din_token_address = _require_din_info_address(effective_network, "token", "DinToken", console)

    # Resolve DINTaskCoordinator address
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator, console
    )

    # Guard: --model-id must match the coordinator's immutable modelId().
    # Both IDs select per-model stake floors; pairing is one-shot and irreversible.
    coord_view = w3.eth.contract(address=task_coordinator_address, abi=_MODEL_ID_ABI)
    coord_model_id = coord_view.functions.modelId().call()
    if model_id is None:
        model_id = coord_model_id
        console.print(f"[cyan]--model-id not given; using the coordinator's modelId() = {model_id}[/cyan]")
    if coord_model_id != model_id:
        console.print(
            f"[bold red]Error:[/bold red] --model-id {model_id} does not match "
            f"coordinator modelId() {coord_model_id}. "
            "Aborting — pairing is one-shot and the IDs are immutable."
        )
        raise typer.Exit(1)

    console.print(f"[bold green]Deploying DINTaskAuditor on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake address:[/cyan] {din_validator_stake_address}")
    console.print(f"[cyan]Using DINTaskCoordinator address:[/cyan] {task_coordinator_address}")
    console.print(f"[cyan]Model ID:[/cyan] {model_id}")

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskAuditor_contract.constructor(din_validator_stake_address, task_coordinator_address, model_id),
        "Deploying DINTaskAuditor",
        "DINTaskAuditor contract deployed successfully",
        "Failed to deploy DINTaskAuditor"
    )
    
    dintaskauditor_contract_address = tx_receipt.contractAddress
    
    console.print(f"[bold green]✓ DINTaskAuditor contract deployed at:[/bold green] {dintaskauditor_contract_address}")
    
    set_env_key(effective_network.upper() + "_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address", dintaskauditor_contract_address)
    console.print(f"[green]✓ Saved DINTaskAuditor address to {os.getcwd()}/.env as {effective_network.upper()}_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address[/green]")

    deployed_auditor = get_contract_instance(artifact_path, effective_network, dintaskauditor_contract_address)
    _set_din_token(ctx, deployed_auditor, din_token_address, "DINTaskAuditor")

    # Set DINTaskAuditor in DINTaskCoordinator
    console.print(f"[cyan]Setting DINTaskAuditor in DINTaskCoordinator...[/cyan]")
    
    DINTaskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(verbose=True, model_id=None, taskCoordinator_address=task_coordinator_address)

    time.sleep(10)

    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskCoordinator_contract.functions.setDINTaskAuditorContract(dintaskauditor_contract_address),
        "Setting DINTaskAuditor in DINTaskCoordinator",
        "DINTaskAuditor contract set in DINTaskCoordinator",
        "Failed to set DINTaskAuditor in DINTaskCoordinator"
    )

