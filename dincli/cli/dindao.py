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


def build_and_send_tx(ctx, contract_function, action_msg, success_msg, error_msg):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    tx_params = ctx.obj.get_tx_params()
    try:
        tx_params["gas"] = int(w3.eth.estimate_gas(contract_function.build_transaction(tx_params)) * 1.1)
    except Exception as e:
        console.print(f"[bold red] X Transaction estimation failed: {e}[/bold red]")
        raise typer.Exit(1)
        
    tx = contract_function.build_transaction(tx_params)
    signed_tx = account.sign_transaction(tx)
    console.print(f"[bold green]{action_msg}...[/bold green]")
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if tx_receipt.status == 1:
        console.print(f"[bold green] ✓ {success_msg}[/bold green]")
    else:
        console.print(f"[bold red] X {error_msg}[/bold red]")
        raise typer.Exit(1)

@registry_app.command("approve-model")
def approve_model(ctx: typer.Context, request_id: int = typer.Argument(..., help="Model request ID to approve")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.approveModel(request_id),
        f"Approving model request {request_id}",
        f"Model request {request_id} approved successfully",
        f"Failed to approve model request {request_id}"
    )

@registry_app.command("reject-model")
def reject_model(ctx: typer.Context, request_id: int = typer.Argument(..., help="Model request ID to reject")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.rejectModel(request_id),
        f"Rejecting model request {request_id}",
        f"Model request {request_id} rejected successfully",
        f"Failed to reject model request {request_id}"
    )

@registry_app.command("approve-manifest-update")
def approve_manifest_update(ctx: typer.Context, request_id: int = typer.Argument(..., help="Manifest update request ID to approve")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.approveManifestUpdate(request_id),
        f"Approving manifest update request {request_id}",
        f"Manifest update request {request_id} approved successfully",
        f"Failed to approve manifest update request {request_id}"
    )

@registry_app.command("reject-manifest-update")
def reject_manifest_update(ctx: typer.Context, request_id: int = typer.Argument(..., help="Manifest update request ID to reject")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.rejectManifestUpdate(request_id),
        f"Rejecting manifest update request {request_id}",
        f"Manifest update request {request_id} rejected successfully",
        f"Failed to reject manifest update request {request_id}"
    )

@registry_app.command("disable-model")
def disable_model(ctx: typer.Context, model_id: int = typer.Argument(..., help="Model ID to disable")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.disableModel(model_id),
        f"Disabling model {model_id}",
        f"Model {model_id} disabled successfully",
        f"Failed to disable model {model_id}"
    )

@registry_app.command("enable-model")
def enable_model(ctx: typer.Context, model_id: int = typer.Argument(..., help="Model ID to enable")):
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.enableModel(model_id),
        f"Enabling model {model_id}",
        f"Model {model_id} enabled successfully",
        f"Failed to enable model {model_id}"
    )

@registry_app.command("set-open-source-fee")
def set_open_source_fee(ctx: typer.Context, amount: float = typer.Argument(..., help="Amount of ETH")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    amount_wei = w3.to_wei(amount, 'ether')
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setOpenSourceFee(amount_wei),
        f"Updating open source fee to {amount} ETH",
        "Open source fee updated successfully",
        "Failed to update open source fee"
    )

@registry_app.command("set-proprietary-fee")
def set_proprietary_fee(ctx: typer.Context, amount: float = typer.Argument(..., help="Amount of ETH")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    amount_wei = w3.to_wei(amount, 'ether')
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setProprietaryFee(amount_wei),
        f"Updating proprietary fee to {amount} ETH",
        "Proprietary fee updated successfully",
        "Failed to update proprietary fee"
    )

@registry_app.command("set-open-source-update-fee")
def set_open_source_update_fee(ctx: typer.Context, amount: float = typer.Argument(..., help="Amount of ETH")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    amount_wei = w3.to_wei(amount, 'ether')
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setOpenSourceUpdateFee(amount_wei),
        f"Updating open source update fee to {amount} ETH",
        "Open source update fee updated successfully",
        "Failed to update open source update fee"
    )

@registry_app.command("set-proprietary-update-fee")
def set_proprietary_update_fee(ctx: typer.Context, amount: float = typer.Argument(..., help="Amount of ETH")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    amount_wei = w3.to_wei(amount, 'ether')
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setProprietaryUpdateFee(amount_wei),
        f"Updating proprietary update fee to {amount} ETH",
        "Proprietary update fee updated successfully",
        "Failed to update proprietary update fee"
    )

@registry_app.command("set-fees")
def set_fees(
    ctx: typer.Context,
    open_source: float = typer.Option(..., "--open-source", help="Open source fee in ETH"),
    proprietary: float = typer.Option(..., "--proprietary", help="Proprietary fee in ETH"),
    open_source_update: float = typer.Option(..., "--open-source-update", help="Open source update fee in ETH"),
    proprietary_update: float = typer.Option(..., "--proprietary-update", help="Proprietary update fee in ETH")
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setFees(
            w3.to_wei(open_source, 'ether'),
            w3.to_wei(proprietary, 'ether'),
            w3.to_wei(open_source_update, 'ether'),
            w3.to_wei(proprietary_update, 'ether')
        ),
        "Updating all fees atomically",
        "All fees updated successfully",
        "Failed to update all fees"
    )

@registry_app.command("withdraw-fees")
def withdraw_fees(ctx: typer.Context, to: str = typer.Argument(..., help="Address to withdraw fees to")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    target_address = w3.to_checksum_address(to)
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.withdrawFees(target_address),
        f"Withdrawing fees to {target_address}",
        "Fees withdrawn successfully",
        "Failed to withdraw fees"
    )

@registry_app.command("set-dao-admin")
def set_dao_admin(ctx: typer.Context, new_admin: str = typer.Argument(..., help="New DAO admin address")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    target_address = w3.to_checksum_address(new_admin)
    build_and_send_tx(
        ctx, 
        DINModelRegistry_Contract.functions.setDAOAdmin(target_address),
        f"Setting DAO admin to {target_address}",
        "DAO admin set successfully",
        "Failed to set DAO admin"
    )

@registry_app.command("unprocessed-requests")
def unprocessed_requests(ctx: typer.Context, req_type: str = typer.Option(None, "--type", "-t", help="Type of request: 'model' or 'manifest'")):
    """Get all unprocessed Model and ManifestUpdate requests"""
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    if req_type == "model" or req_type is None:
        console.print("[bold cyan]Unprocessed Model Requests:[/bold cyan]")

        totalModelRequests = DINModelRegistry_Contract.functions.totalModelRequests().call()
        found_model = False
        for idx in range(totalModelRequests):
            req = DINModelRegistry_Contract.functions.modelRequests(idx).call()
            # req[6] is 'processed'
            if not req[6]:
                console.print(f"  [green]Request ID {idx}[/green] - Requester: {req[0]}")
                found_model = True
        if not found_model:
            console.print("  [gray]No unprocessed model requests[/gray]")

    elif req_type == "manifest" or req_type is None:
        console.print("\n[bold cyan]Unprocessed Manifest Update Requests:[/bold cyan]")
        totalManifestRequests = DINModelRegistry_Contract.functions.totalManifestRequests().call()
        found_manifest = False
        for idx in range(totalManifestRequests):
            req = DINModelRegistry_Contract.functions.manifestRequests(idx).call()
            # req[4] is 'processed'
            if not req[4]:
                console.print(f"  [green]Request ID {idx}[/green] - Model ID: {req[0]}, Requester: {req[2]}")
                found_manifest = True
        if not found_manifest:
            console.print("  [gray]No unprocessed manifest update requests[/gray]")

    else:
        console.print("[bold red]Invalid request type. Must be 'model' or 'manifest'.[/bold red]")
        raise typer.Exit(1)

@registry_app.command("explore-request")
def explore_request(
    ctx: typer.Context,
    req_type: str = typer.Option(..., "--type", "-t", help="Type of request: 'model' or 'manifest'"),
    request_id: int = typer.Argument(..., help="Request ID to explore")
):
    """Explore a specific ModelRequest or ManifestUpdateRequest"""
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()
    
    from dincli.services.cid_utils import get_cid_from_bytes32

    if req_type.lower() == 'model':
        try:
            req = DINModelRegistry_Contract.functions.modelRequests(request_id).call()
            console.print(f"[bold cyan]Model Request {request_id}:[/bold cyan]")
            console.print(f"  Requester: {req[0]}")
            console.print(f"  Is Open Source: {req[1]}")
            
            try:
                manifest_cid = get_cid_from_bytes32(req[2].hex())
            except Exception:
                manifest_cid = req[2].hex()
                
            console.print(f"  Manifest CID: {manifest_cid}")
            console.print(f"  Task Coordinator: {req[3]}")
            console.print(f"  Task Auditor: {req[4]}")
            console.print(f"  Fee Paid: {w3.from_wei(req[5], 'ether')} ETH")
            console.print(f"  Processed: {req[6]}")
            console.print(f"  Approved: {req[7]}")
            import datetime
            console.print(f"  Created At: {datetime.datetime.fromtimestamp(req[8])}")
        except Exception as e:
            console.print(f"[bold red]Failed to retrieve Model Request {request_id}. It may not exist.[/bold red]")
            
    elif req_type.lower() == 'manifest':
        try:
            req = DINModelRegistry_Contract.functions.manifestRequests(request_id).call()
            console.print(f"[bold cyan]Manifest Update Request {request_id}:[/bold cyan]")
            console.print(f"  Model ID: {req[0]}")
            
            try:
                new_manifest_cid = get_cid_from_bytes32(req[1].hex())
            except Exception:
                new_manifest_cid = req[1].hex()
                
            console.print(f"  New Manifest CID: {new_manifest_cid}")
            console.print(f"  Requester: {req[2]}")
            console.print(f"  Fee Paid: {w3.from_wei(req[3], 'ether')} ETH")
            console.print(f"  Processed: {req[4]}")
            console.print(f"  Approved: {req[5]}")
        except Exception as e:
            console.print(f"[bold red]Failed to retrieve Manifest Update Request {request_id}. It may not exist.[/bold red]")
    else:
        console.print("[bold red]Invalid request type. Must be 'model' or 'manifest'.[/bold red]")
        raise typer.Exit(1)

