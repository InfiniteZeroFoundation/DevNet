import typer
from web3 import Web3

from dincli.cli.utils import build_and_send_tx

app = typer.Typer(help="Claim GI rewards (any role: clients, auditors, aggregators).")


@app.command(help="Credit your reward share for a settled GI (DINTaskAuditor.claimReward)")
def claim(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI to claim for (must have ended)"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    # giRewardSnapshot getter: (clientPool, auditorPool, aggregatorPool,
    # aggregatorTotalWeight, settled). settleRewards runs in endGI.
    settled = task_auditor.functions.giRewardSnapshot(gi).call()[4]
    if not settled:
        console.print(f"[bold red]✗ GI {gi} rewards are not settled yet. They settle when the model owner ends the GI.[/bold red]")
        raise typer.Exit(1)

    if task_auditor.functions.rewardClaimed(gi, account.address).call():
        console.print(f"[yellow]Reward for GI {gi} already claimed. Run `dincli rewards withdraw {model_id}` to transfer it.[/yellow]")
        return

    build_and_send_tx(
        ctx,
        task_auditor.functions.claimReward(gi),
        f"Claiming reward for GI {gi}",
        f"Reward for GI {gi} credited.",
        f"Could not claim reward for GI {gi} (TA_NoRewardEarned if you earned nothing in this GI)",
    )

    claimable = task_auditor.functions.claimable(account.address).call()
    console.print(f"[bold green]Claimable balance:[/bold green] {Web3.from_wei(claimable, 'ether')} DIN")
    console.print(f"[dim]Transfer it with: dincli rewards withdraw {model_id}[/dim]")


@app.command(help="Transfer your whole claimable reward balance to your wallet (DINTaskAuditor.claimRewards)")
def withdraw(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    claimable = task_auditor.functions.claimable(account.address).call()
    if claimable == 0:
        console.print(f"[bold red]✗ Nothing to withdraw. Credit a GI first with: dincli rewards claim {model_id} --gi N[/bold red]")
        raise typer.Exit(1)

    build_and_send_tx(
        ctx,
        task_auditor.functions.claimRewards(),
        f"Withdrawing {Web3.from_wei(claimable, 'ether')} DIN",
        "Rewards withdrawn.",
        "Could not withdraw rewards",
    )
