
import typer

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

    console.print(f"[bold green]Slashing Auditors ...[/bold green]")
    try:
        tx_params = ctx.obj.get_tx_params()
        tx_params["gas"] = int(w3.eth.estimate_gas(task_coordinator_Contract.functions.slashAuditors(ref_gi).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
        tx = task_coordinator_Contract.functions.slashAuditors(ref_gi).build_transaction(tx_params)
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
            console.print("[green]✓ Auditors slashed[/green]")
        else:
            console.print("[red]Error:[/red] Slash Auditors Transaction failed with status {receipt.status}")
            raise typer.Exit(1)
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
        tx_params = ctx.obj.get_tx_params()
        tx_params["gas"] = int(w3.eth.estimate_gas(task_coordinator_Contract.functions.slashAggregators(ref_gi).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
        tx = task_coordinator_Contract.functions.slashAggregators(ref_gi).build_transaction(tx_params)

        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
            console.print("[green]✓ Aggregators slashed[/green]")
        else:
            console.print(f"[red]Error:[/red] Slash Aggregators Transaction failed with status {receipt.status}")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
