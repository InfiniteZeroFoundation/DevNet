
import typer
from dincli.cli.utils import build_and_send_tx, _confirm_or_exit

slash_app = typer.Typer(help="Slash commands")

@slash_app.command("auditors")
def slash_auditors(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(curr_GIstate, "T2AggregationDone","Can not slash auditors at this time.")

    # GIstate alone can't tell us whether `dincli model-owner aggregation t2 set-score` actually
    # ran: setTier2Score doesn't advance GIstate, so T2AggregationDone is
    # reached as soon as `t2 close` finishes, before scoring happens. Use the
    # recorded score itself as the signal, with a confirmation fallback since
    # a genuine score of 0 is indistinguishable from "never set".
    tier2_score = task_coordinator_Contract.functions.getTier2Score(ref_gi).call()
    if tier2_score == 0:
        _confirm_or_exit(
            f"Tier 2 score for GI {ref_gi} reads as 0, which usually means `dincli model-owner aggregation t2 set-score --gi {ref_gi}` hasn't been run yet. "
            "Slashing now will use this score. Are you sure you want to continue?",
            f"Run `aggregator t2 set-score --gi {ref_gi}` first.",
            console=console,
        )
    else:
        console.print(f"[cyan]Tier 2 score for GI {ref_gi}:[/cyan] {tier2_score}")

    console.print(f"[bold green]Slashing Auditors ...[/bold green]")
    try:
        tx_receipt = build_and_send_tx(
            ctx,
            task_coordinator_Contract.functions.slashAuditors(ref_gi),
            "Slashing Auditors",
            "Auditors slashed",
            "Slash Auditors Transaction failed",
            exit_on_failure=False
        )
        console.print(f"[dim]Tx hash: {tx_receipt.transactionHash.hex()}[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
    


@slash_app.command("aggregators")
def slash_aggregators(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(curr_GIstate, "AuditorsSlashed","Can not slash aggregators at this time.")
    
    console.print(f"[bold green]Slashing Aggregators ...[/bold green]")

    try:
        tx_receipt = build_and_send_tx(
            ctx,
            task_coordinator_Contract.functions.slashAggregators(ref_gi),
            "Slashing Aggregators",
            "Aggregators slashed",
            "Slash Aggregators Transaction failed",
            exit_on_failure=False
        )
        console.print(f"[dim]Tx hash: {tx_receipt.transactionHash.hex()}[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
