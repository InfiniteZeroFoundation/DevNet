import typer
from rich import print
from rich.table import Table
from typing import Optional
from rich.console import Console
from pathlib import Path
from dotenv import dotenv_values, set_key, get_key, unset_key
from dincli.utils import resolve_network, get_w3, load_account, load_din_info, load_usdt_config, GIstateToStr, GIstatestrToIndex
from dincli.contract_utils import get_contract_instance
from dincli.services.auditor import Score_model_by_auditor

app = typer.Typer(help="Commands for Auditors in DIN.")
console = Console()

MIN_STAKE = 1000000*10**18

dintoken_app = typer.Typer(help="Commands for DIN Token in DIN.")
lms_evaluation_app = typer.Typer(help="Commands for LMS Evaluation in DIN.")

app.add_typer(dintoken_app, name="dintoken")
app.add_typer(lms_evaluation_app, name="lms-evaluation")

@dintoken_app.command(help="Buy DINTokens where amouunt is ETh to exchange for DINTokens")
def buy(amount: int, network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),):

    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    artifact_path = Path(__file__).parent / "abis" / "DinToken.json"
    
    din_addresses = load_din_info()
    dintoken_address = din_addresses[effective_network]["token"] 
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 
    
    DinToken_contract = get_contract_instance(artifact_path, effective_network, dintoken_address)
    
    artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    
    DinCoordinator_contract = get_contract_instance(artifact_path, effective_network, dincoordinator_address)
    
    # Load account
    account = load_account()

    
    print("Auditor address: ", account.address)
    print("Auditor ETH balance: ", w3.eth.get_balance(account.address))
    print("DINToken address: ", dintoken_address)
    print("DINCoordinator address: ", dincoordinator_address)
    print("Auditor DINToken balance: ", DinToken_contract.functions.balanceOf(account.address).call())

    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)

    
    # Build transaction
    tx = DinCoordinator_contract.functions.depositAndMint().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": int(3000000),  # Match FastAPI route
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
        "value": w3.to_wei(amount, "ether"),
    })
    
    # Sign transaction
    signed_tx = account.sign_transaction(tx)
    
    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    if tx_receipt.status == 1:
        print(f"[bold green]✓ DINTokens bought at:[/bold green] {tx_receipt.transactionHash.hex()}")
    else:
        print(f"[bold red]✗ Transaction failed! Could not buy DINTokens.[/bold red]")
        return
    print("Auditor DINToken balance: ", DinToken_contract.functions.balanceOf(account.address).call())

@dintoken_app.command(help="Stake DINTokens")
def stake(amount: int, network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),):     
    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)
    
    token_artifact_path = Path(__file__).parent / "abis" / "DinToken.json"
    stake_artifact_path = Path(__file__).parent / "abis" / "DinValidatorStake.json"
    coordinator_artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    
    din_addresses = load_din_info()
    dintoken_address = din_addresses[effective_network]["token"] 
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 
    dinstake_address = din_addresses[effective_network]["stake"] 
    
    DinToken_contract = get_contract_instance(token_artifact_path, effective_network, dintoken_address)
    
    DinStake_contract = get_contract_instance(stake_artifact_path, effective_network, dinstake_address)
    
    DinCoordinator_contract = get_contract_instance(coordinator_artifact_path, effective_network, dincoordinator_address)
    
    # Load account
    account = load_account()
    
    validator_Din_token_balance = DinToken_contract.functions.balanceOf(account.address).call()
    
    console.print("Auditor address: ", account.address)
    console.print("Auditor ETH balance: ", w3.eth.get_balance(account.address))
    console.print("DINToken address: ", dintoken_address)
    console.print("Auditor DINToken balance: ", validator_Din_token_balance)
    console.print("DINStake address: ", dinstake_address)
    
    
    if validator_Din_token_balance < MIN_STAKE:
        console.print(f"[bold red]✗ Could not stake DINTokens. Not enough DINTokens.[/bold red]")
    else:
        console.print(f"[bold green]✓ Enough DINTokens to stake.[/bold green]")

        tx_approve = DinToken_contract.functions.approve(dinstake_address, MIN_STAKE).build_transaction({"from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": int(3000000),  
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
        })

        # Sign transaction
        signed_tx_approve = account.sign_transaction(tx_approve)
        
        # Send raw transaction
        tx_hash_approve = w3.eth.send_raw_transaction(signed_tx_approve.raw_transaction)

                
        tx_receipt_approve = w3.eth.wait_for_transaction_receipt(tx_hash_approve)
                
        if tx_receipt_approve.status == 1:
            console.print(f"[bold green]✓ DINTokens approved for staking.[/bold green]")
        else:
            console.print(f"[bold red]✗ Could not approve DINTokens for staking.[/bold red]")

        tx_stake = DinStake_contract.functions.stake(MIN_STAKE).build_transaction({"from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": int(3000000),  
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
        })

        # Sign transaction
        signed_tx_stake = account.sign_transaction(tx_stake)
        
        # Send raw transaction
        tx_hash_stake = w3.eth.send_raw_transaction(signed_tx_stake.raw_transaction)
        tx_receipt_stake = w3.eth.wait_for_transaction_receipt(tx_hash_stake)
        
        if tx_receipt_stake.status == 1:
            console.print(f"[bold green]✓ DINTokens staked.[/bold green]")
        else:
            console.print(f"[bold red]✗ Could not stake DINTokens.[/bold red]")



@dintoken_app.command(help="Check stake")
def read_stake(network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)")):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    din_addresses = load_din_info()
    dinstake_address = din_addresses[effective_network]["stake"] 

    
    account = load_account()
    
    stake_artifact_path = Path(__file__).parent / "abis" / "DinValidatorStake.json"
    DinStake_contract = get_contract_instance(stake_artifact_path, effective_network, dinstake_address)
    

    console.print("Auditor address: ", account.address)
    console.print("DINStake address: ", dinstake_address)
    console.print("Auditor DIN token stake: ", DinStake_contract.functions.getStake(account.address).call())


@app.command(help="Register as Auditor")
def register(network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
taskCoordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
taskAuditor: str = typer.Option(None, "--taskAuditor", help="Task auditor address")):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    din_addresses = load_din_info()
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 
    dinstake_address = din_addresses[effective_network]["stake"]

    
    env_config = dotenv_values(".env")

    if taskCoordinator is None:
        taskCoordinator = env_config.get("DINTaskCoordinator_Contract_Address")

    if taskAuditor is None:
        taskAuditor = env_config.get("DINTaskAuditor_Contract_Address")

    taskCoordinator_artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    taskCoordinator_contract = get_contract_instance(taskCoordinator_artifact_path, effective_network, taskCoordinator)

    taskAuditor_artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    taskAuditor_contract = get_contract_instance(taskAuditor_artifact_path, effective_network, taskAuditor)
    
    coordinator_artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    DinCoordinator_contract = get_contract_instance(coordinator_artifact_path, effective_network, dincoordinator_address)

    stake_artifact_path = Path(__file__).parent / "abis" / "DinValidatorStake.json"
    DinStake_contract = get_contract_instance(stake_artifact_path, effective_network, dinstake_address)
    
    account = load_account()
    
    curr_GI = taskCoordinator_contract.functions.GI().call()
    
    curr_GIstate = taskCoordinator_contract.functions.GIstate().call()

    if GIstateToStr(curr_GIstate) != "DINauditorRegistrationStarted":
        console.print(f"[bold red]✗ Can not register validators at this time. Current state: {GIstateToStr(curr_GIstate)} for GI {curr_GI} where taskAuditor is {taskAuditor}[/bold red]")
        return

    
    registered_auditors = taskAuditor_contract.functions.getDINtaskAuditors(curr_GI).call()

    
    console.print("Auditor address: ", account.address)
    console.print("DIN task Auditor address: ", taskAuditor)
    console.print("DIN task Coordinator address: ", taskCoordinator)
    console.print("Current GI: ", curr_GI)
    console.print("Current GI state: ", GIstateToStr(curr_GIstate))
    console.print("Registered Auditors: ", registered_auditors)
    if account.address in registered_auditors:
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

            tx_register = taskAuditor_contract.functions.registerDINAuditor(curr_GI).build_transaction({"from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": int(3000000),  
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
            })

            # Sign transaction
            signed_tx_register = account.sign_transaction(tx_register)
            
            # Send raw transaction
            tx_hash_register = w3.eth.send_raw_transaction(signed_tx_register.raw_transaction)
            tx_receipt_register = w3.eth.wait_for_transaction_receipt(tx_hash_register)
            
            if tx_receipt_register.status == 1:
                console.print(f"[bold green]✓ Auditor registered.[/bold green]")
            else:
                console.print(f"[bold red]✗ Could not register auditor.[/bold red]")




@lms_evaluation_app.command(help="")
def show_batch(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="DINTaskAuditor contract address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    batch: int = typer.Option(None, "--batch", help="Batch number"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    env_config = dotenv_values(".env")
    
    if task_coordinator is None:
        task_coordinator = env_config.get("DINTaskCoordinator_Contract_Address")
    if task_auditor is None:
        task_auditor = env_config.get("DINTaskAuditor_Contract_Address")

    task_coordinator_artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    if not task_coordinator_artifact_path.exists():
        console.print("[red]Error:[/red] task_coordinator ABI file not found")
        raise typer.Exit(1)

    task_coordinator_contract = get_contract_instance(task_coordinator_artifact_path, effective_network, task_coordinator)

    task_auditor_artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    if not task_auditor_artifact_path.exists():
        console.print("[red]Error:[/red] task_auditor ABI file not found")
        raise typer.Exit(1)
    task_auditor_contract = get_contract_instance(task_auditor_artifact_path, effective_network, task_auditor)

    curr_GI = task_coordinator_contract.functions.GI().call()
    curr_GIstate = task_coordinator_contract.functions.GIstate().call()


    if gi:
        if gi != curr_GI:
            console.print(f"[bold red]✗ invalid Global iteration number {gi}. Current GI: {curr_GI}[/bold red]")
            return

    console.print("Auditor address: ", account.address)
    console.print("DIN task Auditor address: ", task_auditor)
    console.print("DIN task Coordinator address: ", task_coordinator)
    console.print("Current GI: ", curr_GI)

    if curr_GI < 1 or curr_GIstate < GIstatestrToIndex("AuditorsBatchesCreated"):
        console.print("[red]Error:[/red] Can not show auditor batches at this time as GIstate is ",GIstateToStr(curr_GIstate))
        raise typer.Exit(1)

    console.print(f"[bold green]Showing auditor batch![/bold green]")
    
    audtor_batch_count = task_auditor_contract.functions.AuditorsBatchCount(curr_GI).call()

    raw_audit_batches = []
    model_idx_to_batch_id = {}
    model_idx_to_test_cid = {}
    auditor_batch = {"raw_batches": []}


    if batch:
        raw_audit_batches.append(task_auditor_contract.functions.getAuditorsBatch(curr_GI, batch).call())
    else:
        for i in range(audtor_batch_count):
            raw_audit_batches.append(task_auditor_contract.functions.getAuditorsBatch(curr_GI, i).call())

    for batch_data in raw_audit_batches:
        batch_id, auditors, model_indexes, test_cid = batch_data

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
            batch["test_cid"] if batch["test_cid"] != "None" else "—"
        )
    
    console.print(table)


    raw_lm_submissions = task_auditor_contract.functions.getClientModels(curr_GI).call()
    
    lm_submissions = {}

    assigned_lm_submissions = {}

    for idx, sub in enumerate(raw_lm_submissions):
        if idx not in relevant_lm_submissions:
            continue
        else:
            client, model_cid, submitted_at, eligible, evaluated, approved, final_avg = sub
            lm_submissions[idx] = {"model_index": idx, "client": client, "model_cid": model_cid, "submitted_at": submitted_at, "eligible": eligible, "evaluated": evaluated, "approved": approved, "final_avg": final_avg}

            batch_id = model_idx_to_batch_id[idx]

            try:
                has_voted = task_auditor_contract.functions.hasAuditedLM(curr_GI, batch_id, account.address, idx).call()
            except:
                has_voted = False
            try:
                is_eligible = task_auditor_contract.functions.LMeligibleVote(curr_GI, batch_id, account.address, idx).call()
            except:
                is_eligible = False
            try:
                has_auditScores = task_auditor_contract.functions.auditScores(curr_GI, batch_id, account.address, idx).call()
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

    
    assigned_lm_submissions_table = Table(title=f"Assigned LM Submissions for GI {curr_GI} for auditor {account.address}", show_header=True, header_style="bold magenta")

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
    network: str = typer.Option("local", "--network", help="Network to connect to"),
    lmi: int = typer.Option(None, "--lmi", help="LM index"),
    batch: int = typer.Option(None, "--batch", help="Batch index"),
    submit: bool = typer.Option(False, "--submit", help="Submit evaluation"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="DINTaskAuditor contract address"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="DINTaskCoordinator contract address"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    env_config = dotenv_values(".env")
    

    
    if task_coordinator is None:
        task_coordinator = env_config.get("DINTaskCoordinator_Contract_Address")
    if task_auditor is None:
        task_auditor = env_config.get("DINTaskAuditor_Contract_Address")

    task_coordinator_artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    if not task_coordinator_artifact_path.exists():
        console.print("[red]Error:[/red] task_coordinator ABI file not found")
        raise typer.Exit(1)

    task_coordinator_contract = get_contract_instance(task_coordinator_artifact_path, effective_network, task_coordinator)

    task_auditor_artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    if not task_auditor_artifact_path.exists():
        console.print("[red]Error:[/red] task_auditor ABI file not found")
        raise typer.Exit(1)
    task_auditor_contract = get_contract_instance(task_auditor_artifact_path, effective_network, task_auditor)

    curr_GI = task_coordinator_contract.functions.GI().call()
    curr_GIstate = task_coordinator_contract.functions.GIstate().call()

    if gi:
        if gi != curr_GI:
            console.print(f"[bold red]✗ invalid Global iteration number {gi}. Current GI: {curr_GI}[/bold red]")
            return

    console.print("Auditor address: ", account.address)
    console.print("DIN task Auditor address: ", task_auditor)
    console.print("DIN task Coordinator address: ", task_coordinator)
    console.print("Current GI: ", curr_GI)
    console.print("Current GI state: ", GIstateToStr(curr_GIstate))
    
    if curr_GI < 1 or curr_GIstate < GIstatestrToIndex("LMSevaluationStarted"):
        console.print("[red]Error:[/red] Can not evaluate auditor batches at this time as GIstate is ",GIstateToStr(curr_GIstate))
        raise typer.Exit(1)

    audtor_batch_count = task_auditor_contract.functions.AuditorsBatchCount(curr_GI).call()
    
    genesis_model_cid = task_coordinator_contract.functions.genesisModelIpfsHash().call()
    
    found_any = False

    for batch_id in range(audtor_batch_count):
        # Filter by batch arg if provided
        if batch is not None and batch != batch_id:
            continue

        audit_batch = task_auditor_contract.functions.getAuditorsBatch(curr_GI, batch_id).call()
        auditors_in_batch = audit_batch[1]
        model_indexes = audit_batch[2]
        testDataCID = audit_batch[3]

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
            console.print(f"[bold green]Evaluating LM {model_index} from batch {batch_id}![/bold green]")

            lms = task_auditor_contract.functions.lmSubmissions(curr_GI, model_index).call()
            lm_cid = lms[1]
            
            score, eligible = Score_model_by_auditor(curr_GI, genesis_model_cid, batch_id, model_index, account.address, testDataCID, lm_cid)

            console.print(f"Score: {score}")
            console.print(f"Eligible: {eligible}")

            if submit:
                try:
                    tx = task_auditor_contract.functions.setAuditScorenEligibility(curr_GI, batch_id, model_index, int(score), bool(eligible)).build_transaction({
                        'from': account.address,
                        "gas": int(3000000),
                        "gasPrice": w3.to_wei("5", "gwei"),
                        'nonce': w3.eth.get_transaction_count(account.address),
                        "chainId": w3.eth.chain_id})
                    signed_tx = account.sign_transaction(tx)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                    if receipt.status == 1:
                        console.print(f"[bold green]✓ Audit score and eligibility submitted successfully for LM {model_index} from batch {batch_id}![/bold green]")
                    else:
                        console.print(f"[bold red]✗ Audit score and eligibility submission failed for LM {model_index} from batch {batch_id}![/bold red]")
                except Exception as e:
                     console.print(f"[bold red]✗ Error submitting for LM {model_index}: {e}[/bold red]")

    if not found_any:
        console.print("[yellow]No matching assigned tasks found.[/yellow]")

        
        
        
    
            



    
        



    
    
    
    
    
    
    


    



    
    