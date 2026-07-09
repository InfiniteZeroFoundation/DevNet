import os
from pathlib import Path
import time

import typer
import json
from web3 import Web3

from dincli.cli.utils import (build_and_send_tx, get_env_key, 
                                get_manifest,
                               get_manifest_key,
                               require_custom_manifest_service,
                               resolve_task_coordinator_address, 
                               set_env_key, _confirm_or_exit)
from dincli.services.cid_utils import get_bytes32_from_cid

#delete-this-for-production
from dincli.services.ipfs import retrieve_from_ipfs

model_app = typer.Typer(help="Model-level commands")


def _manifest_requires_genesis_test_dataset_scoring(manifest_data: dict) -> bool:
    gm_scoring_policy = manifest_data.get("gm_scoring_policy")
    if not isinstance(gm_scoring_policy, dict):
        return False

    evaluation = gm_scoring_policy.get("evaluation")
    if not isinstance(evaluation, dict):
        return False

    if "requires_test_dataset" in evaluation:
        return bool(evaluation["requires_test_dataset"])

    dataset_mode = str(evaluation.get("dataset_mode", "")).strip().lower()
    return bool(dataset_mode) and dataset_mode not in (
        "none",
        "disabled",
        "not_required",
        "no_test_dataset",
    )


@model_app.command("create-genesis-model")
def create_genesis_model(
    ctx: typer.Context,
    help: bool = typer.Option(False, "--help","-h", help="Show help"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )

    if help:
        console.print("[bold green]Usage:[/bold green]")
        console.print("  dincli model-owner model create-genesis --network <network>")
        console.print("\ndincli will use custom getGenesisModelIpfs() from")
        console.print(f"{Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'services' / 'modelowner.py'}")
        console.print(f"The genesis model hash will be set in {os.getcwd()}/.env under {effective_network.upper() + '_' + task_coordinator_address}_GENESIS_MODEL_IPFS_HASH")
        raise typer.Exit(0)

    task_dir = Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address

    _confirm_or_exit(
        "Have you created task directory using: dincli model-owner task create-task-dir ?",
        "Please create the task directory first using: dincli model-owner task create-task-dir",
        console,
    )

    _confirm_or_exit(
        "Have you cached all artifacts using: dincli model-owner task cache-default-artifacts ?",
        "Please cache all artifacts using: dincli model-owner task cache-default-artifacts",
        console,
    )

    _confirm_or_exit(
        "Have you edited all the artifacts as per your task specifications ?",
        "Please edit/modify all artifacts as per your task specifications.",
        console,
    )

    _confirm_or_exit(
        "Have you updated the manifest with the new artifact CIDs ?",
        "Please update the manifest with the new artifact CIDs.",
        console,
    )

    if not task_dir.exists():
        console.print(f"[bold red]Task directory not found at {task_dir}[/bold red]")
        console.print(f"[bold yellow]Please create the task directory first using: dincli model-owner task create-task-dir[/bold yellow]")
        raise typer.Exit(1)

    target_manifest = os.path.join(task_dir, "manifest.json")
    
    if not os.path.exists(target_manifest):
        console.print(f"[bold red]Manifest not found at {target_manifest}[/bold red]")
        console.print(f"[bold yellow]Please cache the artifacts and manifest using: dincli model-owner task cache-default-artifacts[/bold yellow]")
        raise typer.Exit(1)

    manifest = get_manifest_key(effective_network, "getGenesisModelIpfs", None, task_coordinator_address)
    service_path = task_dir / Path(manifest["path"])
    model_service_path = task_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"])

    require_custom_manifest_service(manifest, "getGenesisModelIpfs")
    ctx.obj.ensure_file_exists(service_path, manifest["ipfs"], "model owner service")
    ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["ipfs"], "model architecture service")

    _confirm_or_exit(
        f"Have you edited/modified the modelowner service at {service_path} according to your task requirements?",
        f"Please edit/modify the modelowner service at {service_path} according to your task requirements.",
        console,
    )
    _confirm_or_exit(
        f"Have you edited/modified the modelarchitecture service at {model_service_path} according to your task requirements?",
        f"Please edit/modify the modelarchitecture service at {model_service_path}.",
        console,
    )
    console.print("[bold green]Creating genesis model... [/bold green]")
    fn = ctx.obj.load_custom_fn(
        service_path,
        "getGenesisModelIpfs"
    )
    model_hash = fn(task_dir)
    
    console.print(f"[bold green]Genesis model created successfully![/bold green]")
    console.print(f"[cyan]Model hash:[/cyan] {model_hash}")

    set_env_key(effective_network.upper() + "_" + task_coordinator_address + "_GENESIS_MODEL_IPFS_HASH", model_hash)

    console.print(f"[bold green]Genesis model hash set in {os.getcwd()}/.env as {effective_network.upper()}_{task_coordinator_address}_GENESIS_MODEL_IPFS_HASH successfully![/bold green]")
    
    return

#delete-this-for-production
@model_app.command("add-default-test-data")
def add_default_test_data(ctx: typer.Context,     task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"), model_id: int = typer.Option(None, "--model-id", help="Model ID"), default_test_data: bool = typer.Option(False, "--default-test-data", help="use default test data")):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )

    console.print("[bold green]Getting default test dataset ...[/bold green]")
    

    if model_id is not None:
        task_dir = ctx.obj.get_model_base_dir(model_id)
    elif task_coordinator_address is not None:
        task_dir = Path.cwd() / 'tasks' / effective_network.lower()/ task_coordinator_address
    test_dataset_path = task_dir.joinpath("dataset","test","test_dataset.pt")
    if default_test_data:
        default_test_dataset_ipfs_hash = "bafybeigjtcu2nzsffoy5pjmui25bnc43yduzn6aopi4wnrbtxfleqmw46y"
        console.print(f"[bold yellow] Using default test dataset with IPFS CID {default_test_dataset_ipfs_hash} [/bold yellow]")
        retrieve_from_ipfs(default_test_dataset_ipfs_hash, test_dataset_path)


@model_app.command("submit-genesis-model")
def submit_genesis_model(
    ctx: typer.Context,
    ipfs_hash: str = typer.Option(None, "--ipfs-hash", help="IPFS hash of the model"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    score: int = typer.Option(None, "--score", help="Score of the model"),
    help: bool = typer.Option(False, "--help","-h", help="Show help"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )
    
    if help:
        console.print("[bold green]Usage:[/bold green]")
        console.print("  dincli model-owner model submit-genesis-model --network <network>")
        console.print("\ndincli will use custom getscoreforGM() from")
        console.print(f"{Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'services' / 'modelowner.py'}")
        console.print("\n [yellow]Warning:[/yellow] if the manifest requires dataset-based scoring, the test dataset must be available at: ")
        console.print(f"  {Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'dataset' / 'test' / 'test_dataset.pt'}")
        console.print("\n [yellow]Warning:[/yellow] the genesis model must be available at: ")
        console.print(f"  {Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'models' / 'genesis_model.pth'}")
        console.print(f"\n [yellow]Warning:[/yellow] If --ipfs-hash is not specified, the genesis model IPFS hash will be read from {os.getcwd()}/.env under {effective_network.upper() + '_' + task_coordinator_address + '_GENESIS_MODEL_IPFS_HASH'}")
        raise typer.Exit(0)

    
    _confirm_or_exit(
        f"Have you generated the genesis model using dincli model-owner model create-genesis-model?",
        f"Please generate the genesis model using dincli model-owner model create-genesis-model.",
        console,
    )

    if not ipfs_hash:
        ipfs_hash = get_env_key(effective_network.upper() + "_" + task_coordinator_address + "_GENESIS_MODEL_IPFS_HASH")

        if not ipfs_hash:
            console.print("[bold red]Genesis model IPFS hash not found![/bold red]")
            console.print(f"[yellow]Please set {effective_network.upper() + '_' + task_coordinator_address + '_GENESIS_MODEL_IPFS_HASH'} in {os.getcwd()}/.env[/yellow]")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Submitting genesis model to DIN Task Coordinator![/bold green]")
    console.print(f"[cyan]Genesis model IPFS hash:[/cyan] {ipfs_hash}")

    accuracy = None
    if score is not None:
        accuracy = score
    else:

        task_dir = Path.cwd() / 'tasks' / effective_network.lower()/ task_coordinator_address

        manifest_data = get_manifest(
            effective_network,
            task_coordinator_address=task_coordinator_address,
        )
        requires_test_dataset_scoring = _manifest_requires_genesis_test_dataset_scoring(manifest_data)
        if not requires_test_dataset_scoring:
            console.print("[yellow]Manifest does not require genesis model scoring with a test dataset. Skipping tier 2 score submission.[/yellow]")
        else:
            manifest = manifest_data["getscoreforGM"]
            service_path = task_dir / Path(manifest["path"])
            model_service_path = task_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"])

            require_custom_manifest_service(manifest, "getscoreforGM")
            ctx.obj.ensure_file_exists(service_path, manifest["ipfs"], "model owner service")
            ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["ipfs"], "model architecture service")

            fn = ctx.obj.load_custom_fn(service_path, "getscoreforGM")

            test_dataset_path = task_dir.joinpath("dataset", "test", "test_dataset.pt")
            _confirm_or_exit(
                f"Manifest requires genesis model scoring with a test dataset. Have you added the test dataset at {test_dataset_path}?",
                f"Please add the test dataset at {test_dataset_path} before submitting the genesis model.",
                console,
            )
            if not test_dataset_path.exists():
                console.print(f"[bold red] X Test dataset not found at {test_dataset_path} [/bold red]")
                console.print("[yellow]Please add the test dataset at the required path and rerun submit-genesis-model.[/yellow]")
                raise typer.Exit(1)
            genesis_model_path = task_dir.joinpath("models","genesis_model.pth")
            if not genesis_model_path.exists():
                console.print(f"[bold red] X Genesis model not found at {genesis_model_path} [/bold red]")
                raise typer.Exit(1)

            try:
                accuracy = fn(0, ipfs_hash, task_dir)
            except Exception as e:
                console.print(f"[bold red] X Accuracy calculation failed: {e} [/bold red]")
                raise typer.Exit(1)
            
            if accuracy is None:
                console.print(f"[bold red] X Accuracy is None[/bold red]")
                raise typer.Exit(1)

    
    deployed_DINTaskCoordinatorContract = ctx.obj.get_deployed_din_task_coordinator_contract(True, None, task_coordinator_address)

    genesis_ipfs_hash_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(ipfs_hash))

    _confirm_or_exit("\n Do you want to submit this genesis model to the blockchain? \n ", "You chose not to submit the genesis model to the blockchain.", console)
    
    tx_receipt = build_and_send_tx(
        ctx,
        deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(genesis_ipfs_hash_bytes32),
        "Submitting genesis model",
        "Genesis model submitted!",
        "Failed to submit genesis model!"
    )

    time.sleep(10)
    
    if accuracy is None:
        return

    console.print("Genesis model accuracy:", accuracy)
    
    build_and_send_tx(
        ctx,
        deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)),
        "Submitting genesis model tier 2 score",
        "Genesis model tier 2 score set!",
        "Failed to submit genesis model tier 2 score!"
    )


@model_app.command("validate-update-manifest")
def validate_update_manifest(
    ctx: typer.Context,
    manifest_path: str = typer.Option(None, "--manifest-path", "-mpath", help="Path to the manifest file"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
   ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )

    task_dir = Path.cwd() / 'tasks' / effective_network.lower()/ task_coordinator_address

    manifestpath = task_dir / "manifest.json"
    console.print(f"[bold green] Updating Manifest file at  {manifestpath} ...[/bold green]")

    manifest_data = get_manifest(effective_network, task_coordinator_address=task_coordinator_address)

    manifest_DINTaskCoordinator_Contract = manifest_data["DINTaskCoordinator_Contract"]

    if task_coordinator_address!=manifest_DINTaskCoordinator_Contract:
        console.print(f"[bold red] X Task coordinator address in manifest does not match the task coordinator address in .env! [/bold red]")
        console.print(f"[bold red] Task coordinator address in manifest: {manifest_DINTaskCoordinator_Contract} [/bold red]")
        console.print(f"[bold red] Task coordinator address in .env: {task_coordinator_address} [/bold red]")
        if typer.confirm("Should we update the DINTaskCoordinator_Contract in manifest to match the task coordinator address in .env?:"):
            console.print(f"[bold green] Updating the DINTaskCoordinator_Contract in manifest to match the task coordinator address in .env [/bold green]")
            manifest_data["DINTaskCoordinator_Contract"] = task_coordinator_address
        else:
            console.print("[bold red] X Not updating the DINTaskCoordinator_Contract in manifest. [/bold red]")
    
    manifest_DINTaskAuditor_Contract = manifest_data["DINTaskAuditor_Contract"]
    key = effective_network.upper() + "_" + task_coordinator_address + "_DINTaskAuditor_Contract_Address"
    task_auditor = get_env_key(key)

    if task_auditor!=manifest_DINTaskAuditor_Contract:
        console.print(f"[bold red] X Task auditor address in manifest does not match the task auditor address in .env! [/bold red]")
        console.print(f"[bold red] Task auditor address in manifest: {manifest_DINTaskAuditor_Contract} [/bold red]")
        console.print(f"[bold red] Task auditor address in .env: {task_auditor} [/bold red]")
        if typer.confirm("Should we update the DINTaskAuditor_Contract in manifest to match the task auditor address in .env?:"):
            console.print(f"[bold green] Updating the DINTaskAuditor_Contract in manifest to match the task auditor address in .env [/bold green]")
            manifest_data["DINTaskAuditor_Contract"] = task_auditor
        else:
            console.print("[bold red] X Not updating the DINTaskAuditor_Contract in manifest. [/bold red]")

    manifest_genesis_model_cid = manifest_data["Genesis_Model_CID"]
    genesis_model_ipfs_hash = get_env_key(effective_network.upper() + "_" + task_coordinator_address + "_GENESIS_MODEL_IPFS_HASH")

    if manifest_genesis_model_cid!=genesis_model_ipfs_hash:
        console.print(f"[bold red] X Genesis model CID in manifest does not match the genesis model CID in .env! [/bold red]")
        console.print(f"[bold red] Genesis model CID in manifest: {manifest_genesis_model_cid} [/bold red]")
        console.print(f"[bold red] Genesis model CID in .env: {genesis_model_ipfs_hash} [/bold red]")
        if typer.confirm("Should we update the Genesis model CID in manifest to match the genesis model CID in .env?:"):
            console.print(f"[bold green] Updating the Genesis model CID in manifest to match the genesis model CID in .env [/bold green]")
            manifest_data["Genesis_Model_CID"] = genesis_model_ipfs_hash
        else:
            console.print("[bold red] X Not updating the Genesis model CID in manifest. [/bold red]")

    with open(manifestpath, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=4)
    
    console.print(f"[bold green] Manifest at {manifestpath} updated successfully! [/bold green]")
    console.print(f"[bold yellow] Make sure to throughly read/modify all the parameters/CID values in the manifest file before registering your task/model onchain. [/bold yellow]")


    
        
        

    

    
    


    



        

    


    
    