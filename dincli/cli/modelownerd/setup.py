
import typer

from dincli.cli.contract_utils import erc20_abi
from dincli.cli.utils import get_env_key

setup_app = typer.Typer(help="Setup commands")

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

        tx_params = ctx.obj.get_tx_params()
        tx_params["gas"] = int(w3.eth.estimate_gas(deployed_DINTaskCoordinatorContract.functions.setDINTaskCoordinatorAsSlasher().build_transaction(tx_params)) * 1.1)  # Add 10% buffer

        add_slasher_tx = deployed_DINTaskCoordinatorContract.functions.setDINTaskCoordinatorAsSlasher().build_transaction(tx_params)
        signed = account.sign_transaction(add_slasher_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Confirming DIN Task Coordinator as slasher tx:[/dim] {tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ DIN Task Coordinator confirmed as slasher![/green]")

    if task_auditor_flag:
        console.print("[cyan]Confirming DIN Task Auditor as slasher...[/cyan]")
        tx_params = ctx.obj.get_tx_params()
        tx_params["gas"] = int(w3.eth.estimate_gas(deployed_DINTaskCoordinatorContract.functions.setDINTaskAuditorAsSlasher().build_transaction(tx_params)) * 1.1)  # Add 10% buffer
        add_slasher_tx = deployed_DINTaskCoordinatorContract.functions.setDINTaskAuditorAsSlasher().build_transaction(tx_params)
        signed = account.sign_transaction(add_slasher_tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Confirming DIN Task Auditor as slasher tx:[/dim] {tx_hash.hex()}")
        w3.eth.wait_for_transaction_receipt(tx_hash)
        console.print("[green]✓ DIN Task Auditor confirmed as slasher![/green]")

    return
