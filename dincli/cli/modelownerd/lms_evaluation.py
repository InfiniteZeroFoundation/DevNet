
import typer
from rich.table import Table

lms_evaluation_app = typer.Typer(help="Local Model Submission Evaluation commands")

@lms_evaluation_app.command()
def start(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)
    
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "AuditorsBatchesCreated",  "Can not start LMS evaluation at this time")
    
    console.print(f"[bold green]Starting LMS evaluation[/bold green]")

    try:
        tx = task_coordinator_Contract.functions.startLMsubmissionsEvaluation(ref_gi).build_transaction({
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
            console.print("[green]✓ LMS evaluation started[/green]")
        else:
            console.print("[red]Error:[/red] Failed to start LMS evaluation")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
    

@lms_evaluation_app.command()
def close(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    task_coordinator_Contract, task_auditor_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)
    
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "LMSevaluationStarted",  "Can not close LMS evaluation at this time")
    
    console.print(f"[bold green]Closing LMS evaluation![/bold green]")

    try:        
        tx = task_coordinator_Contract.functions.closeLMsubmissionsEvaluation(ref_gi).build_transaction({
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
            console.print("[green]✓ LMS evaluation closed![/green]")
        else:
            console.print("[red]Error:[/red] Failed to close LMS evaluation")
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)


@lms_evaluation_app.command("show")
def show(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    auditors: bool = typer.Option(False, "--auditors", help="Show auditor evaluations"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    models: bool = typer.Option(False, "--models", help="Show auditors lms evaluations per lms"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator_Contract, task_auditor_Contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(task_coordinator_Contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, GIstate, "AuditorsBatchesCreated",  "Can not show LMS evaluation at this time")

    console.print(f"[bold green]Showing LMS Evaluation for GI {ref_gi}[/bold green]")   
    
    raw_lm_submissions = task_auditor_Contract.functions.getClientModels(ref_gi).call()
    lm_submissions = {}
    for idx, sub in enumerate(raw_lm_submissions):
        client, model_cid, submitted_at, eligible, evaluated, approved, final_avg = sub
        lm_submissions[idx] = {
            "model_index": idx,
            "client": client,
            "model_cid": model_cid,
            "submitted_at": submitted_at,
            "eligible": eligible,
            "evaluated": evaluated,
            "approved": approved,
            "final_avg": final_avg,
        }

    audtor_batch_count = task_auditor_Contract.functions.AuditorsBatchCount(ref_gi).call()
    model_idx_to_batch_id = {}
    model_idx_to_test_cid = {}
    batch_id_to_auditors = {}
    model_idx_to_auditors = {}
    all_auditors = set()

    if auditors or models:
        raw_audit_batches = []
        for i in range(audtor_batch_count):
            batch = task_auditor_Contract.functions.getAuditorsBatch(ref_gi, i).call()
            if batch:
                raw_audit_batches.append(batch)

        for batch_data in raw_audit_batches:
            batch_id, batch_auditors, model_indexes, test_cid = batch_data
            batch_id_to_auditors[batch_id] = list(batch_auditors)
            for m_idx in model_indexes:
                model_idx_to_batch_id[m_idx] = batch_id
                model_idx_to_test_cid[m_idx] = test_cid
                # collect auditors assigned to each model
                model_idx_to_auditors.setdefault(m_idx, set()).update(batch_auditors)
            all_auditors.update(batch_auditors)

        # normalize model_idx_to_auditors sets to lists
        for k in model_idx_to_auditors:
            model_idx_to_auditors[k] = sorted(model_idx_to_auditors[k])

    # If auditors view requested: build per-auditor assigned models and their on-chain states
    assigned_lm_submissions = {}
    if auditors:
        for auditor_addr in sorted(all_auditors):
            assigned_lm_submissions[auditor_addr] = []
            # find models assigned to this auditor by scanning model_idx_to_auditors
            for model_idx, auditors_list in model_idx_to_auditors.items():
                if auditor_addr not in auditors_list:
                    continue
                batch_id = model_idx_to_batch_id.get(model_idx)
                has_voted = task_auditor_Contract.functions.hasAuditedLM(ref_gi, batch_id, auditor_addr, model_idx).call()
                is_eligible = task_auditor_Contract.functions.LMeligibleVote(ref_gi, batch_id, auditor_addr, model_idx).call()
                audit_scores = task_auditor_Contract.functions.auditScores(ref_gi, batch_id, auditor_addr, model_idx).call()

                lm = lm_submissions.get(model_idx)
                client = lm["client"] if lm else "Unknown"
                model_cid = lm["model_cid"] if lm else "N/A"
                test_cid = model_idx_to_test_cid.get(model_idx)

                assigned_lm_submissions[auditor_addr].append({
                    "model_index": model_idx,
                    "client": client,
                    "model_cid": model_cid,
                    "batch_id": batch_id,
                    "has_voted": has_voted,
                    "is_eligible": is_eligible,
                    "audit_scores": audit_scores,
                    "test_cid": test_cid,
                })

    # Print LM submissions table (keeps your existing output)
    lm_submissions_table = Table(title=f"LM Submissions for GI {curr_GI}", show_header=True, header_style="bold magenta")
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

    # Print per-auditor assigned tables if requested
    if auditors:
        for auditor_addr in sorted(assigned_lm_submissions.keys()):
            assigned_lm_submissions_table = Table(
                title=f"Assigned LM Submissions for GI {curr_GI} for auditor {auditor_addr}",
                show_header=True,
                header_style="bold magenta"
            )
            assigned_lm_submissions_table.add_column("Model Index", style="dim")
            assigned_lm_submissions_table.add_column("Client", overflow="fold")
            assigned_lm_submissions_table.add_column("Model CID", overflow="fold")
            assigned_lm_submissions_table.add_column("Batch ID", overflow="fold")
            assigned_lm_submissions_table.add_column("Has Voted", overflow="fold")
            assigned_lm_submissions_table.add_column("Is Eligible", overflow="fold")
            assigned_lm_submissions_table.add_column("Audit Scores", overflow="fold")
            assigned_lm_submissions_table.add_column("Test CID", overflow="fold")

            for sub in assigned_lm_submissions[auditor_addr]:
                assigned_lm_submissions_table.add_row(
                    str(sub["model_index"]),
                    str(sub["client"]),
                    str(sub["model_cid"]),
                    str(sub["batch_id"]),
                    str(sub["has_voted"]),
                    str(sub["is_eligible"]),
                    str(sub["audit_scores"]) if sub["audit_scores"] is not None else "—",
                    str(sub["test_cid"]) if sub["test_cid"] is not None else "—"
                )
            console.print(assigned_lm_submissions_table)

    # Print per-model evaluation tables if requested (--models)
    if models:
        # iterate through all models (sorted)
        for model_idx in sorted(lm_submissions.keys()):
            batch_id = model_idx_to_batch_id.get(model_idx)
            auditors_for_model = model_idx_to_auditors.get(model_idx, [])
            model_eval_table = Table(title=f"Evaluations for Model {model_idx} (GI {curr_GI})", show_header=True, header_style="bold cyan")
            model_eval_table.add_column("Auditor", overflow="fold")
            model_eval_table.add_column("Batch ID", style="dim")
            model_eval_table.add_column("Has Voted")
            model_eval_table.add_column("Is Eligible")
            model_eval_table.add_column("Audit Scores", overflow="fold")

            if not auditors_for_model:
                model_eval_table.add_row("—", str(batch_id) if batch_id is not None else "—", "—", "—", "—")
            else:
                for auditor_addr in auditors_for_model:
                    has_voted = task_auditor_Contract.functions.hasAuditedLM(ref_gi, batch_id, auditor_addr, model_idx).call()
                    is_eligible = task_auditor_Contract.functions.LMeligibleVote(ref_gi, batch_id, auditor_addr, model_idx).call()
                    audit_scores = task_auditor_Contract.functions.auditScores(ref_gi, batch_id, auditor_addr, model_idx).call()
                    model_eval_table.add_row(
                        str(auditor_addr),
                        str(batch_id),
                        str(has_voted),
                        str(is_eligible),
                        str(audit_scores) if audit_scores is not None else "—"
                    )
            console.print(model_eval_table)
            test_cid = model_idx_to_test_cid.get(model_idx)
            if test_cid:
                console.print(f"[dim]Test CID for model {model_idx}'s batch: {test_cid}[/dim]")
