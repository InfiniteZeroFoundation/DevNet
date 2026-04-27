import os
from pathlib import Path
import time

import typer
from web3 import Web3

from dincli.cli.utils import get_env_key, get_manifest_key, set_env_key
from dincli.services.ipfs import retrieve_from_ipfs
from dincli.services.cid_utils import get_bytes32_from_cid
from dincli.services.modelowner import getGenesisModelIpfs, getscoreforGM

model_app = typer.Typer(help="Model-level commands")

@model_app.command("create-genesis")
def create_genesis(
    ctx: typer.Context,
    help: bool = typer.Option(False, "--help","-h", help="Show help"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    if not task_coordinator_address:
        task_coordinator_address = get_env_key(effective_network.upper() + "_DINTaskCoordinator_Contract_Address")
        if not task_coordinator_address:
            raise typer.Exit(1)
        else:
            console.print(f"[bold green] Using DIN Task Coordinator Address: {task_coordinator_address} from {os.getcwd()}/.env[/bold green]")

    if help:
        console.print("[bold green]Usage:[/bold green]")
        console.print("  dincli model-owner model create-genesis --network <network>")
        console.print("\nIf --default flag is not specified, dincli will use getGenesisModelIpfs() from")
        console.print(f"{Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'services' / 'modelowner.py'}")
        console.print(f"The genesis model hash will be set in {os.getcwd()}/.env under {effective_network.upper() + '_' + task_coordinator_address}_GENESIS_MODEL_IPFS_HASH")
        raise typer.Exit(0)

    task_dir = Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address
    os.makedirs(task_dir, exist_ok=True)

    target_manifest = os.path.join(task_dir, "manifest.json")

    if not os.path.exists(target_manifest):
        default_manifest_CID = "bafybeigqmarrtpgzezzsjp4zfnsogtfajnebllvhmbg23h2l3muxj6kntq"
        console.print(f"[bold red]Manifest not found at {target_manifest}[/bold red]")
        console.print(f"[bold yellow]Using default manifest from IPFS CID: {default_manifest_CID}[/bold yellow]")
        retrieve_from_ipfs(default_manifest_CID, target_manifest)

    manifest = get_manifest_key(effective_network, "getGenesisModelIpfs", None, task_coordinator_address)
    service_path = task_dir / Path(manifest["path"])
    model_service_path = task_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"])

    if manifest["type"] == "custom":

        ctx.obj.ensure_file_exists(service_path, manifest["ipfs"], "model owner service")
        ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["ipfs"], "model architecture service")
        console.print("[bold green]Creating genesis model... [/bold green]")
        fn = ctx.obj.load_custom_fn(
            service_path,
            "getGenesisModelIpfs"
        )
        model_hash = fn(task_dir)
    else:
        model_hash = getGenesisModelIpfs(base_path = task_dir)
    
    console.print(f"[bold green]Genesis model created successfully![/bold green]")
    console.print(f"[cyan]Model hash:[/cyan] {model_hash}")

    set_env_key(effective_network.upper() + "_" + task_coordinator_address + "_GENESIS_MODEL_IPFS_HASH", model_hash)

    console.print(f"[bold green]Genesis model hash set in {os.getcwd()}/.env as {effective_network.upper()}_{task_coordinator_address}_GENESIS_MODEL_IPFS_HASH successfully![/bold green]")
    
    return

@model_app.command("submit-genesis")
def submit_genesis(
    ctx: typer.Context,
    ipfs_hash: str = typer.Option(None, "--ipfs-hash", help="IPFS hash of the model"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
    score: int = typer.Option(None, "--score", help="Score of the model"),
    default: bool = typer.Option(False, "--default", help="use default service"),
    help: bool = typer.Option(False, "--help","-h", help="Show help"),
    default_test_data: bool = typer.Option(False, "--default-test-data", help="use default test data"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    if not task_coordinator_address:
        task_coordinator_address = get_env_key(effective_network.upper() + "_DINTaskCoordinator_Contract_Address")
        if not task_coordinator_address:
            raise typer.Exit(1)
    
    if help:
        console.print("[bold green]Usage:[/bold green]")
        console.print("  dincli model-owner model submit-genesis --network <network>")
        console.print("\nIf --default flag is not specified, dincli will use submitGenesisModel() from")
        console.print(f"{Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'services' / 'modelowner.py'}")
        console.print("\n [yellow]Warning:[/yellow] the test dataset must be available at: ")
        console.print(f"  {Path(os.getcwd()) / effective_network.lower() / 'tasks' / task_coordinator_address / 'dataset' / 'test' / 'test_dataset.pt'}")
        console.print("\n [yellow]Warning:[/yellow] the genesis model must be available at: ")
        console.print(f"  {Path(os.getcwd()) / effective_network.lower() / 'tasks' / task_coordinator_address / 'models' / 'genesis_model.pth'}")
        console.print(f"\n [yellow]Warning:[/yellow] If --ipfs-hash is not specified, the genesis model IPFS hash will be read from {os.getcwd()}/.env under {effective_network.upper() + '_' + task_coordinator_address + '_GENESIS_MODEL_IPFS_HASH'}")
        raise typer.Exit(0)
    
    if not ipfs_hash:
        ipfs_hash = get_env_key(effective_network.upper() + "_" + task_coordinator_address + "_GENESIS_MODEL_IPFS_HASH")

        if not ipfs_hash:
            console.print("[bold red]Genesis model IPFS hash not found![/bold red]")
            console.print(f"[yellow]Please set {effective_network.upper() + '_' + task_coordinator_address + '_GENESIS_MODEL_IPFS_HASH'} in {os.getcwd()}/.env[/yellow]")
            raise typer.Exit(1)
    
    console.print(f"[bold green]Submitting genesis model to DIN Task Coordinator![/bold green]")
    console.print(f"[cyan]Genesis model IPFS hash:[/cyan] {ipfs_hash}")

    deployed_DINTaskCoordinatorContract = ctx.obj.get_deployed_din_task_coordinator_contract(True, None, task_coordinator_address)

    if score:
        accuracy = score
    else:
        if not default:
            task_dir = Path.cwd() / 'tasks' / effective_network.lower()/ task_coordinator_address

            manifest = get_manifest_key(effective_network, "getscoreforGM", None, task_coordinator_address)
            service_path = task_dir / Path(manifest["path"])
            model_service_path = task_dir / Path(get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"])

            if manifest["type"] == "custom":
                ctx.obj.ensure_file_exists(service_path, manifest["ipfs"], "model owner service")
                ctx.obj.ensure_file_exists(model_service_path, get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["ipfs"], "model architecture service")

                fn = ctx.obj.load_custom_fn(service_path, "getscoreforGM")

                test_dataset_path = task_dir.joinpath("dataset","test","test_dataset.pt")
                if not test_dataset_path.exists():
                    console.print(f"[bold red] X Test dataset not found at {test_dataset_path} [/bold red]")
                    if default_test_data:
                        default_test_dataset_ipfs_hash = "bafybeigjtcu2nzsffoy5pjmui25bnc43yduzn6aopi4wnrbtxfleqmw46y"
                        console.print(f"[bold yellow] Y Using default test dataset with IPFS CID {default_test_dataset_ipfs_hash} [/bold yellow]")
                        retrieve_from_ipfs(default_test_dataset_ipfs_hash, test_dataset_path)
                    else:
                        raise typer.Exit(1)
                genesis_model_path = task_dir.joinpath("models","genesis_model.pth")
                if not genesis_model_path.exists():
                    console.print(f"[bold red] X Genesis model not found at {genesis_model_path} [/bold red]")
                    raise typer.Exit(1)
                
                accuracy = fn(0, ipfs_hash, task_dir)
                
                if accuracy is None:
                    console.print(f"[bold red] X Accuracy is None[/bold red]")
                    raise typer.Exit(1)
        else:
            accuracy = getscoreforGM(0, ipfs_hash, base_path=Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address)

    
    genesis_ipfs_hash_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(ipfs_hash))

    tx_params = ctx.obj.get_tx_params()
    tx_params["gas"] = int(w3.eth.estimate_gas(deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(genesis_ipfs_hash_bytes32).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
    setGenesisModelIpfsHash_tx = deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(genesis_ipfs_hash_bytes32).build_transaction(tx_params)

    signed = account.sign_transaction(setGenesisModelIpfsHash_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Submitting genesis model tx:[/dim] {tx_hash.hex()}")
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if tx_receipt.status != 1:
        console.print("[bold red] X Failed to submit genesis model![/bold red]")
        raise typer.Exit(1)
    else:
        console.print("[green]✓ Genesis model submitted![/green]")

    if tx_receipt.status == 1:
        time.sleep(10)
        
        console.print("Genesis model accuracy:", accuracy)
        tx_params = ctx.obj.get_tx_params()
        tx_params["gas"] = int(w3.eth.estimate_gas(deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)).build_transaction(tx_params)) * 1.1)  # Add 10% buffer
    
        tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)).build_transaction(tx_params)
        
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        console.print(f"[dim]Submitting genesis model tier 2 score tx:[/dim] {tx_hash.hex()}")
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt.status != 1:
            console.print("[bold red] X Failed to submit genesis model tier 2 score![/bold red]")
            raise typer.Exit(1)
        else:
            console.print("[green]✓ Genesis model tier 2 score set![/green]")

