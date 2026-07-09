from pathlib import Path
import time
from typing import Optional
import typer
from rich.table import Table
from web3 import Web3
from dincli.cli.dintoken import buy_dintokens, read_dintoken_stake, stake_dintokens
from dincli.cli.utils import (CACHE_DIR, MIN_STAKE, build_and_send_tx,
                               get_manifest_key, require_custom_manifest_service)
from dincli.cli.worker import (
    ensure_worker_image,
    ensure_worker_packages_installed,
    get_worker_packages_dir,
    get_worker_requirements_path,
    read_worker_result,
    run_worker_container,
    write_worker_job,
)
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32
from dincli.services.ipfs import upload_to_ipfs

app = typer.Typer(help="Commands for Aggregators in DIN.")

dintoken_app = typer.Typer(help="Commands for DIN Token in DIN.")
app.add_typer(dintoken_app, name="dintoken")


@dintoken_app.command(help="Buy DINTokens where amount is ETH to exchange for DINTokens")
def buy(
    ctx: typer.Context,
    amount: float = typer.Argument(..., help="Amount of ETH to exchange for DINTokens"),
):
    buy_dintokens(ctx, amount, name= "Aggregator")


@dintoken_app.command(help="Stake DINTokens")
def stake(
    ctx: typer.Context,
    amount: int = typer.Argument(..., help="Amount of DINTokens to stake"),
):
    stake_dintokens(ctx, amount, name= "Aggregator")


@dintoken_app.command("read-stake", help="Check stake")
def read_stake(ctx: typer.Context):
    read_dintoken_stake(ctx, name= "Aggregator")


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
                build_and_send_tx(
                    ctx,
                    taskCoordinator_contract.functions.registerDINaggregator(curr_GI),
                    "Registering aggregator",
                    "Aggregator registered.",
                    "Could not register aggregator.",
                    exit_on_failure=False
                )
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
        time.sleep(0.2)
        bid, validators, model_idxs, finalized, cid = taskCoordinator_contract.functions.getTier1Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:

                cid_str = get_cid_from_bytes32(cid.hex()) if cid and any(cid) else ""
                if not detailed:
                    table.add_row(str(bid), ", ".join(map(str, model_idxs)), str(finalized), cid_str)

                if detailed:
                    time.sleep(0.2)
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
        time.sleep(0.2)
        bid, validators, finalized, cid = taskCoordinator_contract.functions.getTier2Batch(curr_GI, i).call()
        for validator in validators:
            if validator == account.address:
                cid_str = get_cid_from_bytes32(cid.hex()) if cid and any(cid) else ""
                if not detailed:
                    table.add_row(str(bid), str(finalized), cid_str)
                else:
                    time.sleep(0.2)
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
    packages_dir: Optional[str] = typer.Option(None, "--packages-dir", help="Packages directory"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not use cached packages"),
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
            time.sleep(0.1)
            (client, modelCID, submittedAt, eligible, evaluated, approved, finalAvgScore) = taskAuditor_contract.functions.lmSubmissions(curr_GI, idxs[j]).call()
            model_cids.append(get_cid_from_bytes32(modelCID.hex()))

        console.print(f"Aggregating Assigned T1 batch {bid} for aggregator {account.address} with model cids {model_cids} and genesis model cid {genesis_model_ipfs_hash}")

        model_base_dir = ctx.obj.get_model_base_dir(model_id)
        manifest = get_manifest_key(effective_network, "get_aggregated_cid_t1", model_id)
        aggregator_service_path = model_base_dir / Path(manifest["path"])
        model_service_path = model_base_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])

        require_custom_manifest_service(manifest, "get_aggregated_cid_t1")
        ctx.obj.ensure_file_exists(aggregator_service_path, manifest["ipfs"], "aggregator service")
        ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network,"ModelArchitecture", model_id)["ipfs"], "model service")

        aggregator_requirements_cid = get_manifest_key(effective_network, "requirements.txt", model_id).get("aggregators")
        requirements_path = get_worker_requirements_path(model_base_dir, "aggregators")
        packages_dir = Path(packages_dir) if packages_dir else None
        if aggregator_requirements_cid:
            ctx.obj.ensure_file_exists(requirements_path, aggregator_requirements_cid, "aggregator requirements")
            try:
                ensure_worker_image(console)
                if not no_cache and packages_dir is None:
                    packages_dir = ensure_worker_packages_installed(
                        requirements_path,
                        get_worker_packages_dir(effective_network, model_id),
                        console,
                    )
            except RuntimeError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(1)

        # dincli fetches every IPFS-addressed input on the host into the same
        # local paths get_aggregated_cid_t1 derives internally, so no network
        # access happens inside the container.
        aggregator_models_path = model_base_dir / "aggregator" / account.address / str(curr_GI) / "T1" / str(bid) / "models"
        for model_cid in model_cids:
            ctx.obj.ensure_file_exists(aggregator_models_path / f"{model_cid}.pth", model_cid, "T1 local model submission")
        ctx.obj.ensure_file_exists(model_base_dir / "models" / "genesis_model.pth", genesis_model_ipfs_hash, "genesis model")

        jobs_dir = model_base_dir / "jobs" / "aggregators" / account.address
        job_path, output_dir = write_worker_job(
            jobs_dir,
            f"aggregator_t1_gi_{curr_GI}_batch_{bid}",
            {
                "network": effective_network,
                "model_base_dir": "/din/model",
                "manifest_path": "/din/model/manifest.json",
                "role": "aggregator",
                "service_path": manifest["path"],
                "function_name": "get_aggregated_cid_t1",
                "args": [curr_GI, account.address, model_cids, genesis_model_ipfs_hash, bid, "/din/model"],
            },
        )

        docker_result = run_worker_container(
            container_name=f"din-worker-aggregator-t1-model-{model_id}-gi-{curr_GI}-batch-{bid}",
            model_base_dir=model_base_dir,
            job_path=job_path,
            output_dir=output_dir,
            writable_subdirs=[aggregator_models_path],
            packages_dir=packages_dir,
        )

        if docker_result.stdout:
            console.print(docker_result.stdout)
        if docker_result.returncode != 0:
            if docker_result.stderr:
                console.print(docker_result.stderr)
            console.print(f"[bold red]Aggregator worker container failed for T1 batch {bid}.[/bold red]")
            continue

        worker_result = read_worker_result(output_dir)
        if worker_result.get("status") != "ok":
            console.print(f"[bold red]Aggregator worker failed:[/bold red] {worker_result.get('error')}")
            traceback = worker_result.get("traceback")
            if traceback:
                console.print(traceback)
            continue

        averaged_model_path = model_base_dir / Path(worker_result["result"]).relative_to("/din/model")
        aggregated_cid = upload_to_ipfs(averaged_model_path, f"Averaged T1 model for batch {bid}")

        console.print(f"Aggregated CID for T1 batch {bid} is {aggregated_cid}")

        if submit:
            try:
                aggregated_cid_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(aggregated_cid))
                time.sleep(2)

                build_and_send_tx(
                    ctx,
                    taskCoordinator_contract.functions.submitT1Aggregation(curr_GI, bid, aggregated_cid_bytes32),
                    f"Submitting T1 aggregation CID for T1 batch {bid} with aggregated CID {aggregated_cid}",
                    "Aggregation CID submitted.",
                    "Could not submit aggregation CID.",
                    exit_on_failure=False
                )
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
    packages_dir: Optional[str] = typer.Option(None, "--packages-dir", help="Packages directory"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not use cached packages"),
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
            time.sleep(0.1)
            (bid, val, idxs, fin, cid) = taskCoordinator_contract.functions.getTier1Batch(curr_GI, j).call()
            model_cids.append(get_cid_from_bytes32(cid.hex()))

        console.print(f"Aggregating T2 batch {bid} for aggregator {account.address} with T1 final cids {model_cids} and genesis model cid {genesis_model_ipfs_hash}")

        model_base_dir = ctx.obj.get_model_base_dir(model_id)
        manifest = get_manifest_key(effective_network, "get_aggregated_cid_t2", model_id)
        aggregator_service_path = model_base_dir / Path(manifest["path"])
        model_service_path = model_base_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", model_id)["path"])
  
        require_custom_manifest_service(manifest, "get_aggregated_cid_t2")
        ctx.obj.ensure_file_exists(aggregator_service_path, manifest["ipfs"], "aggregator service")
        ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network,"ModelArchitecture", model_id)["ipfs"], "model service")

        aggregator_requirements_cid = get_manifest_key(effective_network, "requirements.txt", model_id).get("aggregators")
        requirements_path = get_worker_requirements_path(model_base_dir, "aggregators")
        packages_dir = Path(packages_dir) if packages_dir else None
        if aggregator_requirements_cid:
            ctx.obj.ensure_file_exists(requirements_path, aggregator_requirements_cid, "aggregator requirements")
            try:
                ensure_worker_image(console)
                if not no_cache and packages_dir is None:
                    packages_dir = ensure_worker_packages_installed(
                        requirements_path,
                        get_worker_packages_dir(effective_network, model_id),
                        console,
                    )
            except RuntimeError as e:
                console.print(f"[bold red]{e}[/bold red]")
                raise typer.Exit(1)

        aggregator_models_path = model_base_dir / "aggregator" / account.address / str(curr_GI) / "T2" / str(bid) / "models"
        for model_cid in model_cids:
            ctx.obj.ensure_file_exists(aggregator_models_path / f"{model_cid}.pth", model_cid, "T1 final model")
        ctx.obj.ensure_file_exists(model_base_dir / "models" / "genesis_model.pth", genesis_model_ipfs_hash, "genesis model")

        jobs_dir = model_base_dir / "jobs" / "aggregators" / account.address
        job_path, output_dir = write_worker_job(
            jobs_dir,
            f"aggregator_t2_gi_{curr_GI}_batch_{bid}",
            {
                "network": effective_network,
                "model_base_dir": "/din/model",
                "manifest_path": "/din/model/manifest.json",
                "role": "aggregator",
                "service_path": manifest["path"],
                "function_name": "get_aggregated_cid_t2",
                "args": [curr_GI, account.address, model_cids, genesis_model_ipfs_hash, bid, "/din/model"],
            },
        )

        docker_result = run_worker_container(
            container_name=f"din-worker-aggregator-t2-model-{model_id}-gi-{curr_GI}-batch-{bid}",
            model_base_dir=model_base_dir,
            job_path=job_path,
            output_dir=output_dir,
            writable_subdirs=[aggregator_models_path],
            packages_dir=packages_dir,
        )

        if docker_result.stdout:
            console.print(docker_result.stdout)
        if docker_result.returncode != 0:
            if docker_result.stderr:
                console.print(docker_result.stderr)
            console.print(f"[bold red]Aggregator worker container failed for T2 batch {bid}.[/bold red]")
            continue

        worker_result = read_worker_result(output_dir)
        if worker_result.get("status") != "ok":
            console.print(f"[bold red]Aggregator worker failed:[/bold red] {worker_result.get('error')}")
            traceback = worker_result.get("traceback")
            if traceback:
                console.print(traceback)
            continue

        averaged_model_path = model_base_dir / Path(worker_result["result"]).relative_to("/din/model")
        aggregated_cid = upload_to_ipfs(averaged_model_path, f"Averaged T2 model for batch {bid}")

        console.print(f"Aggregated CID for T2 batch {bid} is {aggregated_cid}")

        if submit:
            try:
                aggregated_cid_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(aggregated_cid))

                build_and_send_tx(
                    ctx,
                    taskCoordinator_contract.functions.submitT2Aggregation(curr_GI, i, aggregated_cid_bytes32),
                    f"Submitting T2 aggregation CID for T2 batch {bid} with aggregated CID {aggregated_cid}",
                    "Aggregation CID submitted.",
                    "Could not submit aggregation CID.",
                    exit_on_failure=False
                )
            except Exception as e:
                console.print(f"[bold red]✗ Could not submit aggregation CID. Error: {e}[/bold red]")
                raise typer.Exit(1)

    if not found_batch:
        console.print(f"[yellow]No T2 batches found for aggregator {account.address} in GI {curr_GI}[/yellow]")
