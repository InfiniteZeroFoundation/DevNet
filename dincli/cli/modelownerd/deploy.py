import os
import time
import typer
from web3.exceptions import ContractLogicError

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.utils import (build_and_send_tx, get_env_key, load_din_info,
                              resolve_task_coordinator_address, set_env_key)


def _task_constructor_args(contract, role, stake, *, coordinator=None,
                           model_id=None, registry=None):
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


# Deploy sub-app (for 'dincli modelowner deploy ...')
deploy_app = typer.Typer(help="Deploy task-level smart contracts")

@deploy_app.command()
def task_coordinator(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Task coordinator artifact JSON (Foundry or Hardhat)."),
    model_id: int = typer.Option(None, "--model-id", help="Anticipated registry ID; required by current Foundry artifacts."),
):
    """
    Deploy the DINTaskCoordinator contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    # Load contract instance
    DINTaskCoordinator_contract = get_contract_instance(artifact_path, effective_network)
    
    # Resolve DINValidatorStake address
    din_info = load_din_info()
    din_validator_stake_address = din_info.get(effective_network, {}).get("stake")
    if not din_validator_stake_address:
        raise typer.BadParameter("Configure the platform stake contract before deployment")
    
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

@deploy_app.command()
def task_auditor(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Task auditor artifact JSON (Foundry or Hardhat)."),
    model_id: int = typer.Option(None, "--model-id", help="Anticipated registry ID; must match paired coordinator."),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
):
    """
    Deploy the DINTaskAuditor contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    # Load contract instance
    DINTaskAuditor_contract = get_contract_instance(artifact_path, effective_network)
      
    din_info = load_din_info()
    din_validator_stake_address = din_info.get(effective_network, {}).get("stake")
    if not din_validator_stake_address:
        raise typer.BadParameter("Configure the platform stake contract before deployment")

    # Resolve DINTaskCoordinator address
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator, console
    )
    
    constructor_args = _task_constructor_args(
        DINTaskAuditor_contract, "auditor", din_validator_stake_address,
        coordinator=task_coordinator_address, model_id=model_id,
        registry=din_info.get(effective_network, {}).get("registry"),
    )
    if len(constructor_args) >= 3:
        model_id_abi = [{"type": "function", "name": "modelId", "inputs": [],
                         "outputs": [{"type": "uint256"}], "stateMutability": "view"}]
        paired = w3.eth.contract(address=task_coordinator_address, abi=model_id_abi)
        try:
            paired_model_id = paired.functions.modelId().call()
        except ContractLogicError as exc:
            raise typer.BadParameter(
                "Cannot read modelId() from the paired coordinator; verify the address "
                "and that it is a compatible task coordinator."
            ) from exc
        if paired_model_id != model_id:
            raise typer.BadParameter("--model-id must match the paired coordinator modelId()")

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

