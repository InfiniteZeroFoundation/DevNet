import os
import time
import typer

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.utils import (build_and_send_tx, get_env_key, load_din_info,
                              resolve_task_coordinator_address, set_env_key)

# Deploy sub-app (for 'dincli modelowner deploy ...')
deploy_app = typer.Typer(help="Deploy task-level smart contracts")

@deploy_app.command()
def task_coordinator(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskCoordinator contract artifact JSON (Hardhat format). "),
):
    """
    Deploy the DINTaskCoordinator contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskCoordinator_contract = get_contract_instance(artifact_path, effective_network)
    
    # Resolve DINValidatorStake address
    din_info = load_din_info()
    if effective_network in din_info and "stake" in din_info[effective_network]:
        din_validator_stake_address = din_info[effective_network]["stake"]
    
    console.print(f"[bold green]Deploying DINTaskCoordinator on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake:[/cyan] {din_validator_stake_address}")
    
    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskCoordinator_contract.constructor(din_validator_stake_address),
        "Deploying DINTaskCoordinator",
        "DINTaskCoordinator contract deployed successfully",
        "Failed to deploy DINTaskCoordinator"
    )
    
    dintaskcoordinator_contract_address = tx_receipt.contractAddress
    
    console.print(f"[bold green]✓ DINTaskCoordinator contract deployed at:[/bold green] {dintaskcoordinator_contract_address}")
    
    set_env_key(effective_network.upper()+"_DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
    console.print(f"[green]✓ Saved DINTaskCoordinator address to {os.getcwd()}/.env as {effective_network.upper()}_DINTaskCoordinator_Contract_Address[/green]")

@deploy_app.command()
def task_auditor(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskAuditor contract artifact JSON (Hardhat format)."),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
):
    """
    Deploy the DINTaskAuditor contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    # Load contract instance
    DINTaskAuditor_contract = get_contract_instance(artifact_path, effective_network)
      
    din_info = load_din_info()
    if effective_network in din_info and "stake" in din_info[effective_network]:
        din_validator_stake_address = din_info[effective_network]["stake"]

    # Resolve DINTaskCoordinator address
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator, console
    )
    
    console.print(f"[bold green]Deploying DINTaskAuditor on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using DINValidatorStake address:[/cyan] {din_validator_stake_address}")
    console.print(f"[cyan]Using DINTaskCoordinator address:[/cyan] {task_coordinator_address}")
    
    tx_receipt = build_and_send_tx(
        ctx,
        DINTaskAuditor_contract.constructor(din_validator_stake_address, task_coordinator_address),
        "Deploying DINTaskAuditor",
        "DINTaskAuditor contract deployed successfully",
        "Failed to deploy DINTaskAuditor"
    )
    
    dintaskauditor_contract_address = tx_receipt.contractAddress
    
    console.print(f"[bold green]✓ DINTaskAuditor contract deployed at:[/bold green] {dintaskauditor_contract_address}")
    
    set_env_key(effective_network.upper() + "_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address", dintaskauditor_contract_address)
    console.print(f"[green]✓ Saved DINTaskAuditor address to {os.getcwd()}/.env as {effective_network.upper()}_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address[/green]")
    
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

