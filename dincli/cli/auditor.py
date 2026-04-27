from pathlib import Path
import time

import typer
from rich.table import Table
from web3 import Web3
from dincli.cli.utils import CACHE_DIR, MIN_STAKE, get_manifest_key
from dincli.services.auditor import Score_model_by_auditor
from dincli.services.cid_utils import get_cid_from_bytes32

app = typer.Typer(help="Commands for Auditors in DIN.")

dintoken_app = typer.Typer(help="Commands for DIN Token in DIN.")
lms_evaluation_app = typer.Typer(help="Commands for LMS Evaluation in DIN.")

app.add_typer(dintoken_app, name="dintoken")
app.add_typer(lms_evaluation_app, name="lms-evaluation")

@dintoken_app.command(help="Buy DINTokens where amouunt is ETh to exchange for DINTokens")
def buy(ctx: typer.Context, 
        amount: float = typer.Argument(..., help="Amount of ETH to exchange for DINTokens")
    ):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console() 
    
    DinToken_contract = ctx.obj.get_deployed_din_token_contract()
    DinCoordinator_contract = ctx.obj.get_deployed_din_coordinator_contract()
        
    console.print("Auditor ETH balance: ", Web3.from_wei(w3.eth.get_balance(account.address), "ether"))
    console.print("Auditor DINToken balance: ", DinToken_contract.functions.balanceOf(account.address).call()/(10**18))

    console.print(f"[bold green]Buying DINTokens... for {amount} ETH[/bold green]")

    try:
        tx_params = ctx.obj.get_tx_params()
        tx_params["value"] = w3.to_wei(amount, "ether")
        tx_params["gas"] = int(w3.eth.estimate_gas(DinCoordinator_contract.functions.depositAndMint().build_transaction(tx_params)) * 1.1)  # Add 10% buffer
        
        tx = DinCoordinator_contract.functions.depositAndMint().build_transaction(tx_params)
    
        # Sign transaction
        signed_tx = account.sign_transaction(tx)
    
        # Send raw transaction
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
        if tx_receipt.status == 1:
            console.print(f"[bold green]✓ DINTokens bought at:[/bold green] {tx_receipt.transactionHash.hex()}")
            console.print("Auditor DINToken balance: ", Web3.from_wei(DinToken_contract.functions.balanceOf(account.address).call(), "ether"))
        else:
            console.print(f"[bold red]✗ Transaction failed! Could not buy DINTokens {tx_receipt.transactionHash.hex()}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Error buying DINTokens: {e}[/bold red]")


@dintoken_app.command(help="Stake DINTokens")
def stake(ctx: typer.Context, amount: int):     
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DinToken_contract, DinStake_contract = ctx.obj.get_deployed_din_token_contract(), ctx.obj.get_deployed_din_stake_contract()
    
    validator_Din_token_balance = DinToken_contract.functions.balanceOf(account.address).call()
    
    console.print("[bold green]Auditor ETH balance:[/bold green] ", Web3.from_wei(w3.eth.get_balance(account.address), "ether"))
    console.print("[bold green]Auditor DINToken balance:[/bold green] ", Web3.from_wei(validator_Din_token_balance, "ether"))
    
    if validator_Din_token_balance < MIN_STAKE:
        console.print(f"[bold red]✗ Could not stake DINTokens. Not enough DINTokens.[/bold red]")
        raise typer.Exit()
    else:
        console.print(f"[bold green]✓ Enough DINTokens to stake. [bold green]\n [bold green]Staking...[/bold green]")

        try:
            tx_params = ctx.obj.get_tx_params()
            tx_params["gas"] = int(w3.eth.estimate_gas(DinToken_contract.functions.approve(DinStake_contract.address, MIN_STAKE).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
            tx_approve = DinToken_contract.functions.approve(DinStake_contract.address, MIN_STAKE).build_transaction(tx_params)

            signed_tx_approve = account.sign_transaction(tx_approve)
            tx_hash_approve = w3.eth.send_raw_transaction(signed_tx_approve.raw_transaction)
            tx_receipt_approve = w3.eth.wait_for_transaction_receipt(tx_hash_approve)
                
            if tx_receipt_approve.status == 1:
                console.print(f"[bold green]✓ DINTokens approved for staking.[/bold green]")
            else:
                console.print(f"[bold red]✗ Could not approve DINTokens for staking.[/bold red]")
                raise typer.Exit()

            time.sleep(5)

            tx_params = ctx.obj.get_tx_params()
            tx_params["gas"] = int(w3.eth.estimate_gas(DinStake_contract.functions.stake(MIN_STAKE).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
            tx_stake = DinStake_contract.functions.stake(MIN_STAKE).build_transaction(tx_params)

            signed_tx_stake = account.sign_transaction(tx_stake)
            tx_hash_stake = w3.eth.send_raw_transaction(signed_tx_stake.raw_transaction)
            tx_receipt_stake = w3.eth.wait_for_transaction_receipt(tx_hash_stake)
        
            if tx_receipt_stake.status == 1:
                console.print(f"[bold green]✓ DINTokens staked.[/bold green]")
            else:
                console.print(f"[bold red]✗ Could not stake DINTokens.[/bold red]")
        except Exception as e:
            console.print(f"[bold red]✗ Error staking DINTokens: {e}[/bold red]")

@dintoken_app.command(help="Check stake")
def read_stake(ctx: typer.Context):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    DinStake_contract = ctx.obj.get_deployed_din_stake_contract()

    console.print("Auditor DIN token stake: ", Web3.from_wei(DinStake_contract.functions.getStake(account.address).call(), "ether"))


@app.command(help="Register as Auditor")
def register(
    ctx: typer.Context, 
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number")):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    DinCoordinator_contract, DinStake_contract = ctx.obj.get_deployed_din_coordinator_contract(), ctx.obj.get_deployed_din_stake_contract()
    
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract, True, False, True)

    ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(curr_GIstate, "DINauditorsRegistrationStarted", "Can not register auditor at this time")

    is_registered = taskAuditor_contract.functions.isRegisteredAuditor(curr_GI, account.address).call()
    
    if is_registered:
        console.print(f"[bold red]✗ Auditor already registered.[/bold red]")
        return
    else:
        console.print(f"[bold green]✓ Auditor not registered.[/bold green]")

        stake = DinStake_contract.functions.getStake(account.address).call()
            
        if stake < MIN_STAKE:
            console.print(f"[bold red]✗ Auditor does not have enough stake.[/bold red]")
            return
        else:
            console.print(f"[bold green]✓ Auditor has enough stake.[/bold green]")

            try:
                tx_params = ctx.obj.get_tx_params()
                tx_params["gas"] = int(w3.eth.estimate_gas(taskAuditor_contract.functions.registerDINAuditor(curr_GI).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
                tx_register = taskAuditor_contract.functions.registerDINAuditor(curr_GI).build_transaction(tx_params)

                signed_tx_register = account.sign_transaction(tx_register)
                tx_hash_register = w3.eth.send_raw_transaction(signed_tx_register.raw_transaction)
                tx_receipt_register = w3.eth.wait_for_transaction_receipt(tx_hash_register)
            
                if tx_receipt_register.status == 1:
                    console.print(f"[bold green]✓ Auditor registered.[/bold green]")
            except Exception as e:
                console.print(f"[bold red]✗ Could not register auditor. {e}[/bold red]")
                raise typer.Exit()

@lms_evaluation_app.command("show-batch", help="Show LMS evaluation batch")
def show_batch(
    ctx: typer.Context, 
    model_id: int = typer.Argument(..., help="Model ID"), 
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    batch: int = typer.Option(None, "--batch", help="Batch number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    task_coordinator_contract, task_auditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, curr_GIstate, "AuditorsBatchesCreated", "Can not show auditor batch at this time")


    console.print(f"[bold green]Showing auditor batch![/bold green]")
    
    audtor_batch_count = task_auditor_contract.functions.AuditorsBatchCount(ref_gi).call()

    raw_audit_batches = []
    model_idx_to_batch_id = {}
    model_idx_to_test_cid = {}
    auditor_batch = {"raw_batches": []}


    if batch:
        raw_audit_batches.append(task_auditor_contract.functions.getAuditorsBatch(ref_gi, batch).call())
    else:
        for i in range(audtor_batch_count):
            raw_audit_batches.append(task_auditor_contract.functions.getAuditorsBatch(ref_gi, i).call())
            time.sleep(1)

        for batch_data in raw_audit_batches:
            batch_id, auditors, model_indexes, test_cid_raw = batch_data
            test_cid = get_cid_from_bytes32(test_cid_raw.hex()) if test_cid_raw and test_cid_raw != bytes(32) else None

            if account.address.lower() in [a.lower() for a in auditors]:
                auditor_batch["raw_batches"].append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid})

        auditor_batch["batch_count"] = len(auditor_batch["raw_batches"])

        console.print("Auditor batch count: ", auditor_batch["batch_count"])


        relevant_lm_submissions = []
        table = Table(title=f"Auditor Batches for GI {curr_GI}", show_header=True, header_style="bold magenta")
        table.add_column("Batch ID", style="dim")
        table.add_column("Auditors", overflow="fold")
        table.add_column("Model Indexes", overflow="fold")
        table.add_column("Test CID")

        for batch in auditor_batch["raw_batches"]:
            relevant_lm_submissions.extend(batch["model_indexes"])
            for idx in batch["model_indexes"]:
                model_idx_to_batch_id[idx] = batch["batch_id"]
                model_idx_to_test_cid[idx] = batch["test_cid"]
            table.add_row(
            str(batch["batch_id"]),
            ", ".join(batch["auditors"]) if batch["auditors"] else "—",
            ", ".join(map(str, batch["model_indexes"])) if batch["model_indexes"] else "—",
            batch["test_cid"] if batch["test_cid"] else "—"
        )
    
        console.print(table)


        raw_lm_submissions = task_auditor_contract.functions.getClientModels(ref_gi).call()
        
        lm_submissions = {}

        assigned_lm_submissions = {}

        for idx, sub in enumerate(raw_lm_submissions):
            if idx not in relevant_lm_submissions:
                continue
            else:
                client, model_cid_raw, submitted_at, eligible, evaluated, approved, final_avg = sub
                model_cid = get_cid_from_bytes32(model_cid_raw.hex()) if model_cid_raw and model_cid_raw != bytes(32) else str(model_cid_raw)
                lm_submissions[idx] = {"model_index": idx, "client": client, "model_cid": model_cid, "submitted_at": submitted_at, "eligible": eligible, "evaluated": evaluated, "approved": approved, "final_avg": final_avg}

                batch_id = model_idx_to_batch_id[idx]

                try:
                    has_voted = task_auditor_contract.functions.hasAuditedLM(curr_GI, batch_id, account.address, idx).call()
                    time.sleep(0.5)
                except:
                    has_voted = False
                try:
                    is_eligible = task_auditor_contract.functions.LMeligibleVote(curr_GI, batch_id, account.address, idx).call()
                    time.sleep(0.5)
                except:
                    is_eligible = False
                try:
                    has_auditScores = task_auditor_contract.functions.auditScores(curr_GI, batch_id, account.address, idx).call()
                    time.sleep(0.5)
                except:
                    has_auditScores = False

                assigned_lm_submissions[idx] = {
                    "model_index": idx,
                    "client": client,
                    "model_cid": model_cid,
                    "submitted_at": submitted_at,
                    "batch_id": batch_id,
                    "has_voted": has_voted,
                    "is_eligible": is_eligible,
                    "has_auditScores": has_auditScores,
                    "test_cid": model_idx_to_test_cid[idx]

                }

        lm_submissions_table = Table(title=f"Relevant LM Submissions for GI {curr_GI} for auditor {account.address}", show_header=True, header_style="bold magenta")

        lm_submissions_table.add_column("Model Index", style="dim")
        lm_submissions_table.add_column("Client", overflow="fold")
        lm_submissions_table.add_column("Model CID", overflow="fold")
        lm_submissions_table.add_column("Submitted At", overflow="fold")
        lm_submissions_table.add_column("Eligible", overflow="fold")
        lm_submissions_table.add_column("Evaluated", overflow="fold")
        lm_submissions_table.add_column("Approved", overflow="fold")
        lm_submissions_table.add_column("Final Avg", overflow="fold")

        for sub in lm_submissions.values():
            lm_submissions_table.add_row(
                str(sub["model_index"]),
                str(sub["client"]),
                str(sub["model_cid"]),
                str(sub["submitted_at"]),
                str(sub["eligible"]),
                str(sub["evaluated"]),
                str(sub["approved"]),
                str(sub["final_avg"]) if sub["final_avg"] != "None" else "—"
            )
        console.print(lm_submissions_table)

        
        assigned_lm_submissions_table = Table(title=f"Evaluated/Assigned LM Submissions for GI {curr_GI} for auditor {account.address}", show_header=True, header_style="bold magenta")

        assigned_lm_submissions_table.add_column("Model Index", style="dim")
        assigned_lm_submissions_table.add_column("Client", overflow="fold")
        assigned_lm_submissions_table.add_column("Model CID", overflow="fold")
        assigned_lm_submissions_table.add_column("Submitted At", overflow="fold")
        assigned_lm_submissions_table.add_column("Batch ID", overflow="fold")
        assigned_lm_submissions_table.add_column("Has Voted", overflow="fold")
        assigned_lm_submissions_table.add_column("Is Eligible", overflow="fold")
        assigned_lm_submissions_table.add_column("Has AuditScores", overflow="fold")
        assigned_lm_submissions_table.add_column("Test CID", overflow="fold")
        
        for idx, sub in assigned_lm_submissions.items():
            assigned_lm_submissions_table.add_row(
                str(sub["model_index"]),
                str(sub["client"]),
                str(sub["model_cid"]),
                str(sub["submitted_at"]),
                str(sub["batch_id"]),
                str(sub["has_voted"]),
                str(sub["is_eligible"]),
                str(sub["has_auditScores"]),
                str(sub["test_cid"]) if sub["test_cid"] != "None" else "—"
            )
        console.print(assigned_lm_submissions_table)


@lms_evaluation_app.command("evaluate")
def evaluate_lms(
    ctx: typer.Context, 
    model_id: int = typer.Argument(..., help="Model index"),
    lmi: int = typer.Option(None, "--lmi", help="LM index"),
    batch: int = typer.Option(None, "--batch", help="Batch index"),
    submit: bool = typer.Option(False, "--submit", help="Submit evaluation"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    task_coordinator_contract, task_auditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(curr_GIstate, "LMSevaluationStarted", "Can not evaluate auditor batches at this time")
    
    audtor_batch_count = task_auditor_contract.functions.AuditorsBatchCount(curr_GI).call()
    
    genesis_model_cid_raw = task_coordinator_contract.functions.genesisModelIpfsHash().call()
    genesis_model_cid = get_cid_from_bytes32(genesis_model_cid_raw.hex())
    
    found_any = False

    for batch_id in range(audtor_batch_count):
        # Filter by batch arg if provided
        if batch is not None and batch != batch_id:
            continue

        time.sleep(0.5)

        audit_batch = task_auditor_contract.functions.getAuditorsBatch(curr_GI, batch_id).call()
        auditors_in_batch = audit_batch[1]
        model_indexes = audit_batch[2]
        testDataCID_raw = audit_batch[3]
        testDataCID = get_cid_from_bytes32(testDataCID_raw.hex()) if testDataCID_raw and testDataCID_raw != bytes(32) else None

        if account.address not in auditors_in_batch:
            # If user specifically requested this batch, warn them
            if batch is not None and batch == batch_id:
                console.print(f"[bold red]✗ You are not assigned to evaluate batch {batch_id}![/bold red]")
            continue

        for model_index in model_indexes:
            # Filter by lmi arg if provided
            if lmi is not None and lmi != model_index:
                continue

            found_any = True
            console.print(f"[bold green]Evaluating LM {model_index} from Audit batch {batch_id}![/bold green]")

            time.sleep(0.5)

            lms = task_auditor_contract.functions.lmSubmissions(curr_GI, model_index).call()
            lm_cid = get_cid_from_bytes32(lms[1].hex())

            model_base_dir = Path(CACHE_DIR) / effective_network / f"model_{model_id}"
            manifest = get_manifest_key(effective_network, "Score_model_by_auditor", model_id)
            auditor_service_path = model_base_dir / Path(manifest["path"])
            model_service_path = model_base_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])

            if manifest["type"] == "custom":

                ctx.obj.ensure_file_exists(auditor_service_path, manifest["ipfs"],"auditor service")
                ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", model_id)["ipfs"],"model service")
           
                fn = ctx.obj.load_custom_fn(
                auditor_service_path,
                "Score_model_by_auditor")
                
                score, eligible = fn(curr_GI, genesis_model_cid, batch_id, model_index, account.address, testDataCID, lm_cid, model_base_dir)
            
            else:
                score, eligible = Score_model_by_auditor(curr_GI, genesis_model_cid, batch_id, model_index, account.address, testDataCID, lm_cid, model_base_dir)

            console.print(f"Score: {score}")
            console.print(f"Eligible: {eligible}")

            if submit:
                try:
                    time.sleep(0.5)
                    tx_params = ctx.obj.get_tx_params()
                    tx_params["gas"] = int(w3.eth.estimate_gas(task_auditor_contract.functions.setAuditScorenEligibility(curr_GI, batch_id, model_index, int(score), bool(eligible)).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
                    tx = task_auditor_contract.functions.setAuditScorenEligibility(curr_GI, batch_id, model_index, int(score), bool(eligible)).build_transaction(tx_params)
                    signed_tx = account.sign_transaction(tx)
                    
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                    if receipt.status == 1:
                        console.print(f"[bold green]✓ Audit score and eligibility submitted successfully for LM {model_index} from batch {batch_id}![/bold green]")
                    else:
                        console.print(f"[bold red]✗ Audit score and eligibility submission failed for LM {model_index} from batch {batch_id}![/bold red]")
                except Exception as e:
                    console.print(f"[bold red]✗ Error submitting  Audit score and eligibility for LM {model_index} from batch {batch_id}: {e}[/bold red]")

    if not found_any:
        console.print("[yellow]No matching assigned auditor batches found.[/yellow]")