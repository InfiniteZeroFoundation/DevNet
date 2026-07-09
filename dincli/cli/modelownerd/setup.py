
import typer

from dincli.cli.contract_utils import erc20_abi
from dincli.cli.utils import build_and_send_tx, get_env_key, resolve_task_coordinator_address

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
        contract_address = resolve_task_coordinator_address(
            effective_network, None, console
        )


    # --- Print summary ---

    deployed_DINTaskCoordinatorContract = ctx.obj.get_deployed_din_task_coordinator_contract(True, None, contract_address)

    if task_coordinator_flag:
        build_and_send_tx(
            ctx,
            deployed_DINTaskCoordinatorContract.functions.setDINTaskCoordinatorAsSlasher(),
            "Confirming DIN Task Coordinator as slasher",
            "DIN Task Coordinator confirmed as slasher!",
            "Failed to confirm DIN Task Coordinator as slasher"
        )

    if task_auditor_flag:
        build_and_send_tx(
            ctx,
            deployed_DINTaskCoordinatorContract.functions.setDINTaskAuditorAsSlasher(),
            "Confirming DIN Task Auditor as slasher",
            "DIN Task Auditor confirmed as slasher!",
            "Failed to confirm DIN Task Auditor as slasher"
        )

    return
