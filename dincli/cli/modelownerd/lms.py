
import typer

lms_app = typer.Typer(help="Local Model Submission commands")

@lms_app.command()    
def open(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator)
    ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    
    console.print(f"[bold green]Opening local model submissions[/bold green]")

    try:
    
        tx = task_coordinator.functions.startLMsubmissions(curr_GI).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
        })
    
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            console.print("[green]✓ Local model submissions opened![/green]")
        else:
            console.print("[red]Error:[/red] Local model submissions opening failed")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Transaction failed:[/red] {str(e)}")
        raise typer.Exit(1)

@lms_app.command()
def show_models(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration to use"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)
    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    console.print(f"[bold green]Showing local model submissions for global iteration {ref_gi} [/bold green]")

    client_model_ipfs_hashes = []
    ClientAddresses = []

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, curr_GIstate, "LMSstarted", "Local model submissions not yet started")

    lm_submissions = taskAuditor_contract.functions.getClientModels(ref_gi).call()
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
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    console.print(f"[bold green]Closing local model submissions[/bold green]")

    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "LMSstarted", "Local model submissions not yet started")

    try:
        tx = taskCoordinator_contract.functions.closeLMsubmissions(ref_gi).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
        })
    
        signed_tx = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if receipt.status == 1:
            console.print(f"[dim]Local model submissions closed tx:[/dim] {tx_hash.hex()}")
            console.print("[green]✓ Local model submissions closed![/green]")
        else:
            console.print("[red]Error:[/red] Local model submissions closing failed")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Transaction failed:[/red] {str(e)}")
        raise typer.Exit(1)
