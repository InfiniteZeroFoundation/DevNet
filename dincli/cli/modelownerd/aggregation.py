from pathlib import Path

import typer
from rich.table import Table

from dincli.cli.utils import CACHE_DIR, get_manifest_key
from dincli.services.modelowner import getscoreforGM
from dincli.services.cid_utils import get_cid_from_bytes32

aggregation_app = typer.Typer(help="Aggregation commands")
t1_app = typer.Typer(help="Tier 1 commands")
t2_app = typer.Typer(help="Tier 2 commands")

aggregation_app.add_typer(t1_app, name="T1")
aggregation_app.add_typer(t2_app, name="T2")

@aggregation_app.command("create-t1nt2-batches")
def create_tier1_tier2_batches(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "LMSevaluationClosed","Can not create Tier 1 & Tier 2 batches at this time.")
    
    console.print(f"[bold green]Creating Tier 1 & Tier 2 batches[/bold green]")
    
    try:
        tx = task_coordinator_Contract.functions.autoCreateTier1AndTier2(ref_gi).build_transaction({
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
            console.print("[red]Error: Could not create Tier 1 & Tier 2 batches. Transaction failed[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: Could not create Tier 1 & Tier 2 batches. {str(e)}[/red]")
        raise typer.Exit(1)


@aggregation_app.command("show-t1-batches")
def show_t1_batches(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI,GIstate, "T1nT2Bcreated","Can not show Tier 1 batches at this time.")

    console.print(f"[green]✓ Showing Tier 1 batches[/green]")


    t1_count = task_coordinator_Contract.functions.tier1BatchCount(ref_gi).call()
    if not detailed:
        table = Table(title=f"Tier 1 Batches (GI: {ref_gi})")
        table.add_column("Batch ID", justify="right", style="cyan")
        table.add_column("Aggregators", style="magenta")
        table.add_column("Model Indexes", style="green")
        table.add_column("Finalized", style="yellow")
        table.add_column("Final CID", style="white")

        for i in range(t1_count):
            bid, validators, model_idxs, finalized, cid_raw = task_coordinator_Contract.functions.getTier1Batch(ref_gi, i).call()
            cid = get_cid_from_bytes32(cid_raw.hex()) if cid_raw and cid_raw != bytes(32) else ""
            val_display = "\n".join([f"{v[:6]}...{v[-4:]}" for v in validators])
            idxs_display = ", ".join(map(str, model_idxs))
            
            table.add_row(str(bid), val_display, idxs_display, str(finalized), cid)
            
        console.print(table)


    if detailed:

        detailed_table = Table(title=f"Detailed Tier 1 Batches (GI: {ref_gi})")
        detailed_table.add_column("Batch ID", justify="right", style="cyan")
        detailed_table.add_column("Aggregator Address", style="magenta")
        detailed_table.add_column("Submitted CID", style="green")
        detailed_table.add_column("Model Indexes", style="green")
        detailed_table.add_column("Finalized CID", style="white")
        for i in range(t1_count):
            bid, validators, model_idxs, finalized, final_cid_raw = task_coordinator_Contract.functions.getTier1Batch(ref_gi, i).call()
            final_cid = get_cid_from_bytes32(final_cid_raw.hex()) if final_cid_raw and final_cid_raw != bytes(32) else "Pending"
            
            for validator in validators:
                submitted_cid_raw = task_coordinator_Contract.functions.t1SubmissionCID(ref_gi, bid, validator).call()
                submitted_cid = get_cid_from_bytes32(submitted_cid_raw.hex()) if submitted_cid_raw and submitted_cid_raw != bytes(32) else "None"
                idxs_display = ", ".join(map(str, model_idxs))
                detailed_table.add_row(str(bid), validator, submitted_cid, idxs_display, final_cid)
        
        console.print(detailed_table)
        


@aggregation_app.command("show-t2-batches")
def show_t2_batches(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI,GIstate, "T1nT2Bcreated","Can not show Tier 2 batches at this time.")

    # Assuming 1 T2 batch for now as per reference code
    t2_count = 1 
    
    table = Table(title=f"Tier 2 Batches (GI: {ref_gi})")
    table.add_column("Batch ID", justify="right", style="cyan")
    table.add_column("Aggregators", style="magenta")
    if detailed:
        table.add_column("Submitted CID", style="green")
    table.add_column("Finalized", style="yellow")
    table.add_column("Final CID", style="white")
    
    for i in range(t2_count):
        bid, validators, finalized, cid_raw = task_coordinator_Contract.functions.getTier2Batch(ref_gi, i).call()
        cid = get_cid_from_bytes32(cid_raw.hex()) if cid_raw and cid_raw != bytes(32) else ""
        val_display = "\n".join([f"{v[:6]}...{v[-4:]}" for v in validators])
        if not detailed:
            table.add_row(str(bid), val_display, str(finalized), cid)
        else:
            submitted_parts = []
            for v in validators:
                sub_raw = task_coordinator_Contract.functions.t2SubmissionCID(ref_gi, bid, v).call()
                submitted_parts.append(get_cid_from_bytes32(sub_raw.hex()) if sub_raw and sub_raw != bytes(32) else "")
            submitted_cid_display = "\n".join(submitted_parts)
            table.add_row(str(bid), val_display, submitted_cid_display, str(finalized), cid)

    console.print(table)


@t1_app.command("start")
def start_t1_aggregation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T1nT2Bcreated","Can not start Tier 1 aggregation at this time.")
    
    console.print(f"[bold green]Starting Tier 1 Aggregation[/bold green]")

    try:
        tx = task_coordinator_Contract.functions.startT1Aggregation(ref_gi).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
        })
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")

        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt.status == 1:
            console.print("[green]✓ Tier 1 Aggregation started[/green]")
        else:
            console.print("[red]Tier 1 Aggregation started transaction failed[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error: Tier 1 Aggregation started transaction failed[/red] {e}")
        raise typer.Exit(1)

@t1_app.command("close")
def close_t1_aggregation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)
    
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T1AggregationStarted","Can not close Tier 1 aggregation at this time.")
    
    console.print(f"[bold green]Finalizing Tier 1 Aggregation[/bold green]")

    try:
        tx = task_coordinator_Contract.functions.finalizeT1Aggregation(ref_gi).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "nonce": w3.eth.get_transaction_count(account.address),
            "chainId": w3.eth.chain_id,
        })
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            console.print("[green]✓ Tier 1 Aggregation finalized[/green]")
        else:
            console.print("[red]Tier 1 Aggregation finalized transaction failed[/red]")
            raise typer.Exit(1)
    
    except Exception as e:
        console.print(f"[red]Error: Tier 1 Aggregation finalized transaction failed[/red] {e}")
        raise typer.Exit(1)

@t2_app.command("start")
def start_t2_aggregation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T1AggregationDone","Can not start Tier 2 aggregation at this time.")

    console.print(f"[bold green]Starting Tier 2 Aggregation[/bold green]")
    try:
        tx = task_coordinator_Contract.functions.startT2Aggregation(ref_gi).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "nonce": w3.eth.get_transaction_count(account.address),
        })
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            console.print("[green]✓ Tier 2 Aggregation started[/green]")
        else:
            console.print("[red]Tier 2 Aggregation started transaction failed[/red]")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: Tier 2 Aggregation started transaction failed[/red] {e}")
        raise typer.Exit(1)


@t2_app.command("close")
def close_t2_aggregation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T2AggregationStarted","Can not close Tier 2 aggregation at this time.")

    console.print(f"[bold green]Finalizing Tier 2 Aggregation[/bold green]")
    try:
        tx = task_coordinator_Contract.functions.finalizeT2Aggregation(ref_gi).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "nonce": w3.eth.get_transaction_count(account.address),
        })
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Tx hash: {tx_hash.hex()}[/dim]")
    
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            console.print("[green]✓ Tier 2 Aggregation finalized[/green]")
        else:
            console.print("[red]Tier 2 Aggregation finalized transaction failed[/red]")
            raise typer.Exit(1)

        # 2. Get Tier 2 batch to find final CID
        tier2_batch = task_coordinator_Contract.functions.getTier2Batch(ref_gi, 0).call()
        # (bid, validators, finalized, cid)
        finalCID_raw = tier2_batch[3]
        finalCID = get_cid_from_bytes32(finalCID_raw.hex()) if finalCID_raw and finalCID_raw != bytes(32) else None
        
        console.print(f"[cyan]Final CID:[/cyan] {finalCID}")

        # 3. Calculate score
        console.print("[cyan]Calculating score for final GM model...[/cyan]")


        manifest = get_manifest_key(effective_network, "getscoreforGM", model_id)
        model_base_path = Path(CACHE_DIR) / effective_network /  f"model_{model_id}"
        modelowner_service_path = model_base_path / Path(manifest["path"])
        model_service_path = model_base_path / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])

        if manifest["type"] == "custom":
            ctx.obj.ensure_file_exists(modelowner_service_path, manifest["ipfs"], "modelowner service")
            ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", model_id)["ipfs"], "model architecture service")

            fn = ctx.obj.load_custom_fn(
            modelowner_service_path,
            "getscoreforGM")

            ctx.obj.ensure_file_exists(Path(model_base_path)/"models"/"genesis_model.pth", get_manifest_key(effective_network,"Genesis_Model_CID", model_id), "genesis model")
            if not (Path(model_base_path)/"dataset"/"test"/"test_dataset.pt").exists():
                console.print("[red]Error:[/red] Test dataset not found at ", str(Path(model_base_path)/"dataset"/"test"/"test_dataset.pt"))
                console.print("[yellow]Warning:[/yellow] please ensure the test dataset is present at ", str(Path(model_base_path)/"dataset"/"test"/"test_dataset.pt"))
                raise typer.Exit(1) 
            accuracy = fn(curr_GI, finalCID, model_base_path)

        else:
            accuracy = getscoreforGM(curr_GI, finalCID)
        console.print(f"[green]Accuracy:[/green] {accuracy}")

        # 4. Set Tier 2 score
        console.print("[cyan]Setting Tier 2 score...[/cyan]")
        nonce = w3.eth.get_transaction_count(account.address)
        tx = task_coordinator_Contract.functions.setTier2Score(curr_GI, int(accuracy)).build_transaction({
            "from": account.address,
            "gas": 3000000,
            "gasPrice": w3.to_wei("5", "gwei"),
            "nonce": nonce,
        })
    
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Score Tx hash: {tx_hash.hex()}[/dim]")
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        if tx_receipt.status == 1:
            console.print("[green]✓ Tier 2 Aggregation finalized and score set[/green]")
        else:
            console.print("[red]Tier 2 score set transaction failed[/red]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error: Tier 2 Aggregation finalized and score set transactions failed[/red] {e}")
        raise typer.Exit(1)
    