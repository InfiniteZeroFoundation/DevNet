import typer
import os
from rich import print
from rich.console import Console
from pathlib import Path
from dincli.utils import resolve_network, get_w3, load_account, load_din_info, save_din_info 
from dincli.contract_utils import  get_DINCoordinator_Instance, get_DINValidatorStake_Instance, get_contract_instance
from dotenv import dotenv_values, set_key


console = Console()

app = typer.Typer(help="Commands for DIN DAO")

# Deploy sub-app (for 'dincli dindao deploy ...')
deploy_app = typer.Typer(help="Deploy DIN smart contracts")

app.add_typer(deploy_app, name="deploy")

@deploy_app.command()
def din_coordinator(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    artifact_path: str = typer.Option(None, "--artifact", help="Path to contract artifact JSON (Hardhat/Brownie format)")
):
    
    """
    Deploy the DIN Coordinator contract.
    """
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    DINCoordinator_contract = get_DINCoordinator_Instance(artifact_path, effective_network)
    
    # Load account
    account = load_account()  # returns LocalAccount

    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)    
    tx = DINCoordinator_contract.constructor().build_transaction({
        "from": account.address,        # ← MUST be string address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    }) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    print(f"[bold green]Deploying DIN Coordinator on network:[/bold green] {effective_network}")
   
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    dincoordinator_contract_address = tx_receipt.contractAddress
        
    print("DINCoordinator contract deployed at:", dincoordinator_contract_address)
    
     
    din_addresses = load_din_info()
    din_addresses[effective_network]["coordinator"] = tx_receipt.contractAddress
    din_addresses[effective_network]["representative"] = account.address 
    
    save_din_info(din_addresses)
    
    deployed_DINCoordinatorContract = get_DINCoordinator_Instance(artifact_path, effective_network, dincoordinator_contract_address)
    
    dintoken_address = deployed_DINCoordinatorContract.functions.dintoken().call()
    
    print("DINtoken contract deployed at:", dintoken_address)
    
    din_addresses = load_din_info()
    din_addresses[effective_network]["token"] = dintoken_address
    save_din_info(din_addresses)
    
    

@deploy_app.command()
def din_validator_stake(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    artifact_path: str = typer.Option(..., "--artifact", help="Path to contract artifact JSON (Hardhat/Brownie format)"),
    dinCoordinator: str  = typer.Option(None, "--dinCoordinator", help="the dinCoordinator asddress"),
    dinToken: str  = typer.Option(None, "--dinToken", help="the dinToken asddress"),
                                        
):
    
    """
    Deploy the DIN Validator Stake contract.
    """
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    DINValidatorStake_contract = get_DINValidatorStake_Instance(artifact_path, effective_network)
    
    # Load account
    account = load_account()  # returns LocalAccount
    
    
    din_addresses = load_din_info()
    
    if dinCoordinator:
        dinCoordinator_address = dinCoordinator
    else:
        dinCoordinator_address = din_addresses[effective_network]["coordinator"]
        
    if dinToken:
        dinToken_address = dinToken
    else:
        dinToken_address = din_addresses[effective_network]["token"]
    
    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)    
    tx = DINValidatorStake_contract.constructor(
            dinToken_address, 
            dinCoordinator_address
        ).build_transaction({
        "from": account.address,        # ← MUST be string address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    }) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    DINValidatorStake_contract_address = tx_receipt.contractAddress
        
    print("DINValidatorStake contract deployed at:", DINValidatorStake_contract_address)
    
    print(f"[bold green]Deploying DIN DINValidatorStake on network:[/bold green] {effective_network}")
    
    dinvalidatorstake_address = tx_receipt.contractAddress
    din_addresses[effective_network]["stake"] = dinvalidatorstake_address

    
    save_din_info(din_addresses)
    
    deployed_DINValidatorStake_Contract = get_DINValidatorStake_Instance(artifact_path, effective_network, DINValidatorStake_contract_address)
    
    
    dincoordinator_abi_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    deployed_dincoordinator = get_DINCoordinator_Instance(dincoordinator_abi_path, effective_network, dinCoordinator_address)
    
    
    nonce = w3.eth.get_transaction_count(account.address)    
    
    tx = deployed_dincoordinator.functions.add_dinvalidatorStakeContract(dinvalidatorstake_address).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": nonce,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
        
    # Sign transaction
    signed_tx = account.sign_transaction(tx) 
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        print("DinValidatorStake contract added to DINCoordinator contract successfully")
        
    else:
        print("Failed to add DinValidatorStake contract to DINCoordinator contract")


@deploy_app.command("din-model-registry")
def deploy_din_model_registry(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    artifact_path: str = typer.Option(..., "--artifact", help="Path to contract artifact JSON (Hardhat/Brownie format)"),
    dinvalidatorstake: str = typer.Option(None, "--dinvalidatorstake", help="the dinvalidatorstake address"),
):
    
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    DINModelRegistry_contract = get_contract_instance(artifact_path, effective_network)
    
    # Load account
    account = load_account()  # returns LocalAccount

    din_addresses = load_din_info()

    if dinvalidatorstake:
        dinValidatorStake_address = dinvalidatorstake
    else:
        dinValidatorStake_address = din_addresses[effective_network]["stake"]
    
    
    
    nonce = w3.eth.get_transaction_count(account.address)    
    tx = DINModelRegistry_contract.constructor(dinValidatorStake_address).build_transaction({
        "from": account.address,        # ← MUST be string address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    }) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    DINModelRegistry_contract_address = tx_receipt.contractAddress

    print(f"[bold green]Deploying DIN DINModelRegistry on network:[/bold green] {effective_network}")
    
    print("DINModelRegistry contract deployed at:", DINModelRegistry_contract_address)
    
    dinmodelregistry_address = tx_receipt.contractAddress
    din_addresses[effective_network]["registry"] = dinmodelregistry_address
    
    save_din_info(din_addresses)
    
    deployed_DINModelRegistry_Contract = get_contract_instance(artifact_path, effective_network, DINModelRegistry_contract_address)
    
    
    


# ```
# dincli dindao add-slasher \
#   --contract <address> \
#   --network <net>
# ```
@app.command(
    help="Add a slasher to the DIN SlasherRegistry contract."
    "You must specify either the task coordinator or the task auditor (from config) to be registered as the slasher."
    "The contract address can be provided explicitly or loaded from config."
    "Network defaults to 'local' if not specified.")
def add_slasher(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
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
    
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)

    artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"


    din_addresses = load_din_info()
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 
    
    deployed_dincoordinator = get_DINCoordinator_Instance(artifact_path, effective_network, dincoordinator_address)
    
    # Load account
    account = load_account()  

    env_config = dotenv_values(".env")

    if contract:
        contract_address = contract
    elif  task_coordinator_flag:
        contract_address = env_config.get("DINTaskCoordinator_Contract_Address")
        if not contract_address:
            console.print("[bold red] X DINTaskCoordinator_Contract_Address not found in .env file[/bold red]")
            exit(1)
        console.print(f"Using DINTaskCoordinator address: {contract_address} from env variable DINTaskCoordinator_Contract_Address in {os.getcwd()}/.env")
    elif task_auditor_flag:
        contract_address = env_config.get("DINTaskAuditor_Contract_Address")
        if not contract_address:
            console.print("[bold red] X DINTaskAuditor_Contract_Address not found in .env file[/bold red]")
            exit(1)
        console.print(f"Using DINTaskAuditor address: {contract_address} from env variable DINTaskAuditor_Contract_Address in {os.getcwd()}/.env")
    

    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)    
    tx = deployed_dincoordinator.functions.add_slasher_contract(contract_address).build_transaction({
        "from": account.address,        # ← MUST be string address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    }) 
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)  
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        console.print("[bold green] ✓ Slasher contract added to DINCoordinator contract successfully[/bold green]")
        if task_coordinator_flag:
            set_key(".env", "DINTaskCoordinatorISslasher", "True")
        elif task_auditor_flag:
            set_key(".env", "DINTaskAuditorISslasher", "True")
    else:
        console.print("[bold red] X Failed to add Slasher contract to DINCoordinator contract[/bold red]")
        
    
    

    