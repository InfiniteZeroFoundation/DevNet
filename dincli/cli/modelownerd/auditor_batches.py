from pathlib import Path

import typer
from rich.table import Table

from dincli.cli.utils import CACHE_DIR, get_manifest_key
from dincli.services.modelowner import create_audit_testDataCIDs

auditor_batches_app = typer.Typer(help="Auditor Batches commands")

@auditor_batches_app.command()
def create(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "LMSclosed", "Can not create auditor batches at this time")
    
    console.print(f"[bold green]Creating auditor batches [/bold green]")

    try:
    
        tx = taskCoordinator_contract.functions.createAuditorsBatches(ref_gi).build_transaction({
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
            console.print(f"[dim]Auditor batches created tx:[/dim] {tx_hash.hex()}")
            console.print("[green]✓ Auditor batches created![/green]")
        else:
            console.print("[red]Error:[/red] Auditor batches creation failed")
            raise typer.Exit(1) 
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

@auditor_batches_app.command()
def show(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskauditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, GIstate, "AuditorsBatchesCreated", "Can not show auditor batches at this time")

    
    console.print(f"[bold green]Showing auditor batches for global iteration {ref_gi}![/bold green]")

    try:
        audtor_batch_count = taskauditor_contract.functions.AuditorsBatchCount(ref_gi).call()

        console.print(f"[bold green]Auditor batches count:[/bold green] {audtor_batch_count}")

        raw_audit_batches = []
        processed_audit_batches = []
    
        for i in range(audtor_batch_count):
            raw_audit_batches.append(taskauditor_contract.functions.getAuditorsBatch(ref_gi, i).call())

        for batch in raw_audit_batches:
            batch_id, auditors, model_indexes, test_cid = batch
            processed_audit_batches.append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid or "None"})
            
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

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

@auditor_batches_app.command("create-testdataset")
def create_testdataset(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit test dataset to TaskCoordinator"),
    test_data_path: str = typer.Option(None, "--test-data-path", help="Path to test dataset"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskauditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "AuditorsBatchesCreated", "Can not create test dataset at this time")

    console.print(f"[bold green]Creating test dataset![/bold green]")

    audtor_batch_count = taskauditor_contract.functions.AuditorsBatchCount(ref_gi).call()

    model_base_path = Path(CACHE_DIR) / effective_network /  f"model_{model_id}"
    manifest = get_manifest_key(effective_network, "create_audit_testDataCIDs", model_id)
    modelowner_service_path = model_base_path / Path(manifest["path"])

    if manifest["type"] == "custom":
        ctx.obj.ensure_file_exists(modelowner_service_path, manifest["ipfs"], "model owner service")
        fn = ctx.obj.load_custom_fn(modelowner_service_path, "create_audit_testDataCIDs")
        audit_testDataCIDs = fn(audtor_batch_count, curr_GI, str(model_base_path), test_data_path)
        #audit_testDataCIDs = ['QmYHc4Y6pmMKFohYDJXkFCCrLAQBUhwGuD6ebGZUxi34ea', 'QmSvTuP4XmcNnaYAqYkv6ewUKU7v2PCAnnLB9DqE7MTrAg', 'QmSdiTciKYBTxHKntjY3Pko8szD5D1nXVLU2mVWrsZhWdE', 'QmcLCGEz9FDHti6c2PPUqAh8rzGpQSwFAZi4QifcYkQB49', 'QmRZydYdpcHTpSSNy7MsX2K29KuUwEsoRxDkT9NEHqu6CQ', 'QmfBeoeqxb3SecGj4qUWcYYZ5AtCsUPyBn8deUj4RQofxw']
    else:
        audit_testDataCIDs = create_audit_testDataCIDs(audtor_batch_count, curr_GI)
    
    console.print("audit_testDataCIDs", audit_testDataCIDs)
    
    console.print(f"[bold green] ✓ Created test subdatasets![/bold green]")

    if submit:

        console.print(f"[bold green]Assigning test dataset![/bold green]")

        try:
            for batch_id in range(audtor_batch_count):
                tx = taskauditor_contract.functions.assignAuditTestDataset(curr_GI, batch_id, audit_testDataCIDs[batch_id]).build_transaction({
                    "from": account.address,
                    "nonce": w3.eth.get_transaction_count(account.address),
                    "gas": 3000000,
                    "gasPrice": w3.to_wei("5", "gwei"),
                    "chainId": w3.eth.chain_id
                })

                signed_tx = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                if receipt.status == 1:
                    console.print("[green]✓ Test dataset assigned for auditor batch :", batch_id)
                else:
                    console.print("[red]Error:[/red] Failed to assign test dataset for auditor batch :", batch_id)

            tx = taskCoordinator_contract.functions.setTestDataAssignedFlag(curr_GI, True).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 3000000,
                "gasPrice": w3.to_wei("5", "gwei"),
                "chainId": w3.eth.chain_id
            })
            signed_tx = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

            if receipt.status == 1:
                console.print("[green]✓ Test dataset assigned for auditor batches[/green]")
            else:
                console.print("[red]Error:[/red] Failed to set test dataset assigned flag")
                raise typer.Exit(1)
        except Exception as e:
            console.print("[red]Error:[/red] Failed to assign test dataset for auditor batches")
            raise typer.Exit(1)
            