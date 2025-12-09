import typer
from rich import print
from rich.table import Table
from typing import Optional
from rich.console import Console
from pathlib import Path
from dotenv import dotenv_values, set_key, get_key, unset_key
from dincli.utils import resolve_network, get_w3, load_account, load_din_info, load_usdt_config, GIstatestrToIndex, GIstateToStr
from dincli.contract_utils import get_contract_instance

from dincli.system import connect_wallet
from dincli.services.modelowner import getGenesisModelIpfs, getscoreforGM, create_audit_testDataCIDs

app = typer.Typer(help="Commands for Model Owners in DIN.")

# Deploy sub-app (for 'dincli modelowner deploy ...')
deploy_app = typer.Typer(help="Deploy task-level smart contracts")

model_app = typer.Typer(help="Model-level commands")
gi_app = typer.Typer(help="Global iteration commands")
aggregation_app = typer.Typer(help="Aggregation commands")
lms_app = typer.Typer(help="Local Model Submission commands")
auditor_batches_app = typer.Typer(help="Auditor Batches commands")
lms_evaluation_app = typer.Typer(help="Local Model Submission Evaluation commands")
slash_app = typer.Typer(help="Slash commands")

app.add_typer(deploy_app, name="deploy")
app.add_typer(model_app, name="model")
app.add_typer(gi_app, name="gi")
app.add_typer(aggregation_app, name="aggregation")
app.add_typer(lms_app, name="lms")
app.add_typer(auditor_batches_app, name="auditor-batches")
app.add_typer(lms_evaluation_app, name="lms-evaluation")
app.add_typer(slash_app, name="slash")

reg_app = typer.Typer(help="Registration commands for a Global Iteration")
gi_app.add_typer(reg_app, name="reg")

t1_app = typer.Typer(help="Tier 1 commands")
t2_app = typer.Typer(help="Tier 2 commands")
aggregation_app.add_typer(t1_app, name="T1")
aggregation_app.add_typer(t2_app, name="T2")

console = Console()

@deploy_app.command()
def task_coordinator(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskCoordinator contract artifact JSON (Hardhat format). "),
    din_validator_stake: str = typer.Option(None, "--din-validator-stake", help="DINValidatorStake contract address. If not provided, reads from .env or din_info.json")
):
    """
    Deploy the DINTaskCoordinator contract.
    """
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)

    # Load contract instance
    DINTaskCoordinator_contract = get_contract_instance(artifact_path, effective_network)
    
    # Load account
    account = load_account()
    
    # Resolve DINValidatorStake address
    if din_validator_stake:
        din_validator_stake_address = din_validator_stake
    else:
        # Try .env first
        env_config = dotenv_values(".env")
        din_validator_stake_address = env_config.get("DINValidatorStake_Contract_Address")
        
        # If not in .env, try din_info.json
        if not din_validator_stake_address:
            din_info = load_din_info()
            if effective_network in din_info and "stake" in din_info[effective_network]:
                din_validator_stake_address = din_info[effective_network]["stake"]
        
        if not din_validator_stake_address:
            print("[red]Error:[/red] DINValidatorStake contract address not found.")
            print("[yellow]Please provide --din-validator-stake or ensure it's set in .env or din_info.json[/yellow]")
            raise typer.Exit(1)
    
    print(f"[bold green]Deploying DINTaskCoordinator on network:[/bold green] {effective_network}")
    print(f"[cyan]Using DINValidatorStake:[/cyan] {din_validator_stake_address}")
    
    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)
    
    # Build deployment transaction
    tx = DINTaskCoordinator_contract.constructor(din_validator_stake_address).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(2.5 * 3000000),  # Match FastAPI route
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    dintaskcoordinator_contract_address = tx_receipt.contractAddress
    
    print(f"[bold green]✓ DINTaskCoordinator contract deployed at:[/bold green] {dintaskcoordinator_contract_address}")
    
    # Save to .env
    env_path = Path(".env")
    if env_path.exists():
        set_key(".env", "DINTaskCoordinator_Contract_Address", dintaskcoordinator_contract_address)
        print(f"[green]✓ Saved DINTaskCoordinator address to .env[/green]")
    else:
        print(f"[yellow]Warning:[/yellow] .env file not found. Address not saved.")
        print(f"[yellow]Please manually add to .env:[/yellow] DINTaskCoordinator_Contract_Address={dintaskcoordinator_contract_address}")


@deploy_app.command()
def task_auditor(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    artifact_path: str = typer.Option(..., "--artifact", help="Path to DINTaskAuditor contract artifact JSON (Hardhat format)."),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    usdt_contract: str = typer.Option(None, "--usdt-contract", help="USDT contract address. If not provided, reads from .env or din_info.json"),
    din_validator_stake: str = typer.Option(None, "--din-validator-stake", help="DINValidatorStake contract address. If not provided, reads from .env or din_info.json"),
    task_coordinator_artifact: str = typer.Option(None, "--task-coordinator-artifact", help="Path to DINTaskCoordinator artifact (needed to call setDINTaskAuditorContract). If not provided, tries to find it automatically")
):
    """
    Deploy the DINTaskAuditor contract.
    """
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    # Load contract instance
    DINTaskAuditor_contract = get_contract_instance(artifact_path, effective_network)
    
    # Load account
    account = load_account()
    
    # Resolve USDT contract address
    if usdt_contract:
        usdt_contract_address = usdt_contract
    else:
        env_config = dotenv_values(".env")


        usdt_contract_address = env_config.get(effective_network.upper() + "_USDT_Contract_Address")
        if not usdt_contract_address:

            usdt_config = load_usdt_config()
            if effective_network in usdt_config and "usdt" in usdt_config[effective_network]:
                usdt_contract_address = usdt_config[effective_network]["usdt"]

            if not usdt_contract_address:
                print("[red]Error:[/red] USDT contract address not found.")
                print("[yellow]Please provide --usdt-contract or ensure " + effective_network.upper() + "_USDT_Contract_Address is set in .env[/yellow]")
                raise typer.Exit(1)
    
    # Resolve DINValidatorStake address
    if din_validator_stake:
        din_validator_stake_address = din_validator_stake
    else:
        env_config = dotenv_values(".env")
        din_validator_stake_address = env_config.get(effective_network.upper() + "_DINValidatorStake_Contract_Address")
        
        # If not in .env, try din_info.json
        if not din_validator_stake_address:
            din_info = load_din_info()
            if effective_network in din_info and "stake" in din_info[effective_network]:
                din_validator_stake_address = din_info[effective_network]["stake"]
        
        if not din_validator_stake_address:
            print("[red]Error:[/red] DINValidatorStake contract address not found.")
            print("[yellow]Please provide --din-validator-stake or ensure " + effective_network.upper() + "_DINValidatorStake_Contract_Address is set in .env or din_info.json[/yellow]")
            raise typer.Exit(1)

    # Resolve DINTaskCoordinator address
    if task_coordinator:
        task_coordinator_address = task_coordinator
    else:
        env_config = dotenv_values(".env")
        task_coordinator_address = env_config.get("DINTaskCoordinator_Contract_Address")
        
        if not task_coordinator_address:
            print("[red]Error:[/red] DINTaskCoordinator contract address not found.")
            print("[yellow]Please provide --task-coordinator or ensure DINTaskCoordinator_Contract_Address is set in .env[/yellow]")
            raise typer.Exit(1)
    
    print(f"[bold green]Deploying DINTaskAuditor on network:[/bold green] {effective_network}")
    print(f"[cyan]Using USDT address:[/cyan] {usdt_contract_address}")
    print(f"[cyan]Using DINValidatorStake address:[/cyan] {din_validator_stake_address}")
    print(f"[cyan]Using DINTaskCoordinator address:[/cyan] {task_coordinator_address}")
    
     
    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)
    
    # Build deployment transaction
    tx = DINTaskAuditor_contract.constructor(
        usdt_contract_address,
        din_validator_stake_address,
        task_coordinator_address
    ).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(2.5 * 3000000),  # Match FastAPI route
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    dintaskauditor_contract_address = tx_receipt.contractAddress
    
    print(f"[bold green]✓ DINTaskAuditor contract deployed at:[/bold green] {dintaskauditor_contract_address}")
    
    # Save to .env
    env_path = Path(".env")
    if env_path.exists():
        set_key(".env", "DINTaskAuditor_Contract_Address", dintaskauditor_contract_address)
        print(f"[green]✓ Saved DINTaskAuditor address to .env[/green]")
    else:
        print(f"[yellow]Warning:[/yellow] .env file not found. Address not saved.")
        print(f"[yellow]Please manually add to .env:[/yellow] DINTaskAuditor_Contract_Address={dintaskauditor_contract_address}")
    
    # Set DINTaskAuditor in DINTaskCoordinator
    print(f"[cyan]Setting DINTaskAuditor in DINTaskCoordinator...[/cyan]")
    
    # Resolve DINTaskCoordinator artifact path
    if task_coordinator_artifact is None:
        # Try to find artifact file
        task_coordinator_artifact = Path(__file__).parent /"abis"/"DINTaskCoordinator.json"
        if not task_coordinator_artifact.exists():
            print(f"[yellow]Warning:[/yellow] DINTaskCoordinator artifact not found at {task_coordinator_artifact}")
            print(f"[yellow]Skipping setDINTaskAuditorContract call on DINTaskCoordinator. Please call it manually.[/yellow]")
            return dintaskauditor_contract_address
    
    # Load DINTaskCoordinator contract instance
    DINTaskCoordinator_contract = get_contract_instance(str(task_coordinator_artifact), effective_network, task_coordinator_address)
    
    # Get nonce for the setDINTaskAuditorContract call
    nonce = w3.eth.get_transaction_count(account.address)
    
    # Build transaction to set DINTaskAuditor in DINTaskCoordinator
    tx = DINTaskCoordinator_contract.functions.setDINTaskAuditorContract(dintaskauditor_contract_address).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(2.5 * 3000000),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        print(f"[bold green]✓ DINTaskAuditor contract set in DINTaskCoordinator[/bold green]")
    else:
        print(f"[red]Error:[/red] Failed to set DINTaskAuditor in DINTaskCoordinator")
    
    return dintaskauditor_contract_address
    
    
@app.command()
def deposit_reward_in_dintask_auditor(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    amount: int = typer.Option(..., "--amount", help="Amount of rewards to deposit in USDT"),
    dintask_auditor: str = typer.Option(None, "--dintask-auditor", help="DINTaskAuditor contract address"),
    usdt_contract: str = typer.Option(None, "--usdt-contract", help="USDT contract address. If not provided, reads from .env or usdt_config.json")
):
    """
    Deposit rewards into the DINTaskAuditor contract.
    """
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    # Load account
    account = load_account()
    
    # Resolve USDT contract address
    if usdt_contract:
        usdt_address = usdt_contract
    else:
        env_config = dotenv_values(".env")
        usdt_address = env_config.get(effective_network.upper() + "_USDT_Contract_Address")
        
        if not usdt_address:
            usdt_config = load_usdt_config()
            if effective_network in usdt_config and "usdt" in usdt_config[effective_network]:
                usdt_address = usdt_config[effective_network]["usdt"]
                
        if not usdt_address:
            print("[red]Error:[/red] USDT contract address not found.")
            print("[yellow]Please provide --usdt-contract or ensure " + effective_network.upper() + "_USDT_Contract_Address is set in .env[/yellow]")
            raise typer.Exit(1)

    # Resolve DINTaskAuditor address
    if dintask_auditor:
        dintask_auditor_address = dintask_auditor
    else:
        env_config = dotenv_values(".env")
        dintask_auditor_address = env_config.get("DINTaskAuditor_Contract_Address")
        
        if not dintask_auditor_address:
            print("[red]Error:[/red] DINTaskAuditor contract address not found.")
            print("[yellow]Please provide --dintask-auditor or ensure DINTaskAuditor_Contract_Address is set in .env[/yellow]")
            raise typer.Exit(1)

    print(f"[bold green]Depositing rewards on network:[/bold green] {effective_network}")
    print(f"[cyan]Using USDT address:[/cyan] {usdt_address}")
    print(f"[cyan]Using DINTaskAuditor address:[/cyan] {dintask_auditor_address}")
    print(f"[cyan]Amount:[/cyan] {amount}")

    # Load USDT contract (ERC20)
    # We need a generic ERC20 ABI or just the USDT ABI. 
    # Assuming DinToken.json is an ERC20 compliant token which we can use for ABI.
    # Or we can use a minimal ABI for approve.
    
    # Minimal ERC20 ABI (enough for approve + decimals + balanceOf)
    erc20_abi = [
        {
            "constant": True,
            "inputs": [],
            "name": "decimals",
            "outputs": [{"name": "", "type": "uint8"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
            "constant": True,
            "inputs": [{"name": "owner", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "payable": False,
            "stateMutability": "view",
            "type": "function",
        },
        {
        "constant": True,
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
        },
        {
            "constant": False,
            "inputs": [
                {"name": "spender", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "name": "approve",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        
        # --- Added: transfer ---
        {
            "constant": False,
            "inputs": [
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "name": "transfer",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        },
        # --- Added: transferFrom ---
        {
            "constant": False,
            "inputs": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
            ],
            "name": "transferFrom",
            "outputs": [{"name": "", "type": "bool"}],
            "payable": False,
            "stateMutability": "nonpayable",
            "type": "function",
        }
    ]

    
    usdt_contract_instance = w3.eth.contract(address=usdt_address, abi=erc20_abi)

    # Get decimals
    decimals = usdt_contract_instance.functions.decimals().call()

    amount_wei = int(amount * (10 ** decimals))

    sender_balance = usdt_contract_instance.functions.balanceOf(account.address).call()

    if sender_balance < amount_wei:
        human_balance = sender_balance / (10 ** decimals)
        console.print(f"[red]Error:[/red] Insufficient USDT balance.")
        console.print(f"[yellow]Available: {human_balance:.6f} USDT | Requested: {amount} USDT[/yellow]")
        raise typer.Exit(1)

    # Load DINTaskAuditor contract
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    if not artifact_path.exists():
         print(f"[red]Error:[/red] DINTaskAuditor artifact not found at {artifact_path}")
         raise typer.Exit(1)

    DINTaskAuditor_contract = get_contract_instance(str(artifact_path), effective_network, dintask_auditor_address)

    # --- Print summary ---
    console.print(f"[bold green]Depositing {amount} USDT on network:[/bold green] {effective_network}")
    console.print(f"[cyan]USDT contract:[/cyan] {usdt_address}")
    console.print(f"[cyan]DINTaskAuditor:[/cyan] {dintask_auditor_address}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")


    current_allowance = usdt_contract_instance.functions.allowance(account.address, dintask_auditor_address).call()

    if current_allowance > 0  and current_allowance != amount_wei:
        console.print(f"[yellow]Resetting existing allowance of {current_allowance / (10 ** decimals):.6f} USDT to 0 for USDT compatibility...[/yellow]")
        reset_tx = usdt_contract_instance.functions.approve(dintask_auditor_address, 0).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": 60000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
        })
        signed = account.sign_transaction(reset_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Reset tx: {tx_hash.hex()}[/dim]")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ Reset allowance[/green]")

    if current_allowance != amount_wei or current_allowance == 0:
        # --- Step 1: Approve ---
        console.print(f"[cyan]Approving DINTaskAuditor to spend {amount} USDT...[/cyan]")
        nonce = w3.eth.get_transaction_count(account.address)
        approve_tx = usdt_contract_instance.functions.approve(dintask_auditor_address, amount_wei).build_transaction({
            "from": account.address,
            "nonce": nonce,
            "gas": 100_000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
        })
        signed = account.sign_transaction(approve_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Approve tx:[/dim] {tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ Approval confirmed[/green]")


    owner = DINTaskAuditor_contract.functions.owner().call()
    console.print(f"[cyan]Owner:[/cyan] {owner}")
    mock_addr_in_contract = DINTaskAuditor_contract.functions.mockusdt().call()
    console.print(f"[cyan]mockusdt in contract:[/cyan] {mock_addr_in_contract}")
    console.print(f"[cyan]USDT address used in CLI:[/cyan] {usdt_address}")

    usdt_balance = usdt_contract_instance.functions.balanceOf(account.address).call()
    console.print(f"[cyan]USDT balance:[/cyan] {usdt_balance / (10 ** decimals):.6f}")
    console.print(f"[cyan]USDT allowance:[/cyan] {usdt_contract_instance.functions.allowance(account.address, dintask_auditor_address).call() / (10 ** decimals):.6f}")



    # --- Step 2: Deposit ---
    console.print("[cyan]Calling depositReward...[/cyan]")
    nonce = w3.eth.get_transaction_count(account.address)
    deposit_tx = DINTaskAuditor_contract.functions.depositReward(amount_wei).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 200_000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    signed = account.sign_transaction(deposit_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Deposit tx:[/dim] {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status != 1:
        console.print("[red]✗ Deposit transaction reverted[/red]")
        raise typer.Exit(1)

    # --- Final balances (optional but useful for CLI feedback) ---
    final_sender = usdt_contract_instance.functions.balanceOf(account.address).call() / (10 ** decimals)
    final_auditor = usdt_contract_instance.functions.balanceOf(dintask_auditor_address).call() / (10 ** decimals)
    eth_balance = w3.from_wei(w3.eth.get_balance(account.address), "ether")

    console.print("[bold green]✓ Rewards deposited successfully![/bold green]")
    console.print(f"[cyan]Your USDT balance:[/cyan] {final_sender:.6f}")
    console.print(f"[cyan]Auditor USDT balance:[/cyan] {final_auditor:.6f}")
    console.print(f"[cyan]Your ETH balance:[/cyan] {eth_balance:.6f} ETH")


    owner = DINTaskAuditor_contract.functions.owner().call()
    console.print(f"[cyan]Owner:[/cyan] {owner}")
    return


@app.command()
def add_slasher(
    task_coordinator_flag: bool = typer.Option(False, "--taskCoordinator", help="Add task coordinator as slasher"),
    task_auditor_flag: bool = typer.Option(False, "--taskAuditor", help="Add task auditor as slasher"),
    network: str = typer.Option(None, "--network", help="Network to use"),
    contract_address: str = typer.Option(None, "--contract", help="Contract address to use DIN Task Coordinator"),
):

    effective_network = resolve_network(network)
    if not effective_network:
        console.print("[red]Error:[/red] Invalid network specified")
        raise typer.Exit(1)

    w3 = get_w3(effective_network)
    if not w3:
        console.print("[red]Error:[/red] Failed to connect to network")
        raise typer.Exit(1)

    account = load_account()


    env_config = dotenv_values(".env")

    if task_coordinator_flag and task_auditor_flag:
        console.print("[red]Error:[/red] Cannot add both task coordinator and task auditor as slashers")
        raise typer.Exit(1)
    elif not task_coordinator_flag and not task_auditor_flag:
        console.print("[red]Error:[/red] You must specify either --taskCoordinator or --taskAuditor")
        raise typer.Exit(1)


    if not contract_address:
        
        contract_address = env_config["DINTaskCoordinator_Contract_Address"]

        if not contract_address:
            console.print("[red]Error:[/red] Contract address for DIN Task Coordinator not found in .env")
            raise typer.Exit(1)


    # --- Print summary ---
    console.print(f"[bold green]Adding slasher on network:[/bold green] {effective_network}")
    console.print(f"[cyan]DIN Task Coordinator Contract:[/cyan] {contract_address}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")

    # --- Step 1: Add slasher ---

    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"

    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    

    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, contract_address)

    if task_coordinator_flag:
        console.print("[cyan]Confirming DIN Task Coordinator as slasher...[/cyan]")
        nonce = w3.eth.get_transaction_count(account.address)
        add_slasher_tx = deployed_DINTaskCoordinatorContract.functions.setDINTaskCoordinatorAsSlasher().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 200_000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
        })
        signed = account.sign_transaction(add_slasher_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Confirming DIN Task Coordinator as slasher tx:[/dim] {tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ DIN Task Coordinator confirmed as slasher![/green]")

    if task_auditor_flag:
        console.print("[cyan]Confirming DIN Task Auditor as slasher...[/cyan]")
        nonce = w3.eth.get_transaction_count(account.address)
        add_slasher_tx = deployed_DINTaskCoordinatorContract.functions.setDINTaskAuditorAsSlasher().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 200_000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
        })
        signed = account.sign_transaction(add_slasher_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Confirming DIN Task Auditor as slasher tx:[/dim] {tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ DIN Task Auditor confirmed as slasher![/green]")

    return

@model_app.command()
def create_genesis(
    network: str = typer.Option(None, "--network", help="Network to use"),
):

    effective_network = resolve_network(network)
    model_hash = getGenesisModelIpfs()
    console.print(f"[bold green]Genesis model created successfully![/bold green]")
    console.print(f"[cyan]Model hash:[/cyan] {model_hash}")

    # set in .env
    set_key(".env", "GENESIS_MODEL_IPFS_HASH", model_hash)
    
    return

@model_app.command()
def submit_genesis(
    network: str = typer.Option(None, "--network", help="Network to use"),
    ipfs_hash: str = typer.Option(None, "--ipfs-hash", help="IPFS hash of the model"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    score: int = typer.Option(None, "--score", help="Score of the model"),
):

    effective_network = resolve_network(network)

    w3 = get_w3(effective_network)
    
    account = load_account()
    
    if not ipfs_hash:
        ipfs_hash = get_key(".env", "GENESIS_MODEL_IPFS_HASH")
    
    if not task_coordinator_address:
        task_coordinator_address = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    console.print(f"[bold green]Submitting genesis model to DIN Task Coordinator![/bold green]")
    console.print(f"[cyan]IPFS hash:[/cyan] {ipfs_hash}")
    console.print(f"[cyan]Task coordinator address:[/cyan] {task_coordinator_address}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    # --- Step 1: Submit genesis model ---
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"

    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator_address)
    
    setGenesisModelIpfsHash_tx = deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(ipfs_hash).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 200_000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })

    signed = account.sign_transaction(setGenesisModelIpfsHash_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Submitting genesis model tx:[/dim] {tx_hash.hex()}")
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Genesis model submitted![/green]")
    
    
    set_key(".env", "IS_GenesisModelCreated", "True")
    set_key(".env", "GenesisModelIpfsHash", ipfs_hash)

    if score:
        accuracy = score
    else:
        accuracy = getscoreforGM(0, ipfs_hash)
        
    console.print("Genesis model accuracy:", accuracy)
    nonce = w3.eth.get_transaction_count(account.address)
        
    tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
        
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Submitting genesis model tier 2 score tx:[/dim] {tx_hash.hex()}")
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Genesis model tier 2 score set![/green]")

@gi_app.command(help="Start a global iteration")
def start(
    gi: Optional[int] = typer.Option(None, "--gi", help="Global iteration (optional)"),
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    

    if not task_coordinator_address:
        task_coordinator_address = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"

    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator_address)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    
    if gi:
        if gi!=curr_GI+1:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    console.print(f"[bold green]Starting global iteration {curr_GI+1}! on TaskCoordinator {task_coordinator_address}[/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")



    
    if curr_GI == 0:
        gmcid = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
    else:
        batch_id, _, _, gmcid = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI,0).call()
    
    accuracy = getscoreforGM(curr_GI, gmcid)
    console.print("Current GI:", curr_GI, "\nGM Accuracy:", accuracy)


    tx = deployed_DINTaskCoordinatorContract.functions.startGI(curr_GI+1, int(accuracy-5)).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
    })

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    unset_key(".env", "ClientModelsCreatedF")
    
    console.print(f"[dim]Global iteration started tx:[/dim] {tx_hash.hex()}")
    console.print("passScore for GI ", curr_GI+1, " is ", int(accuracy))
    console.print("[green]✓ Global iteration started![/green]")
    
    
@reg_app.command()  
def aggregators_open(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Opening aggregators registration for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.startDINvalidatorRegistration(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Aggregators registration opening failed")
        raise typer.Exit(1)
    console.print(f"[dim]Aggregators opened registration tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Aggregators registration opened![/green]")        

reg_app.command()
def aggregators_close(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Closing aggregators registration for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.closeDINvalidatorRegistration(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Aggregators registration closing failed")
        raise typer.Exit(1)
    console.print(f"[dim]Aggregators closed registration tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Aggregators registration closed![/green]")
    
@reg_app.command()
def aggregators_close(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):      
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Closing aggregators registration for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.closeDINvalidatorRegistration(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Aggregators registration closing failed")
        raise typer.Exit(1)
    console.print(f"[dim]Aggregators closed registration tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Aggregators registration closed![/green]")
    
@reg_app.command()
def auditors_open(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):      
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Opening auditors registration for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.startDINauditorRegistration(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Auditors registration opening failed")
        raise typer.Exit(1)
    console.print(f"[dim]Auditors opened registration tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Auditors registration opened![/green]")

@gi_app.command(help="Show registered auditors")
def show_registered_auditors(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--task-coordinator", help="DINTaskCoordinator contract address"),
    task_auditor: str = typer.Option(None, "--task-auditor", help="DINTaskAuditor contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):    
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)

    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GIstate < GIstatestrToIndex("DINauditorRegistrationStarted"):
        console.print("[red]Error:[/red] No auditors registered yet as DINauditorRegistrationStarted has not been reached")
        raise typer.Exit(1)

    
    console.print(f"[bold green]Showing registered auditors for global iteration {curr_GI} on TaskCoordinator {task_coordinator} and TaskAuditor {task_auditor}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")


    
    registered_auditors = deployed_DINTaskAuditorContract.functions.getDINtaskAuditors(curr_GI).call()
    console.print(str(len(registered_auditors)) + " Registered Auditors:", registered_auditors)    
    console.print("[green]✓ Registered auditors shown![/green]")


@gi_app.command(help="Show registered aggregators")
def show_registered_aggregators(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if curr_GIstate < GIstatestrToIndex("DINvalidatorRegistrationStarted"):
        console.print("[red]Error:[/red] No aggregators registered yet as DINvalidatorRegistrationStarted has not been reached")
        raise typer.Exit(1)

    console.print(f"[bold green]Showing registered aggregators for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    registered_aggregators = deployed_DINTaskCoordinatorContract.functions.getDINtaskValidators(curr_GI).call()
    console.print(str(len(registered_aggregators)) + " Registered Aggregators:", registered_aggregators)    
    console.print("[green]✓ Registered aggregators shown![/green]")


@gi_app.command()
def show_state(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    curr_GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    console.print(f"[bold green]Showing global iteration state for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    console.print(f"[cyan]Global iteration numerical state:[/cyan] {curr_GIstate}")
    console.print(f"[cyan]Global iteration state:[/cyan] {GIstateToStr(curr_GIstate)}")
    console.print("[green]✓ Global iteration state shown![/green]")

@reg_app.command()
def auditors_close(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Closing auditors registration for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.closeDINauditorRegistration(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Auditors registration closing failed")
        raise typer.Exit(1)
    console.print(f"[dim]Auditors closed registration tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Auditors registration closed![/green]")

@lms_app.command()    
def open(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Opening local model submissions for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.startLMsubmissions(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Local model submissions opening failed")
        raise typer.Exit(1)
    console.print(f"[dim]Local model submissions opened tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Local model submissions opened![/green]")

@lms_app.command()
def show_models(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--task-coordinator", help="Task coordinator address"),
    task_auditor: str = typer.Option(None, "--task-auditor", help="Task auditor address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration to use"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)
    
    console.print(f"[bold green]Showing local model submissions for global iteration {curr_GI} on TaskCoordinator {task_coordinator} and TaskAuditor {task_auditor}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")

    client_model_ipfs_hashes = []
    ClientAddresses = []

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if GIstate >= GIstatestrToIndex("LMSstarted"):
        lm_submissions = deployed_DINTaskAuditorContract.functions.getClientModels(curr_GI).call()
        if len(lm_submissions) == 0:
            console.print("[red]Error:[/red] No local model submissions found")
            raise typer.Exit(1)
        else:
            console.print(f"[green]✓ {len(lm_submissions)} Local model submissions found![/green]")
        for i in range(len(lm_submissions)):

            client_model_ipfs_hash = lm_submissions[i][1]
            ClientAddresses.append(lm_submissions[i][0])
            client_model_ipfs_hashes.append(client_model_ipfs_hash)
            console.print(f"[green]✓ Client {ClientAddresses[i]} submitted model {client_model_ipfs_hash}![/green]")

        console.print(f"[bold green]✓ Local model submissions shown![/bold green]")
        

@lms_app.command()    
def close(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GI < 1 or GIstate != GIstatestrToIndex("LMSstarted"):
        console.print("[red]Error:[/red] Can not close LM submissions at this time")
        raise typer.Exit(1)

    
    console.print(f"[bold green]Closing local model submissions for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.closeLMsubmissions(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Local model submissions closing failed")
        raise typer.Exit(1)
    console.print(f"[dim]Local model submissions closed tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Local model submissions closed![/green]")
      
@auditor_batches_app.command()
def create(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GI < 1 or GIstate != GIstatestrToIndex("LMSclosed"):
        console.print("[red]Error:[/red] Can not create auditor batches at this time")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Creating auditor batches for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")
    
    tx = deployed_DINTaskCoordinatorContract.functions.createAuditorsBatches(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
    
    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print("[red]Error:[/red] Auditor batches creation failed")
        raise typer.Exit(1)
    console.print(f"[dim]Auditor batches created tx:[/dim] {tx_hash.hex()}")
    console.print("[green]✓ Auditor batches created![/green]")

@auditor_batches_app.command()
def show(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="DINTaskAuditor contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    console.print(f"[bold green]Showing auditor batches for global iteration {gi} on TaskCoordinator {task_coordinator}![/bold green]")

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GI < 1 or GIstate < GIstatestrToIndex("AuditorsBatchesCreated"):
        console.print("[red]Error:[/red] Can not show auditor batches at this time as GIstate is ",GIstateToStr(GIstate))
        raise typer.Exit(1)

    console.print(f"[bold green]Showing auditor batches for global iteration {gi} on TaskCoordinator {task_coordinator}![/bold green]")
    console.print(f"[cyan]Network:[/cyan] {effective_network}")
    console.print(f"[cyan]From account:[/cyan] {account.address}")

    audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()

    console.print(f"[bold green]Auditor batches count:[/bold green] {audtor_batch_count}")

    raw_audit_batches = []
    processed_audit_batches = []
    
    for i in range(audtor_batch_count):
        raw_audit_batches.append(deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, i).call())

    for batch in raw_audit_batches:
        batch_id, auditors, model_indexes, test_cid = batch
        processed_audit_batches.append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid or "None"})

    

    # After building `processed_audit_batches`:
    if not processed_audit_batches:
        console.print("[yellow]No auditor batches found.[/yellow]")
    else:
        table = Table(title=f"Auditor Batches for GI {curr_GI}", show_header=True, header_style="bold magenta")
        table.add_column("Batch ID", style="dim")
        table.add_column("Auditors", overflow="fold")
        table.add_column("Model Indexes", overflow="fold")
        table.add_column("Test CID")

    for batch in processed_audit_batches:
        table.add_row(
            str(batch["batch_id"]),
            ", ".join(batch["auditors"]) if batch["auditors"] else "—",
            ", ".join(map(str, batch["model_indexes"])) if batch["model_indexes"] else "—",
            batch["test_cid"] if batch["test_cid"] != "None" else "—"
        )
    
    console.print(table)

    console.print("[green]✓ Auditor batches shown![/green]")

@auditor_batches_app.command()
def create_testdataset(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="DINTaskAuditor contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit test dataset to TaskCoordinator"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GI < 1 or GIstate != GIstatestrToIndex("AuditorsBatchesCreated"):
        console.print("[red]Error:[/red] Can not create test dataset at this time as GIstate is ",GIstateToStr(GIstate))
        raise typer.Exit(1)

    console.print(f"[bold green]Creating test dataset for global iteration {curr_GI} on TaskCoordinator {task_coordinator}![/bold green]")

    audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()

    audit_testDataCIDs = create_audit_testDataCIDs(audtor_batch_count, curr_GI)
    
    #audit_testDataCIDs = ['QmYHc4Y6pmMKFohYDJXkFCCrLAQBUhwGuD6ebGZUxi34ea', 'QmSvTuP4XmcNnaYAqYkv6ewUKU7v2PCAnnLB9DqE7MTrAg', 'QmSdiTciKYBTxHKntjY3Pko8szD5D1nXVLU2mVWrsZhWdE', 'QmcLCGEz9FDHti6c2PPUqAh8rzGpQSwFAZi4QifcYkQB49', 'QmRZydYdpcHTpSSNy7MsX2K29KuUwEsoRxDkT9NEHqu6CQ', 'QmfBeoeqxb3SecGj4qUWcYYZ5AtCsUPyBn8deUj4RQofxw']

    console.print("audit_testDataCIDs", audit_testDataCIDs)
    
    console.print(f"[bold green] ✓ Created test subdatasets for global iteration {curr_GI}![/bold green]")

    if submit:

        console.print(f"[bold green]Assigning test dataset for global iteration {curr_GI} on TaskAuditor {task_auditor}![/bold green]")

        for batch_id in range(audtor_batch_count):
            tx = deployed_DINTaskAuditorContract.functions.assignAuditTestDataset(curr_GI, batch_id, audit_testDataCIDs[batch_id]).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
                "chainId": w3.eth.chain_id
            })

            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status == 0:
                console.print("[red]Error:[/red] Failed to assign test dataset for auditor batch :", batch_id)
            else:
                console.print("[green]✓ Test dataset assigned for auditor batch :", batch_id)

        tx = deployed_DINTaskCoordinatorContract.functions.setTestDataAssignedFlag(curr_GI, True).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
                "chainId": w3.eth.chain_id
            })
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 0:
            console.print("[red]Error:[/red] Failed to set test dataset assigned flag for global iteration", curr_GI)
            raise typer.Exit(1)
            
        console.print(f"[green]✓ Test dataset assigned for auditor batches for global iteration {curr_GI}![/green]")


@lms_evaluation_app.command()
def start(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)

    if curr_GI < 1 or GIstate != GIstatestrToIndex("AuditorsBatchesCreated"):
        console.print("[red]Error:[/red] Can not start LMS evaluation at this time as GIstate is ",GIstateToStr(GIstate))
        raise typer.Exit(1)
    
    console.print(f"[bold green]Starting LMS evaluation for global iteration {curr_GI}![/bold green]")

    tx = deployed_DINTaskCoordinatorContract.functions.startLMsubmissionsEvaluation(curr_GI).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id
    })

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 0:
        console.print("[red]Error:[/red] Failed to start LMS evaluation for global iteration", curr_GI)
        raise typer.Exit(1)
    console.print(f"[green]✓ LMS evaluation started for global iteration {curr_GI}![/green]")
    

@lms_evaluation_app.command()
def close(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    
    # if artifact_path does not exist, raise error
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
    
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    
    if gi:
        if gi!=curr_GI:
            console.print("[red]Error:[/red] Invalid global iteration")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Closing LMS evaluation for global iteration {curr_GI}![/bold green]")

    if GIstate != GIstatestrToIndex("LMSevaluationStarted"):
        console.print("[red]Error:[/red] Can not close LMS evaluation at this time as GIstate is ",GIstateToStr(GIstate))
        raise typer.Exit(1)

    tx = deployed_DINTaskCoordinatorContract.functions.closeLMsubmissionsEvaluation(curr_GI).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id
    })

    signed_tx = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 0:
        console.print("[red]Error:[/red] Failed to close LMS evaluation for global iteration", curr_GI)
        raise typer.Exit(1)
    console.print(f"[green]✓ LMS evaluation closed for global iteration {curr_GI}![/green]")

@aggregation_app.command("create-t1nt2-batches")
def create_tier1_tier2_batches(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    if not artifact_path.exists():
        console.print("[red]Error:[/red] ABI file not found")
        raise typer.Exit(1)
        
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)
    
    if GIstate != GIstatestrToIndex("LMSevaluationClosed"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)} ({GIstate}), expected LMSevaluationClosed {GIstatestrToIndex("LMSevaluationClosed")}")
        raise typer.Exit(1)

    
    console.print(f"[bold green]Creating Tier 1 & Tier 2 batches for GI {curr_GI}...[/bold green]")
    
    tx = deployed_DINTaskCoordinatorContract.functions.autoCreateTier1AndTier2(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status == 1:
        console.print("[green]✓ Tier 1 & Tier 2 batches created successfully[/green]")
    else:
        console.print("[red]Error: Transaction failed[/red]")
        raise typer.Exit(1)


@aggregation_app.command("show-t1-batches")
def show_t1_batches(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account() 

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    
    # Check if batches can exist
    # GIstate must be >= T1nT2Bcreated (7)
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()


    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1nT2Bcreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. Batches do not exist yet.")
        raise typer.Exit(1)

    t1_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()
    if not detailed:
        table = Table(title=f"Tier 1 Batches (GI: {curr_GI})")
        table.add_column("Batch ID", justify="right", style="cyan")
        table.add_column("Aggregators", style="magenta")
        table.add_column("Model Indexes", style="green")
        table.add_column("Finalized", style="yellow")
        table.add_column("Final CID", style="white")

        for i in range(t1_count):
            bid, validators, model_idxs, finalized, cid = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            
            val_display = "\n".join([f"{v[:6]}...{v[-4:]}" for v in validators])
            idxs_display = ", ".join(map(str, model_idxs))
            
            table.add_row(str(bid), val_display, idxs_display, str(finalized), cid or "")
            
        console.print(table)


    if detailed:

        detailed_table = Table(title=f"Detailed Tier 1 Batches (GI: {curr_GI})")
        detailed_table.add_column("Batch ID", justify="right", style="cyan")
        detailed_table.add_column("Aggregator Address", style="magenta")
        detailed_table.add_column("Submitted CID", style="green")
        detailed_table.add_column("Model Indexes", style="green")
        detailed_table.add_column("Finalized CID", style="white")
        for i in range(t1_count):
            bid, validators, model_idxs, finalized, final_cid = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
            
            for validator in validators:
                submitted_cid = deployed_DINTaskCoordinatorContract.functions.t1SubmissionCID(curr_GI, bid, validator).call()
                idxs_display = ", ".join(map(str, model_idxs))
                detailed_table.add_row(str(bid), validator, submitted_cid or "None", idxs_display, final_cid or "Pending")
        
        console.print(detailed_table)
        


@aggregation_app.command("show-t2-batches")
def show_t2_batches(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account() 

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)
    
    if GIstate < GIstatestrToIndex("T1nT2Bcreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. Batches do not exist yet.")
        raise typer.Exit(1)

    # Assuming 1 T2 batch for now as per reference code
    t2_count = 1 
    
    table = Table(title=f"Tier 2 Batches (GI: {curr_GI})")
    table.add_column("Batch ID", justify="right", style="cyan")
    table.add_column("Validators", style="magenta")
    if detailed:
        table.add_column("Submitted CID", style="green")
    table.add_column("Finalized", style="yellow")
    table.add_column("Final CID", style="white")
    
    for i in range(t2_count):
        try:
            bid, validators, finalized, cid = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
            val_display = "\n".join([f"{v[:6]}...{v[-4:]}" for v in validators])
            if not detailed:
                table.add_row(str(bid), val_display, str(finalized), cid or "")
            else:
                submitted_cid_display = "\n".join(deployed_DINTaskCoordinatorContract.functions.t2SubmissionCID(curr_GI, bid, v).call() for v in validators)
                table.add_row(str(bid), val_display, submitted_cid_display, str(finalized), cid or "")
        except Exception:
            # Maybe batch doesn't exist if count assumption is wrong or not created
            pass

    console.print(table)


@t1_app.command("start")
def start_t1_aggregation(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)
    
    if GIstate < GIstatestrToIndex("T1nT2Bcreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state T1nT2Bcreated not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Starting Tier 1 Aggregation for GI {curr_GI}...[/bold green]")
    
    tx = deployed_DINTaskCoordinatorContract.functions.startT1Aggregation(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Tier 1 Aggregation started[/green]")


@t1_app.command("close")
def close_t1_aggregation(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    
    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1AggregationStarted"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state T1AggregationStarted not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Finalizing Tier 1 Aggregation for GI {curr_GI}...[/bold green]")
    
    tx = deployed_DINTaskCoordinatorContract.functions.finalizeT1Aggregation(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Tier 1 Aggregation finalized[/green]")


@t2_app.command("start")
def start_t2_aggregation(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1AggregationDone"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state T1AggregationDone not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Starting Tier 2 Aggregation for GI {curr_GI}...[/bold green]")
    
    tx = deployed_DINTaskCoordinatorContract.functions.startT2Aggregation(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Tier 2 Aggregation started[/green]")


@t2_app.command("close")
def close_t2_aggregation(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if GIstate < GIstatestrToIndex("T2AggregationStarted"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state T2AggregationStarted not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Finalizing Tier 2 Aggregation for GI {curr_GI}...[/bold green]")
    
    # 1. Finalize T2 Aggregation
    console.print("[cyan]Calling finalizeT2Aggregation...[/cyan]")
    tx = deployed_DINTaskCoordinatorContract.functions.finalizeT2Aggregation(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    w3.eth.wait_for_transaction_receipt(tx_hash)
    
    # 2. Get Tier 2 batch to find final CID
    tier2_batch = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, 0).call()
    # (bid, validators, finalized, cid)
    finalCID = tier2_batch[3]
    
    console.print(f"[cyan]Final CID:[/cyan] {finalCID}")
    
    # 3. Calculate score
    console.print("[cyan]Calculating score for final model...[/cyan]")
    accuracy = getscoreforGM(curr_GI, finalCID)
    console.print(f"[green]Accuracy:[/green] {accuracy}")
    
    # 4. Set Tier 2 score
    console.print("[cyan]Setting Tier 2 score...[/cyan]")
    nonce = w3.eth.get_transaction_count(account.address)
    tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(curr_GI, int(accuracy)).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": nonce,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Score Tx hash: {tx_hash.hex()}[/dim]")
    
    w3.eth.wait_for_transaction_receipt(tx_hash)
    
    console.print("[green]✓ Tier 2 Aggregation finalized and score set[/green]")

@slash_app.command("auditors")
def slash_auditors(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if GIstate < GIstatestrToIndex("T2AggregationDone"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state T2AggregationDone not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Slashing for GI {curr_GI}...[/bold green]")
    
    # 1. Slash
    console.print(f"[cyan]Calling slashAuditors... for GI {curr_GI} with account {account.address} on task coordinator {task_coordinator}[/cyan]")
    tx = deployed_DINTaskCoordinatorContract.functions.slashAuditors(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print(f"[red]Error:[/red] Slash Auditors Transaction failed with status {receipt.status}")
        raise typer.Exit(1)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
   
    
    console.print("[green]✓ Auditors slashed[/green]")

@slash_app.command("aggregators")
def slash_aggregators(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid GI, current GI is {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("AuditorsSlashed"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state AuditorsSlashed not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Slashing Aggregators for GI {curr_GI}...[/bold green]")

    # 1. Slash
    console.print(f"[cyan]Calling slash Aggregators... for GI {curr_GI} with account {account.address} on task coordinator {task_coordinator}[/cyan]")
    tx = deployed_DINTaskCoordinatorContract.functions.slashValidators(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print(f"[red]Error:[/red] Slash Aggregators Transaction failed with status {receipt.status}")
        raise typer.Exit(1)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
   
    
    console.print("[green]✓ Aggregators slashed[/green]")

@gi_app.command()
def end(
    network: str = typer.Option(None, "--network", help="Network to use"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid GI, current GI is {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("ValidatorSlashed"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state ValidatorSlashed not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Ending GI {curr_GI}...[/bold green]")   
    
    # 1. End
    console.print(f"[cyan]Calling end GI... for GI {curr_GI} with account {account.address} on task coordinator {task_coordinator}[/cyan]")
    tx = deployed_DINTaskCoordinatorContract.functions.endGI(curr_GI).build_transaction({
        "from": account.address,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "nonce": w3.eth.get_transaction_count(account.address),
        "chainId": w3.eth.chain_id,
    })
    
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if receipt.status == 0:
        console.print(f"[red]Error:[/red] End Transaction failed with status {receipt.status}")
        raise typer.Exit(1)
    console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
    
    console.print("[green]✓ GI ended[/green]")



@lms_evaluation_app.command("show")
def show(
    network: str = typer.Option(None, "--network", help="Network to use"),
    auditor: bool = typer.Option(False, "--auditor", help="Show auditor evaluations"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="DINTaskAuditor contract address"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()

    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")

    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid GI, current GI is {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("AuditorsBatchesCreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. GI state AuditorsBatchesCreated not passed yet.")
        raise typer.Exit(1)
    
    console.print(f"[bold green]Showing LMS Evaluation for GI {curr_GI}...[/bold green]")   
    console.print("DIN task Auditor address: ", task_auditor)
    console.print("DIN task Coordinator address: ", task_coordinator)

    audtor_batch_count = deployed_DINTaskAuditorContract.functions.AuditorsBatchCount(curr_GI).call()

    model_idx_to_batch_id = {}
    model_idx_to_test_cid = {}
    raw_audit_batches = []
    auditor_batch = {}

    raw_lm_submissions = deployed_DINTaskAuditorContract.functions.getClientModels(curr_GI).call()

    lm_submissions = {}
    relevant_lm_submissions = {}

    assigned_lm_submissions = {}

    if auditor:
        all_auditors = set()

    for i in range(audtor_batch_count):
        raw_audit_batches.append(deployed_DINTaskAuditorContract.functions.getAuditorsBatch(curr_GI, i).call())
    
    for batch_data in raw_audit_batches:
        batch_id, auditors, model_indexes, test_cid = batch_data

        for a in auditors:
            auditor_batch[a]=auditor_batch.get(a, {"raw_batches": []})
            auditor_batch[a]["raw_batches"].append({"batch_id": batch_id, "model_indexes": model_indexes, "test_cid": test_cid})

        all_auditors.update(auditors)

    if auditor:
        for a in all_auditors:
            auditor_batch[a]["batch_count"] = len(auditor_batch[a]["raw_batches"])

            relevant_lm_submissions[a] = set()

            for batch in auditor_batch[a]["raw_batches"]:
                relevant_lm_submissions[a].update(batch["model_indexes"])

                for model_idx in batch["model_indexes"]:
                    model_idx_to_batch_id[model_idx] = batch["batch_id"]
                    model_idx_to_test_cid[model_idx] = batch["test_cid"]

    for idx, sub in enumerate(raw_lm_submissions):
        client, model_cid, submitted_at, eligible, evaluated, approved, final_avg = sub

        lm_submissions[idx] = {"model_index": idx, "client": client, "model_cid": model_cid, "submitted_at": submitted_at, "eligible": eligible, "evaluated": evaluated, "approved": approved, "final_avg": final_avg}

        if auditor:

            for auditor in all_auditors:
                assigned_lm_submissions[auditor] = assigned_lm_submissions.get(auditor, [])

                if idx not in relevant_lm_submissions[auditor]:
                    continue
                else:
                    batch_id = model_idx_to_batch_id[idx]

                    try:
                        has_voted = deployed_DINTaskAuditorContract.functions.hasAuditedLM(curr_GI, batch_id, auditor, idx).call()
                    except:
                        has_voted = False
                    
                    try:
                        is_eligible = deployed_DINTaskAuditorContract.functions.LMeligibleVote(curr_GI, batch_id, auditor, idx).call()
                    except:
                        is_eligible = False
                    
                    try:
                        has_auditScores = deployed_DINTaskAuditorContract.functions.auditScores(curr_GI, batch_id, auditor, idx).call()
                    except:
                        has_auditScores = False

                    assigned_lm_submissions[auditor].append({
                        "model_index": idx,
                        "client": client,
                        "model_cid": model_cid,
                        "submitted_at": submitted_at,
                        "batch_id": batch_id,
                        "has_voted": has_voted,
                        "is_eligible": is_eligible,
                        "has_auditScores": has_auditScores,
                        "test_cid": model_idx_to_test_cid[idx]
                    })
                    

    lm_submissions_table = Table(title=f"LM Submissions for GI {curr_GI}", show_header=True, header_style="bold magenta")

    lm_submissions_table.add_column("Model Index", style="dim")
    lm_submissions_table.add_column("Client", overflow="fold")
    lm_submissions_table.add_column("Model CID", overflow="fold")
    lm_submissions_table.add_column("Submitted At", overflow="fold")
    lm_submissions_table.add_column("Eligible", overflow="fold")
    lm_submissions_table.add_column("Evaluated", overflow="fold")
    lm_submissions_table.add_column("Approved", overflow="fold")
    lm_submissions_table.add_column("Final Avg", overflow="fold")

    for sub in lm_submissions.values():
        lm_submissions_table.add_row(
            str(sub["model_index"]),
            str(sub["client"]),
            str(sub["model_cid"]),
            str(sub["submitted_at"]),
            str(sub["eligible"]),
            str(sub["evaluated"]),
            str(sub["approved"]),
            str(sub["final_avg"]) if sub["final_avg"] != "None" else "—"
        )
    console.print(lm_submissions_table)

    if auditor:

        for auditor in all_auditors:
            
            assigned_lm_submissions_table = Table(title=f"Assigned LM Submissions for GI {curr_GI} for auditor {auditor}", show_header=True, header_style="bold magenta")

            assigned_lm_submissions_table.add_column("Model Index", style="dim")
            assigned_lm_submissions_table.add_column("Client", overflow="fold")
            assigned_lm_submissions_table.add_column("Model CID", overflow="fold")
            assigned_lm_submissions_table.add_column("Submitted At", overflow="fold")
            assigned_lm_submissions_table.add_column("Batch ID", overflow="fold")
            assigned_lm_submissions_table.add_column("Has Voted", overflow="fold")
            assigned_lm_submissions_table.add_column("Is Eligible", overflow="fold")
            assigned_lm_submissions_table.add_column("Has AuditScores", overflow="fold")
            assigned_lm_submissions_table.add_column("Test CID", overflow="fold")

            for idx, sub in enumerate(assigned_lm_submissions[auditor]):
                assigned_lm_submissions_table.add_row(
                    str(sub["model_index"]),
                    str(sub["client"]),
                    str(sub["model_cid"]),
                    str(sub["submitted_at"]),
                    str(sub["batch_id"]),
                    str(sub["has_voted"]),
                    str(sub["is_eligible"]),
                    str(sub["has_auditScores"]),
                    str(sub["test_cid"]) if sub["test_cid"] != "None" else "—"
                )
            console.print(assigned_lm_submissions_table)
    
            


        






    












    





        


    
    
    
