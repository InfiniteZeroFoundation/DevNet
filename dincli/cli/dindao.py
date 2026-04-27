import os
import time

import typer

from dincli.cli.contract_utils import get_contract_instance
from dincli.cli.utils import get_env_key, load_din_info, save_din_info

app = typer.Typer(help="Commands for DIN DAO")

registry_app = typer.Typer(help="Registry sub-app (for 'dincli dindao registry to interact with DINRegistry ...')")
deploy_app = typer.Typer(help="Deploy DIN smart contracts")

app.add_typer(deploy_app, name="deploy")
app.add_typer(registry_app, name="registry")

@deploy_app.command()
def din_coordinator(
    ctx: typer.Context,
    artifact_path: str = typer.Option(None, "--artifact", help="Path to contract artifact JSON (Hardhat format)")
):
    
    """
    Deploy the DIN Coordinator contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    DINCoordinator_contract = get_contract_instance(artifact_path, effective_network)
    
    tx_params = ctx.obj.get_tx_params()

    tx_params["gas"] = int(w3.eth.estimate_gas(DINCoordinator_contract.constructor().build_transaction(tx_params)) * 1.1)  # Add 10% buffer
    
    tx = DINCoordinator_contract.constructor().build_transaction(tx_params) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    console.print(f"[bold green]Deploying DIN Coordinator Contract ...[/bold green]")
   
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    dincoordinator_contract_address = tx_receipt.contractAddress
        
    console.print("DINCoordinator contract deployed at:", dincoordinator_contract_address)
    
    din_addresses = load_din_info()
    din_addresses[effective_network]["coordinator"] = dincoordinator_contract_address
    din_addresses[effective_network]["representative"] = account.address 
    save_din_info(din_addresses)

    taskCoordinator_contract = ctx.obj.get_deployed_din_coordinator_contract()
    
    dintoken_address = taskCoordinator_contract.functions.dinToken().call()
    console.print("DINtoken contract deployed at:", dintoken_address)
    din_addresses = load_din_info()
    din_addresses[effective_network]["token"] = dintoken_address
    save_din_info(din_addresses)


    
@deploy_app.command("din-validator-stake")
def din_validator_stake(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to contract artifact JSON (Hardhat/Brownie format)"),
    dinCoordinator: str  = typer.Option(None, "--dinCoordinator", help="the dinCoordinator asddress"),
    dinToken: str  = typer.Option(None, "--dinToken", help="the dinToken asddress"),
                                        
):
    
    """
    Deploy the DIN Validator Stake contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    DINValidatorStake_contract = get_contract_instance(artifact_path, effective_network)
    
    din_addresses = load_din_info()
    
    if dinCoordinator:
        dinCoordinator_address = dinCoordinator
    else:
        dinCoordinator_address = din_addresses[effective_network]["coordinator"]
        
    if dinToken:
        dinToken_address = dinToken
    else:
        dinToken_address = din_addresses[effective_network]["token"]
    
    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(DINValidatorStake_contract.constructor(dinToken_address, dinCoordinator_address).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
  
    tx = DINValidatorStake_contract.constructor(
        dinToken_address, 
        dinCoordinator_address
    ).build_transaction(tx_params) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    

    console.print(f"[bold green]Deploying DIN Validator Stake Contract ...[/bold green]")
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    DINValidatorStake_contract_address = tx_receipt.contractAddress
        
    console.print("DINValidatorStake contract deployed at:", DINValidatorStake_contract_address)
    
    din_addresses[effective_network]["stake"] = DINValidatorStake_contract_address

    save_din_info(din_addresses)
    
    deployed_DINValidatorStake_Contract = ctx.obj.get_deployed_din_stake_contract()
    
    
    DINCoordinator_Contract = ctx.obj.get_deployed_din_coordinator_contract()
    
    # add delay to allow the 
    time.sleep(10)


    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(DINCoordinator_Contract.functions.updateValidatorStakeContract(deployed_DINValidatorStake_Contract.address).build_transaction(tx_params)) * 1.1)  # Add 10% buffer

    tx = DINCoordinator_Contract.functions.updateValidatorStakeContract(deployed_DINValidatorStake_Contract.address).build_transaction(tx_params) 
        
    # Sign transaction
    signed_tx = account.sign_transaction(tx) 
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        console.print("[bold green] ✅ DinValidatorStake contract added to DINCoordinator contract successfully[/bold green]")
    else:
        console.print("[bold red] ❌ Failed to add DinValidatorStake contract to DINCoordinator contract[/bold red]")


@deploy_app.command("din-model-registry")
def deploy_din_model_registry(
    ctx: typer.Context,
    artifact_path: str = typer.Option(..., "--artifact", help="Path to contract artifact JSON (Hardhat/Brownie format)"),
    dinvalidatorstake: str = typer.Option(None, "--dinvalidatorstake", help="the dinvalidatorstake address"),
):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    DINModelRegistry_contract = get_contract_instance(artifact_path, effective_network)
    
    din_addresses = load_din_info()

    if dinvalidatorstake:
        dinValidatorStake_address = dinvalidatorstake
    else:
        dinValidatorStake_address = din_addresses[effective_network]["stake"]
    
    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(DINModelRegistry_contract.constructor(dinValidatorStake_address).build_transaction(tx_params)) * 1.1)  # Add 10% buffer

    tx = DINModelRegistry_contract.constructor(dinValidatorStake_address).build_transaction(tx_params) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)

    console.print(f"[bold green]Deploying DIN Model Registry...[/bold green]")  
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        DINModelRegistry_contract_address = tx_receipt.contractAddress
        console.print("[bold green] ✅ DINModelRegistry contract deployed at:[/bold green]", DINModelRegistry_contract_address)
    else:
        console.print("[bold red] ❌ Failed to deploy DINModelRegistry contract[/bold red]")
        raise typer.Exit(code=1)
    
    din_addresses[effective_network]["registry"] = DINModelRegistry_contract_address
    
    save_din_info(din_addresses)
    
@app.command(
    help="Add a slasher to the DIN SlasherRegistry contract."
    "You must specify either the task coordinator or the task auditor (from config) to be registered as the slasher."
    "The contract address can be provided explicitly or loaded from config."
)
def add_slasher(
    ctx: typer.Context,
    contract: str = typer.Option(None, "--contract", help="The contract address"),
    task_coordinator_flag: bool = typer.Option(
        False, "--taskCoordinator", 
        help="Use the default task coordinator address from config",
        is_flag=True,
    ),
    task_auditor_flag: bool = typer.Option(
        False, "--taskAuditor", 
        help="Use the default task auditor address from config",
        is_flag=True,
    ),

):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    DINCoordinator_Contract = ctx.obj.get_deployed_din_coordinator_contract()

    if contract:
        contract_address = contract
    elif  task_coordinator_flag:
        contract_address = get_env_key(effective_network.upper()+"_DINTaskCoordinator_Contract_Address")
        if not contract_address:
            typer.Exit(1)
        console.print(f"Using DINTaskCoordinator address: {contract_address} from env variable {effective_network.upper()}_DINTaskCoordinator_Contract_Address in {os.getcwd()}/.env")
    elif task_auditor_flag:
        task_coordinator_key = f"{effective_network.upper()}_DINTaskCoordinator_Contract_Address"
        task_coordinator_address = get_env_key(task_coordinator_key)

        if not task_coordinator_address:
            typer.Exit(1)

        contract_address = get_env_key(effective_network.upper()+"_"+task_coordinator_address+"_DINTaskAuditor_Contract_Address")
        if not contract_address:
            typer.Exit(1)
        console.print(f"Using DINTaskAuditor address: {contract_address} from env variable {effective_network.upper()}_{task_coordinator_address}_DINTaskAuditor_Contract_Address in {os.getcwd()}/.env")

    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(DINCoordinator_Contract.functions.addSlasherContract(contract_address).build_transaction(tx_params)) * 1.1)  # Add 10% buffer

    tx = DINCoordinator_Contract.functions.addSlasherContract(contract_address).build_transaction(tx_params)

    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        console.print("[bold green] ✓ Slasher contract added to DINCoordinator contract successfully[/bold green]")
    else:
        console.print("[bold red] X Failed to add Slasher contract to DINCoordinator contract[/bold red]")
        
    
    
@registry_app.command("total-models")
def total_models(ctx: typer.Context,
    ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    models_length = DINModelRegistry_Contract.functions.totalModels().call()

    console.print(f"[bold green]Total models: {models_length}[/bold green]")


@registry_app.command("update-proprietary-fee")
def update_proprietary_fee(ctx: typer.Context,
    amount: float = typer.Argument(..., help="Amount of ETH as proprietary fee in DIN model registry")
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    amount_wei = w3.to_wei(amount, 'ether')

    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(DINModelRegistry_Contract.functions.setProprietaryFee(amount_wei).build_transaction(tx_params)) * 1.1)  # Add 10% buffer

    tx = DINModelRegistry_Contract.functions.setProprietaryFee(amount_wei).build_transaction(tx_params)

    # Sign transaction
    signed_tx = account.sign_transaction(tx)

    console.print(f"[bold green]Updating proprietary fee to {amount} ETH in DINModelRegistry contract...[/bold green]")

    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if tx_receipt.status == 1:
        console.print("[bold green] ✓ Proprietary fee updated successfully[/bold green]")
    else:
        console.print("[bold red] X Failed to update proprietary fee[/bold red]")
