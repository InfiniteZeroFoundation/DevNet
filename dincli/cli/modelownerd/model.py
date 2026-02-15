import os
from pathlib import Path

import typer

from dincli.cli.utils import get_env_key, get_manifest_key, set_env_key
from dincli.services.ipfs import retrieve_from_ipfs
from dincli.services.modelowner import getGenesisModelIpfs, getscoreforGM

model_app = typer.Typer(help="Model-level commands")

@model_app.command("create-genesis")
def create_genesis(
    ctx: typer.Context,
    help: bool = typer.Option(False, "--help","-h", help="Show help"),
    default: bool = typer.Option(False, "--default", help="use default service"),
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    if not task_coordinator_address:
        task_coordinator_address = get_env_key(effective_network.upper() + "_DINTaskCoordinator_Contract_Address")
        if not task_coordinator_address:
            raise typer.Exit(1)
        else:
            console.print(f"[bold green] Using DIN Task Coordinator Address: {task_coordinator_address}[/bold green]")

    if help:
        console.print("[bold green]Usage:[/bold green]")
        console.print("  dincli model-owner model create-genesis --network <network>")
        console.print("\nIf --default flag is not specified, dincli will use getGenesisModelIpfs() from")
        console.print(f"{Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address / 'services' / 'modelowner.py'}")
        console.print(f"The genesis model hash will be set in {os.getcwd()}/.env under {effective_network.upper() + '_' + task_coordinator_address}_GENESIS_MODEL_IPFS_HASH")
        raise typer.Exit(0)

    
    if not default:
        
        tasks_dir = Path.cwd() / 'tasks' / effective_network.lower()
        # Ensure tasks_dir exists
        if not tasks_dir.exists():
            raise FileNotFoundError(f"Tasks directory not found: {tasks_dir}")

        # Check if target already exists
        target_folder = tasks_dir / task_coordinator_address

        # ### Start - To Delete ###
        # # Find all subdirs that look like Ethereum addresses
        # eth_like_subdirs = [
        #     p for p in tasks_dir.iterdir()
        #     if p.is_dir() and is_ethereum_address(p.name)
        # ]

        # target_normalized = task_coordinator_address.lower()

        # # Check if target already exists (case-insensitively)
        # target_exists = any(
        #     p.name.lower() == target_normalized for p in eth_like_subdirs
        # )

        # if not target_exists:
        #     # Filter out the target itself just in case (shouldn't be needed, but safe)
        #     candidates = [p for p in eth_like_subdirs if p.name.lower() != target_normalized]
        #     if len(candidates) == 1:
        #         # Exactly one folder exists → assume it's the one to rename
        #         old_folder = candidates[0]
        #         console.print(f"Auto-renaming task coordinator folder: {old_folder.name} → {task_coordinator_address}")
        #         old_folder.rename(target_folder)
        #     elif len(candidates) == 0:
        #         raise FileNotFoundError(
        #             f"No existing Ethereum-like coordinator folder found in {tasks_dir}, "
        #             f"and target '{task_coordinator_address}' does not exist."
        #         )
        #     else:
        #         raise RuntimeError(
        #             f"Multiple Ethereum-like coordinator folders found, but target is missing. "
        #             f"Cannot auto-rename. Candidates: {[p.name for p in candidates]}"
        #         )
        # ### End - To Delete ###
        # # Construct the path


        if get_manifest_key(effective_network, "getGenesisModelIpfs", None, task_coordinator_address)["type"] == "custom":
            service_path_str = get_manifest_key(effective_network, "getGenesisModelIpfs", None, task_coordinator_address)["path"]
            service_path = target_folder / Path(service_path_str)

        if not service_path.exists():
            retrieve_from_ipfs(get_manifest_key(effective_network,"getGenesisModelIpfs", None, task_coordinator_address)["ipfs"], service_path)

        model_service_path_str = target_folder / get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"]
        model_service_path = target_folder / Path(model_service_path_str)

        if not model_service_path.exists():
            retrieve_from_ipfs(get_manifest_key(effective_network,"ModelArchitecture", None, task_coordinator_address)["ipfs"], model_service_path)

        console.print("[bold green]Creating genesis model... [/bold green]")
        fn = ctx.obj.load_custom_fn(
            service_path,
            "getGenesisModelIpfs"
        )
        base_path = Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address
        model_hash = fn(base_path)
    else:
        model_hash = getGenesisModelIpfs(base_path = Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address)
    
    
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
    
    console.print(f"[bold green]Submitting genesis model to DIN Task Coordinator![/bold green]")
    console.print(f"[cyan]Genesis model IPFS hash:[/cyan] {ipfs_hash}")

    deployed_DINTaskCoordinatorContract = ctx.obj.get_deployed_din_task_coordinator_contract(True, None, task_coordinator_address)

    if score:
        accuracy = score
    else:
        if not default:
            tasks_dir = Path.cwd() / 'tasks' / effective_network.lower()
            target_folder = tasks_dir / task_coordinator_address

            if get_manifest_key(effective_network, "getscoreforGM", None, task_coordinator_address)["type"] == "custom":
                service_path_str = get_manifest_key(effective_network, "getscoreforGM", None, task_coordinator_address)["path"]
                service_path = target_folder / Path(service_path_str)

                if not service_path.exists():
                    retrieve_from_ipfs(get_manifest_key(effective_network,"getscoreforGM", None, task_coordinator_address)["ipfs"], service_path)
                
                model_service_path_str = target_folder / get_manifest_key(effective_network, "ModelArchitecture", None, task_coordinator_address)["path"]
                model_service_path = target_folder / Path(model_service_path_str)

                if not model_service_path.exists():
                    retrieve_from_ipfs(get_manifest_key(effective_network,"ModelArchitecture", None, task_coordinator_address)["ipfs"], model_service_path)

                fn = ctx.obj.load_custom_fn(service_path, "getscoreforGM")

                test_dataset_path = target_folder.joinpath("dataset","test","test_dataset.pt")
                if not test_dataset_path.exists():
                    console.print(f"[bold red] X Test dataset not found at {test_dataset_path} [/bold red]")
                    raise typer.Exit(1)
                genesis_model_path = target_folder.joinpath("models","genesis_model.pth")
                if not genesis_model_path.exists():
                    console.print(f"[bold red] X Genesis model not found at {genesis_model_path} [/bold red]")
                    raise typer.Exit(1)
                
                accuracy = fn(0, ipfs_hash, target_folder)
                
                if accuracy is None:
                    console.print(f"[bold red] X Accuracy is None[/bold red]")
                    raise typer.Exit(1)
        else:
            accuracy = getscoreforGM(0, ipfs_hash, base_path=Path(os.getcwd()) / "tasks" / effective_network.lower() / task_coordinator_address)

    
    setGenesisModelIpfsHash_tx = deployed_DINTaskCoordinatorContract.functions.setGenesisModelIpfsHash(ipfs_hash).build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 200_000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })

    signed = account.sign_transaction(setGenesisModelIpfsHash_tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Submitting genesis model tx:[/dim] {tx_hash.hex()}")
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Genesis model submitted![/green]")
         
    console.print("Genesis model accuracy:", accuracy)
    nonce = w3.eth.get_transaction_count(account.address)
        
    tx = deployed_DINTaskCoordinatorContract.functions.setTier2Score(0, int(accuracy)).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": w3.to_wei("5", "gwei"),
        "chainId": w3.eth.chain_id,
    })
        
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    console.print(f"[dim]Submitting genesis model tier 2 score tx:[/dim] {tx_hash.hex()}")
    w3.eth.wait_for_transaction_receipt(tx_hash)
    console.print("[green]✓ Genesis model tier 2 score set![/green]")
