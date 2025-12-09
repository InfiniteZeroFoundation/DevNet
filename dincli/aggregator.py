import typer
from rich import print
from rich.table import Table
from typing import Optional
from rich.console import Console
from pathlib import Path
from dotenv import dotenv_values, set_key, get_key, unset_key
from dincli.utils import resolve_network, get_w3, load_account, load_din_info, load_usdt_config, GIstateToStr, GIstatestrToIndex
from dincli.contract_utils import get_contract_instance
from dincli.services.aggregator import get_aggregated_cid

app = typer.Typer(help="Commands for Aggregators in DIN.")

console = Console()

MIN_STAKE = 1000000*10**18

dintoken_app = typer.Typer(help="Commands for DIN Token in DIN.")
app.add_typer(dintoken_app, name="dintoken")


@dintoken_app.command(help="Buy DINTokens where amouunt is ETh to exchange for DINTokens")
def buy(amount: int, network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),):

    effective_network = resolve_network(network)
    
    w3 = get_w3(effective_network)

    artifact_path = Path(__file__).parent / "abis" / "DinToken.json"
    
    din_addresses = load_din_info()
    dintoken_address = din_addresses[effective_network]["token"] 
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 

    # Load contract instance
    DINToken_contract = get_contract_instance(artifact_path, effective_network, dintoken_address)


    artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    
    DinCoordinator_contract = get_contract_instance(artifact_path, effective_network, dincoordinator_address)
    
    # Load account
    account = load_account()

    print("Aggregator address: ", account.address)
    print("Aggregator ETH balance: ", w3.eth.get_balance(account.address))
    print("DINToken address: ", dintoken_address)
    print("DINCoordinator address: ", dincoordinator_address)
    print("Aggregator DINToken balance: ", DINToken_contract.functions.balanceOf(account.address).call())

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
    print("Aggregator DINToken balance: ", DINToken_contract.functions.balanceOf(account.address).call())
    
    
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
    
    console.print("Aggregator address: ", account.address)
    console.print("Aggregator ETH balance: ", w3.eth.get_balance(account.address))
    console.print("DINToken address: ", dintoken_address)
    console.print("Aggregator DINToken balance: ", validator_Din_token_balance)
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
                
        tx_stake_receipt = w3.eth.wait_for_transaction_receipt(tx_hash_stake) 

        if tx_stake_receipt.status == 1:
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
    

    console.print("Aggregator address: ", account.address)
    console.print("DINStake address: ", dinstake_address)
    console.print("Aggregator DIN token stake: ", DinStake_contract.functions.getStake(account.address).call())


@app.command(help="Register as aggregator")
def register(network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
taskCoordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address")):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    din_addresses = load_din_info()
    dincoordinator_address = din_addresses[effective_network]["coordinator"] 
    dinstake_address = din_addresses[effective_network]["stake"] 

    env_config = dotenv_values(".env")

    if taskCoordinator is None:
        taskCoordinator = env_config.get("DINTaskCoordinator_Contract_Address")

    taskCoordinator_artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    taskCoordinator_contract = get_contract_instance(taskCoordinator_artifact_path, effective_network, taskCoordinator)
    
    coordinator_artifact_path = Path(__file__).parent / "abis" / "DinCoordinator.json"
    DinCoordinator_contract = get_contract_instance(coordinator_artifact_path, effective_network, dincoordinator_address)

    stake_artifact_path = Path(__file__).parent / "abis" / "DinValidatorStake.json"
    DinStake_contract = get_contract_instance(stake_artifact_path, effective_network, dinstake_address)
    
    account = load_account()

    curr_GI = taskCoordinator_contract.functions.GI().call()
    
    curr_GIstate = taskCoordinator_contract.functions.GIstate().call()

    if GIstateToStr(curr_GIstate) != "DINvalidatorRegistrationStarted":
        console.print(f"[bold red]✗ Can not register validators at this time. Current state: {GIstateToStr(curr_GIstate)} for GI {curr_GI} where taskCoordinator is {taskCoordinator}[/bold red]")
        return

    registered_validators = taskCoordinator_contract.functions.getDINtaskValidators(curr_GI).call()
    
    
    console.print("Aggregator address: ", account.address)
    console.print("DIN task Coordinator address: ", taskCoordinator)
    console.print("Current GI: ", curr_GI)
    console.print("Current GI state: ", GIstateToStr(curr_GIstate))
    console.print("Registered validators: ", registered_validators)
    if account.address in registered_validators:
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
    
            tx = taskCoordinator_contract.functions.registerDINvalidator(curr_GI).build_transaction({
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
            else:
                console.print(f"[bold red]✗ Could not register aggregator.[/bold red]")
    
  
   
@app.command(help="Show T1 batches")    
def show_t1_batches(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    console.print("Aggregator address: ", account.address)

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1nT2Bcreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. Batches do not exist yet.")
        raise typer.Exit(1)

    t1_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()

    table = Table(title=f"Tier 1 Batches (GI: {curr_GI}) for aggregator {account.address}")
    table.add_column("Batch ID", justify="right", style="cyan")
    table.add_column("Model Indexes", style="green")
    table.add_column("Finalized", style="yellow")
    table.add_column("Final CID", style="white")

    if detailed:
        table.add_column("Submitted CID", style="green")

    found_batches = False
    for i in range(t1_count):
        bid, validators, model_idxs, finalized, cid = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:

                if not detailed:
                    table.add_row(str(bid), ", ".join(map(str, model_idxs)), str(finalized), cid or "")
                
                if detailed:
                    submission_cid = deployed_DINTaskCoordinatorContract.functions.t1SubmissionCID(curr_GI, bid, validator).call()
                    table.add_row(str(bid), ", ".join(map(str, model_idxs)), str(finalized), cid or "", submission_cid)
                found_batches = True

    if found_batches:
        console.print(table)
    else:
        console.print(f"[yellow]No T1 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")

@app.command(help="Show T2 batches")
def show_t2_batches(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    detailed: bool = typer.Option(False, "--detailed", help="Show detailed information"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    console.print("Aggregator address: ", account.address)

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1nT2Bcreated"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. Batches do not exist yet.")
        raise typer.Exit(1)

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
        bid, validators, finalized, cid = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:
                if not detailed:
                    table.add_row(str(bid), str(finalized), cid or "")
                else:
                    submission_cid = deployed_DINTaskCoordinatorContract.functions.t2SubmissionCID(curr_GI, bid, validator).call()
                    table.add_row(str(bid), str(finalized), submission_cid or "", cid or "")
                found_batches = True

    if found_batches:
        console.print(table)
    else:
        console.print(f"[yellow]No T2 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")

@app.command(help="Aggregate T1 batches")
def aggregate_t1(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="Task auditor address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit aggregation to task coordinator"),
    batch_id: int = typer.Option(None, "--batch", help="Batch ID"),
):
    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    console.print("Aggregator address: ", account.address)

    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)

    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()

    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)

    if GIstate < GIstatestrToIndex("T1AggregationStarted"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. Batches do not exist yet.")
        raise typer.Exit(1)


    t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call() 

    genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()

    found_batch = False

    if batch_id and batch_id >= t1_batches_count:
        console.print(f"[red]Error:[/red] invalid T1 batch ID {batch_id} does not exist")
        raise typer.Exit(1)

    for i in range(t1_batches_count):

        if batch_id:
            if i != batch_id:
                continue
            console.print(f"Aggregating T1 batch {batch_id} found... on task coordinator {task_coordinator}")
        
        (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, i).call()
        
        if account.address not in val:
            continue
            console.print(f"Aggregating T1 batch {bid} for aggregator {account.address} found... on task coordinator {task_coordinator}")
        
        found_batch = True       

        model_cids = []
        for j in range(len(idxs)):
            (client, modelCID, submittedAt, eligible,evaluated, approved, finalAvgScore) = deployed_DINTaskAuditorContract.functions.lmSubmissions(curr_GI, idxs[j]).call()
            model_cids.append(modelCID)

        aggregated_cid = get_aggregated_cid(curr_GI, account.address, model_cids, genesis_model_ipfs_hash)

        if submit:

            console.print(f"Submitting T1 aggregation CID for T1 batch {bid} ... on task coordinator {task_coordinator} with aggregated CID {aggregated_cid}")
            tx = deployed_DINTaskCoordinatorContract.functions.submitT1Aggregation(curr_GI, bid, aggregated_cid).build_transaction({
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

    if not found_batch:
        console.print(f"[yellow]No T1 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")

    
@app.command(help="Aggregate T2 batches")
def aggregate_t2(
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    task_coordinator: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    task_auditor: str = typer.Option(None, "--taskAuditor", help="Task auditor address"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit aggregation to task coordinator"),
    batch_id: int = typer.Option(None, "--batch", help="Batch ID"),
):

    effective_network = resolve_network(network)
    w3 = get_w3(effective_network)
    account = load_account()
    console.print("Aggregator address: ", account.address)
    
    if not task_coordinator:
        task_coordinator = get_key(".env", "DINTaskCoordinator_Contract_Address")
        
    artifact_path = Path(__file__).parent / "abis" / "DINTaskCoordinator.json"
    deployed_DINTaskCoordinatorContract = get_contract_instance(str(artifact_path), effective_network, task_coordinator)
    
    if not task_auditor:
        task_auditor = get_key(".env", "DINTaskAuditor_Contract_Address")
    
    artifact_path = Path(__file__).parent / "abis" / "DINTaskAuditor.json"
    deployed_DINTaskAuditorContract = get_contract_instance(str(artifact_path), effective_network, task_auditor)
    
    curr_GI = deployed_DINTaskCoordinatorContract.functions.GI().call()
    GIstate = deployed_DINTaskCoordinatorContract.functions.GIstate().call()
    
    if gi:
        if curr_GI != gi:
            console.print(f"[red]Error:[/red] invalid global iteration {gi} does not match current GI {curr_GI}")
            raise typer.Exit(1)
    
    if GIstate < GIstatestrToIndex("T2AggregationStarted"):
        console.print(f"[red]Error:[/red] GI state is {GIstateToStr(GIstate)}. T2 aggregation has not started yet.")
        raise typer.Exit(1)
    
    t2_batches_count = 1

    genesis_model_ipfs_hash = deployed_DINTaskCoordinatorContract.functions.genesisModelIpfsHash().call()
    
    found_batch = False
    
    if batch_id and batch_id >= t2_batches_count:
        console.print(f"[red]Error:[/red] invalid T2 batch ID {batch_id} does not exist")
        raise typer.Exit(1)
    
    for i in range(t2_batches_count):
        if batch_id:
            if i != batch_id:
                continue
            console.print(f"Aggregating T2 batch {batch_id} found... on task coordinator {task_coordinator}")
        
        (bid, validators, finalized, cid) = deployed_DINTaskCoordinatorContract.functions.getTier2Batch(curr_GI, i).call()

        if account.address not in validators:
            continue
            console.print(f"Aggregating T2 batch {bid} for aggregator {account.address} found... on task coordinator {task_coordinator}")
        
        found_batch = True      

        model_cids = []

        t1_batches_count = deployed_DINTaskCoordinatorContract.functions.tier1BatchCount(curr_GI).call()

        for j in range(t1_batches_count):
            (bid, val, idxs, fin, cid) = deployed_DINTaskCoordinatorContract.functions.getTier1Batch(curr_GI, j).call()
            model_cids.append(cid)

        aggregated_cid = get_aggregated_cid(curr_GI, account.address, model_cids, genesis_model_ipfs_hash)

        if submit:
            console.print(f"Submitting T2 aggregation CID for T2 batch {i} ... on task coordinator {task_coordinator} with aggregated CID {aggregated_cid}")
            tx = deployed_DINTaskCoordinatorContract.functions.submitT2Aggregation(curr_GI, i, aggregated_cid).build_transaction({
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

    if not found_batch:
        console.print(f"[yellow]No T2 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")

            
        





        
     
                
            

    