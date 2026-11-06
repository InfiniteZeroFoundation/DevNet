from decimal import Decimal
from typing import Optional

import typer
from web3 import Web3

from dincli.cli.dintoken import approve_din
from dincli.cli.utils import build_and_send_tx

rewards_app = typer.Typer(help="Fund GI reward pools")

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _resolve_funding_gi(console, task_coordinator, gi: Optional[int]) -> int:
    """depositRewards accepts the current GI or a later one (TA_InvalidRewardGI
    otherwise). Defaults to the next GI, the one `gi start` needs funded."""
    curr_gi = task_coordinator.functions.GI().call()
    target_gi = gi if gi is not None else curr_gi + 1
    if target_gi == 0 or target_gi < curr_gi:
        console.print(f"[bold red]✗ GI {target_gi} can't be funded: the current GI is {curr_gi}, and only it or a later GI can be.[/bold red]")
        raise typer.Exit(1)
    return target_gi


@rewards_app.command(help="Deposit DIN into a GI's reward pool (approve + DINTaskAuditor.depositRewards). Anyone can fund.")
def deposit(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    amount: float = typer.Option(..., "--amount", help="DIN to deposit"),
    gi: Optional[int] = typer.Option(None, "--gi", help="GI to fund (default: the next GI)"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    din_token = ctx.obj.get_deployed_din_token_contract(verbose=False)

    target_gi = _resolve_funding_gi(console, task_coordinator, gi)
    amount_wei = Web3.to_wei(Decimal(str(amount)), "ether")
    if amount_wei <= 0:
        console.print("[bold red]✗ --amount must be positive.[/bold red]")
        raise typer.Exit(1)

    if task_auditor.functions.dinToken().call() == ZERO_ADDRESS:
        console.print("[bold red]✗ DINTaskAuditor has no DIN token set. The model owner must call setDinToken on it first.[/bold red]")
        raise typer.Exit(1)

    balance = din_token.functions.balanceOf(account.address).call()
    if balance < amount_wei:
        console.print(f"[bold red]✗ Not enough DIN: balance {Web3.from_wei(balance, 'ether')}, deposit {amount}.[/bold red]")
        raise typer.Exit(1)

    approve_din(ctx, task_auditor.address, amount_wei, purpose="the GI reward pool")

    build_and_send_tx(
        ctx,
        task_auditor.functions.depositRewards(target_gi, amount_wei),
        f"Depositing {amount} DIN into the GI {target_gi} reward pool",
        f"GI {target_gi} reward pool funded.",
        f"Could not deposit into the GI {target_gi} reward pool",
    )

    pool = task_auditor.functions.giRewardPool(target_gi).call()
    console.print(f"[bold green]GI {target_gi} reward pool:[/bold green] {Web3.from_wei(pool, 'ether')} DIN")


@rewards_app.command("fund-emission", help="Fund a GI's reward pool from the protocol emission schedule (DinEmission.fundGI)")
def fund_emission(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: Optional[int] = typer.Option(None, "--gi", help="GI to fund (default: the next GI)"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    emission = ctx.obj.get_deployed_din_emission_contract()

    target_gi = _resolve_funding_gi(console, task_coordinator, gi)

    # fundGI reverts for these; checking first names the cause.
    exists, registry_model_id = ctx.obj.get_deployed_din_registry_contract(verbose=False).functions.getModelIdByTaskAuditor(task_auditor.address).call()
    if not exists:
        console.print("[bold red]✗ This DINTaskAuditor isn't registered in DINModelRegistry, so DinEmission won't fund it (UnregisteredTaskAuditor).[/bold red]")
        raise typer.Exit(1)
    if emission.functions.giEmissionFunded(task_auditor.address, target_gi).call():
        console.print(f"[bold red]✗ GI {target_gi} was already funded from emission (GIAlreadyFunded).[/bold red]")
        raise typer.Exit(1)
    amount = emission.functions.emissionForCurrentEpoch(task_auditor.address).call()
    if amount == 0:
        console.print("[bold red]✗ This model's emission schedule is exhausted (EmissionExhausted). Use `rewards deposit` instead.[/bold red]")
        raise typer.Exit(1)

    build_and_send_tx(
        ctx,
        emission.functions.fundGI(target_gi, task_auditor.address),
        f"Funding GI {target_gi} with {Web3.from_wei(amount, 'ether')} DIN of emission",
        f"GI {target_gi} reward pool funded from emission.",
        f"Could not fund GI {target_gi} from emission (ModelDisabledForEmission if model {registry_model_id} is disabled)",
    )

    pool = task_auditor.functions.giRewardPool(target_gi).call()
    console.print(f"[bold green]GI {target_gi} reward pool:[/bold green] {Web3.from_wei(pool, 'ether')} DIN")
