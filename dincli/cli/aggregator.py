from pathlib import Path

import typer
from rich.table import Table
from web3 import Web3

from dincli.cli.utils import CACHE_DIR, MIN_STAKE, get_manifest_key
from dincli.services.aggregator import get_aggregated_cid
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32

app = typer.Typer(help="Commands for Aggregators in DIN.")

dintoken_app = typer.Typer(help="Commands for DIN Token in DIN.")
app.add_typer(dintoken_app, name="dintoken")


@dintoken_app.command(help="Buy DINTokens where amount is ETh to exchange for DINTokens")
def buy(ctx: typer.Context, 
        amount: float = typer.Argument(..., help="Amount of ETH to exchange for DINTokens")
    ):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINToken_contract = ctx.obj.get_deployed_din_token_contract()
    DinCoordinator_contract = ctx.obj.get_deployed_din_coordinator_contract()
    
    console.print("[bold green]Aggregator ETH balance:[/bold green] ", Web3.from_wei(w3.eth.get_balance(account.address), "ether"))
    console.print("[bold green]Aggregator DINToken balance:[/bold green] ", DINToken_contract.functions.balanceOf(account.address).call()/(10**18))

    console.print(f"[bold green]Buying DINTokens... for {amount} ETH[/bold green]")

    try:
        nonce = w3.eth.get_transaction_count(account.address)
    
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
            console.print(f"[bold green]✓ DINTokens bought at:[/bold green] {tx_receipt.transactionHash.hex()}")
            console.print("Aggregator DINToken balance: ", Web3.from_wei(DINToken_contract.functions.balanceOf(account.address).call(), "ether"))
        else:
            console.print(f"[bold red]✗ Transaction failed! Could not buy DINTokens {tx_receipt.transactionHash.hex()}[/bold red]")
    except Exception as e:
        console.print(f"[bold red]✗ Error buying DINTokens: {e}[/bold red]")
    
@dintoken_app.command(help="Stake DINTokens")
def stake(ctx: typer.Context, amount: int):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DinToken_contract, DinStake_contract = ctx.obj.get_deployed_din_token_contract(), ctx.obj.get_deployed_din_stake_contract()

    aggregator_Din_token_balance = DinToken_contract.functions.balanceOf(account.address).call()

    console.print(f"[bold green]Aggregator ETH balance:[/bold green] {w3.eth.get_balance(account.address)}")
    console.print(f"[bold green]Aggregator DINToken balance:[/bold green] {aggregator_Din_token_balance}")
    
    if aggregator_Din_token_balance < MIN_STAKE:
        console.print(f"[bold red]✗ Could not stake DINTokens. Not enough DINTokens.[/bold red]")
    else:
        console.print(f"[bold green]✓ Enough DINTokens to stake. [bold green]\n [bold green]Staking...[/bold green]")

        try:

            tx_approve = DinToken_contract.functions.approve(DinStake_contract.address, MIN_STAKE).build_transaction({"from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": int(3000000),  
            "gasPrice": w3.to_wei("5", "gwei"),
            "chainId": w3.eth.chain_id,
            })

            signed_tx_approve = account.sign_transaction(tx_approve)
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

            signed_tx_stake = account.sign_transaction(tx_stake)
        
            tx_hash_stake = w3.eth.send_raw_transaction(signed_tx_stake.raw_transaction)
                
            tx_stake_receipt = w3.eth.wait_for_transaction_receipt(tx_hash_stake) 

            if tx_stake_receipt.status == 1:
                console.print(f"[bold green]✓ DINTokens staked.[/bold green]")
            else:
                console.print(f"[bold red]✗ Could not stake DINTokens.[/bold red]")
        except Exception as e:
            console.print(f"[bold red]✗ Could not stake DINTokens. {e}[/bold red]")

@dintoken_app.command("read-stake", help="Check stake")
def read_stake(ctx: typer.Context):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DinStake_contract = ctx.obj.get_deployed_din_stake_contract()

    console.print("Aggregator staked DIN tokens : ", DinStake_contract.functions.getStake(account.address).call())

@app.command(help="Register as aggregator")
def register(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number")):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    DinStake_contract = ctx.obj.get_deployed_din_stake_contract()

    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract, True, False, True)

    ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(curr_GIstate, "DINaggregatorsRegistrationStarted", "Can not register aggregator at this time")

    is_registered = taskCoordinator_contract.functions.isDINAggregator(curr_GI, account.address).call()
    
    if is_registered:
        console.print(f"[bold red]✗ Aggregator already registered.[/bold red]")
        return
    else:
        console.print(f"[bold green]✓ Aggregator not registered.[/bold green]")

        stake = DinStake_contract.functions.getStake(account.address).call()
            
        if stake < MIN_STAKE:
            console.print(f"[bold red]✗ Aggregator does not have enough stake.[/bold red]")
            return
        else:
            console.print(f"[bold green]✓ Aggregator has enough stake.[/bold green]")

            try:
    
                tx = taskCoordinator_contract.functions.registerDINaggregator(curr_GI).build_transaction({
                    "from": account.address, 
                    "nonce": w3.eth.get_transaction_count(account.address), 
                    "gas": int(3000000), 
                    "gasPrice": w3.to_wei("5", "gwei"), 
                    "chainId": w3.eth.chain_id})
                
                # Sign transaction
                signed_tx = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
                if tx_receipt.status == 1:
                    console.print(f"[bold green]✓ Aggregator registered.[/bold green]")
            except Exception as e:
                console.print(f"[bold red]✗ Could not register aggregator. {e}[/bold red]")
    
  
   
@app.command("show-t1-batches", help="Show T1 batches")    
def show_t1_batches(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI,GIstate, "T1nT2Bcreated", "Can not show T1 batches at this time")

    console.print(f"Showing T1 batches for GI {ref_gi} for aggregator {account.address}")

    t1_count = taskCoordinator_contract.functions.tier1BatchCount(curr_GI).call()

    table = Table(title=f"Tier 1 Batches (GI: {curr_GI}) for aggregator {account.address}")
    table.add_column("Batch ID", justify="right", style="cyan")
    table.add_column("Model Indexes", style="green")
    table.add_column("Finalized", style="yellow")
    table.add_column("Final CID", style="white")

    if detailed:
        table.add_column("Submitted CID", style="green")

    found_batches = False
    for i in range(t1_count):
        bid, validators, model_idxs, finalized, cid = taskCoordinator_contract.functions.getTier1Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:

                cid_str = get_cid_from_bytes32(cid.hex()) if cid and any(cid) else ""
                if not detailed:
                    table.add_row(str(bid), ", ".join(map(str, model_idxs)), str(finalized), cid_str)

                if detailed:
                    submission_cid = taskCoordinator_contract.functions.t1SubmissionCID(curr_GI, bid, validator).call()
                    submission_cid_str = get_cid_from_bytes32(submission_cid.hex()) if submission_cid and any(submission_cid) else ""
                    table.add_row(str(bid), ", ".join(map(str, model_idxs)), str(finalized), cid_str, submission_cid_str)
                found_batches = True

    if found_batches:
        console.print(table)
    else:
        console.print(f"[yellow]No T1 batches found for aggregator {account.address}[/yellow]")

@app.command("show-t2-batches", help="Show T2 batches")
def show_t2_batches(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract, True, False, True)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI,GIstate, "T1nT2Bcreated", "Can not show T2 batches at this time")

    # Assuming 1 T2 batch for now as per reference code
    t2_count = 1 

    table = Table(title=f"Tier 2 Batches (GI: {curr_GI}) for aggregator {account.address}")
    table.add_column("Batch ID", justify="right", style="cyan")
    table.add_column("Finalized", style="yellow")
    table.add_column("Final CID", style="white")

    if detailed:
        table.add_column("Submitted CID", style="green")

    found_batches = False
    for i in range(t2_count):
        bid, validators, finalized, cid = taskCoordinator_contract.functions.getTier2Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:
                cid_str = get_cid_from_bytes32(cid.hex()) if cid and any(cid) else ""
                if not detailed:
                    table.add_row(str(bid), str(finalized), cid_str)
                else:
                    submission_cid = taskCoordinator_contract.functions.t2SubmissionCID(curr_GI, bid, validator).call()
                    submission_cid_str = get_cid_from_bytes32(submission_cid.hex()) if submission_cid and any(submission_cid) else ""
                    table.add_row(str(bid), str(finalized), cid_str, submission_cid_str)
                found_batches = True

    if found_batches:
        console.print(table)
    else:
        console.print(f"[yellow]No T2 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")

@app.command("aggregate-t1", help="Aggregate T1 batches")
def aggregate_t1(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit aggregation to task coordinator"),
    batch_id: int = typer.Option(None, "--batch", help="Batch ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    taskAuditor_contract = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T1AggregationStarted", "Can not aggregate T1 batches at this time")

    t1_batches_count = taskCoordinator_contract.functions.tier1BatchCount(curr_GI).call() 

    genesis_model_ipfs_hash_raw = taskCoordinator_contract.functions.genesisModelIpfsHash().call()
    genesis_model_ipfs_hash = get_cid_from_bytes32(genesis_model_ipfs_hash_raw.hex())

    found_batch = False

    if batch_id is not None and batch_id >= t1_batches_count:
        console.print(f"[red]Error:[/red] invalid T1 batch ID {batch_id} does not exist")
        raise typer.Exit(1)

    for i in range(t1_batches_count):

        if batch_id is not None:
            if i != batch_id:
                continue
        
        (bid, val, idxs, fin, cid) = taskCoordinator_contract.functions.getTier1Batch(curr_GI, i).call()
        
        if account.address not in val:
            continue

        found_batch = True   

        model_cids = []
        for j in range(len(idxs)):
            (client, modelCID, submittedAt, eligible, evaluated, approved, finalAvgScore) = taskAuditor_contract.functions.lmSubmissions(curr_GI, idxs[j]).call()
            model_cids.append(get_cid_from_bytes32(modelCID.hex()))

        console.print(f"Aggregating Assigned T1 batch {bid} for aggregator {account.address} with model cids {model_cids} and genesis model cid {genesis_model_ipfs_hash}")

        model_base_dir = Path(CACHE_DIR) / effective_network / f"model_{model_id}"
        manifest = get_manifest_key(effective_network, "get_aggregated_cid_t1", model_id)
        aggregator_service_path = model_base_dir / Path(manifest["path"])
        model_service_path = model_base_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])

        if manifest["type"] == "custom":
            ctx.obj.ensure_file_exists(aggregator_service_path, manifest["ipfs"], "aggregator service")
            ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network,"ModelArchitecture", model_id)["ipfs"], "model service")

            fn = ctx.obj.load_custom_fn(aggregator_service_path, "get_aggregated_cid_t1")
            
            aggregated_cid = fn(curr_GI, account.address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir)
        else:
            aggregated_cid = get_aggregated_cid(curr_GI, account.address, model_cids, genesis_model_ipfs_hash)

        console.print(f"Aggregated CID for T1 batch {bid} is {aggregated_cid}")

        if submit:

            console.print(f"Submitting T1 aggregation CID for T1 batch {bid} with aggregated CID {aggregated_cid}")
            try:
                aggregated_cid_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(aggregated_cid))
                tx = taskCoordinator_contract.functions.submitT1Aggregation(curr_GI, bid, aggregated_cid_bytes32).build_transaction({
                    "from": account.address,
                    "gas": 3000000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": w3.eth.chain_id,
                    "nonce": w3.eth.get_transaction_count(account.address),
                })
                signed_tx = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    console.print(f"[bold green]✓ Aggregation CID submitted.[/bold green]")
                else:
                    console.print(f"[bold red]✗ Could not submit aggregation CID.[/bold red]")
            except Exception as e:
                console.print(f"[bold red]✗ Could not submit aggregation CID. Error: {e}[/bold red]")
                raise typer.Exit(1)

    if not found_batch:
        console.print(f"[yellow]No T1 batches found for aggregator {account.address}[/yellow]")

    
@app.command("aggregate-t2", help="Aggregate T2 batches")
def aggregate_t2(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit aggregation to task coordinator"),
    batch_id: int = typer.Option(None, "--batch", help="Batch ID"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)
    
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)
    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "T2AggregationStarted", "Can not aggregate T2 batches at this time")
    
    t2_batches_count = 1

    genesis_model_ipfs_hash_raw = taskCoordinator_contract.functions.genesisModelIpfsHash().call()
    genesis_model_ipfs_hash = get_cid_from_bytes32(genesis_model_ipfs_hash_raw.hex())
    
    found_batch = False
    
    if batch_id and batch_id >= t2_batches_count:
        console.print(f"[red]Error:[/red] invalid T2 batch ID {batch_id} does not exist")
        raise typer.Exit(1)
    
    for i in range(t2_batches_count):
        if batch_id:
            if i != batch_id:
                continue
        
        (bid, aggregators, finalized, cid) = taskCoordinator_contract.functions.getTier2Batch(curr_GI, i).call()

        if account.address not in aggregators:
            continue
        
        console.print(f"Aggregating T2 batch {bid} for aggregator {account.address}")
        
        found_batch = True      

        model_cids = []

        t1_batches_count = taskCoordinator_contract.functions.tier1BatchCount(curr_GI).call()

        for j in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = taskCoordinator_contract.functions.getTier1Batch(curr_GI, j).call()
            model_cids.append(get_cid_from_bytes32(cid.hex()))

        console.print(f"Aggregating T2 batch {bid} for aggregator {account.address} with T1 final cids {model_cids} and genesis model cid {genesis_model_ipfs_hash}")

        model_base_dir = Path(CACHE_DIR) / effective_network / f"model_{model_id}"
        manifest = get_manifest_key(effective_network, "get_aggregated_cid_t2", model_id)
        aggregator_service_path = model_base_dir / Path(manifest["path"])
        model_service_path = model_base_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])
  
        if manifest["type"] == "custom":

            ctx.obj.ensure_file_exists(aggregator_service_path, manifest["ipfs"], "aggregator service")
            ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network,"ModelArchitecture", model_id)["ipfs"], "model service")
            
            fn = ctx.obj.load_custom_fn(aggregator_service_path, "get_aggregated_cid_t2")
            
            aggregated_cid = fn(curr_GI, account.address, model_cids, genesis_model_ipfs_hash, bid, model_base_dir)
        else:
            aggregated_cid = get_aggregated_cid(curr_GI, account.address, model_cids, genesis_model_ipfs_hash)

        if submit:
            console.print(f"Submitting T2 aggregation CID for T2 batch {bid}  with aggregated CID {aggregated_cid}")
            try:
                aggregated_cid_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(aggregated_cid))
                tx = taskCoordinator_contract.functions.submitT2Aggregation(curr_GI, i, aggregated_cid_bytes32).build_transaction({
                    "from": account.address,
                    "gas": 3000000,
                    "gasPrice": w3.eth.gas_price,
                    "chainId": w3.eth.chain_id,
                    "nonce": w3.eth.get_transaction_count(account.address),
                })

                signed_tx = account.sign_transaction(tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)

                receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

                if receipt.status == 1:
                    console.print(f"[bold green]✓ Aggregation CID submitted.[/bold green]")
                else:
                    console.print(f"[bold red]✗ Could not submit aggregation CID.[/bold red]")
            except Exception as e:
                console.print(f"[bold red]✗ Could not submit aggregation CID. Error: {e}[/bold red]")
                raise typer.Exit(1)

    if not found_batch:
        console.print(f"[yellow]No T2 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")
