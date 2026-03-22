
import typer

from dincli.cli.contract_utils import erc20_abi
from dincli.cli.utils import get_env_key, load_usdt_config

setup_app = typer.Typer(help="Setup commands")

@setup_app.command("deposit-reward-in-dintask-auditor")
def deposit_reward_in_dintask_auditor(
    ctx: typer.Context,
    amount: int = typer.Option(..., "--amount", help="Amount of rewards to deposit in USDT"),
):
    """
    Deposit rewards into the DINTaskAuditor contract.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    
    usdt_config = load_usdt_config()
    if effective_network in usdt_config and "usdt" in usdt_config[effective_network]:
        usdt_address = usdt_config[effective_network]["usdt"]
    
    if not usdt_address:
        console.print("[red]Error:[/red] USDT contract address not found.")
        raise typer.Exit(1)

    
    # Step 1: Get Task Coordinator address
    task_coordinator_key = f"{effective_network.upper()}_DINTaskCoordinator_Contract_Address"
    task_coordinator_address = get_env_key(task_coordinator_key)

    if not task_coordinator_address:
        raise typer.Exit(1)
    
    # Step 2: Use it to build the Auditor key
    auditor_key = f"{effective_network.upper()}_{task_coordinator_address}_DINTaskAuditor_Contract_Address"
    dintask_auditor_address = get_env_key(auditor_key)
    
    if not dintask_auditor_address:
        raise typer.Exit(1)

    console.print(f"[bold green]Depositing rewards on network:[/bold green] {effective_network}")
    console.print(f"[cyan]Using USDT address:[/cyan] {usdt_address}")
    console.print(f"[cyan]Using DINTaskAuditor address:[/cyan] {dintask_auditor_address}")
    console.print(f"[cyan]Amount:[/cyan] {amount}")
    
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

    DINTaskAuditor_contract = ctx.obj.get_deployed_din_task_auditor_contract(False, None, dintask_auditor_address)

    # --- Print summary ---
    console.print(f"[bold green]Depositing {amount} USDT[/bold green]")

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

    if current_allowance != amount_wei:
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
    console.print(f"[cyan]Owner of DINTaskAuditor:[/cyan] {owner}")
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

    return


@setup_app.command("add-slasher")
def add_slasher(
    ctx: typer.Context,
    task_coordinator_flag: bool = typer.Option(False, "--taskCoordinator", help="Add task coordinator as slasher"),
    task_auditor_flag: bool = typer.Option(False, "--taskAuditor", help="Add task auditor as slasher"),
    contract_address: str = typer.Option(None, "--contract", help="Contract address to use for DIN Task Coordinator"),
):


    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    if task_coordinator_flag and task_auditor_flag:
        console.print("[red]Error:[/red] Cannot add both task coordinator and task auditor as slashers simultaneously")
        raise typer.Exit(1)
    elif not task_coordinator_flag and not task_auditor_flag:
        console.print("[red]Error:[/red] You must specify either --taskCoordinator or --taskAuditor")
        raise typer.Exit(1)



    if not contract_address:
        
        contract_address = get_env_key(effective_network.upper() + "_DINTaskCoordinator_Contract_Address")

        if not contract_address:
            raise typer.Exit(1)


    # --- Print summary ---

    deployed_DINTaskCoordinatorContract = ctx.obj.get_deployed_din_task_coordinator_contract(True, None, contract_address)

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
