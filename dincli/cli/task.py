import os
from pathlib import Path
import json
import typer

from dincli.cli.utils import cache_manifest, get_env_key
from dincli.services.ipfs import upload_to_ipfs

app = typer.Typer(help="Manage DIN tasks/models across networks.")

model_owner_app = typer.Typer( help="model owner commands")


app.add_typer(model_owner_app, name="model-owner")



# @app.command()
# def list(
#     network: str = typer.Option(None, help="Target network"),
#     models: bool = typer.Option(False, "--models", help="List models"),
#     roles: bool = typer.Option(False, "--roles", help="List roles for a model"),
#     model_id: str = typer.Option(None, "--model-id", help="Model ID (e.g. model_0)"),
# ):
#     """
#     List networks, models, or roles depending on flags.
#     """

#     effective_network = resolve_network(network)

#     tasks = load_tasks()

#     if "networks" not in tasks:
#         tasks["networks"] = {}

#     if effective_network not in tasks["networks"]:
#         tasks["networks"][effective_network] = {}



# @app.command()
# def add(
#     network: str = typer.Option(...),
#     model_id: int = typer.Option(...),
#     role: str = typer.Option(...),
# ):
#     """
#     Add a model role binding.
#     """

#     if role not in ["aggregator", "auditor", "client", "model-owner"]:
#         print(f"[red]Error:[/red] Invalid role: {role}")
#         raise typer.Exit(1)

#     effective_network = resolve_network(network)

#     tasks = load_tasks()

#     if "networks" not in tasks:
#         tasks["networks"] = {}

#     if effective_network not in tasks["networks"]:
#         tasks["networks"][effective_network] = {}

#     if "model_" + str(model_id) not in tasks["networks"][effective_network]:

#         roles = []
#         manifesto_cid = "None"
#         genesis_model_cid = "None"
        
#         if role not in roles:
#             roles.append(role)
        
#         tasks["networks"][effective_network]["model_" + str(model_id)] = {
#             "manifesto_cid": manifesto_cid,
#             "genesis_model_cid": genesis_model_cid,
#             "roles": roles
#         }

    

#     tasks["networks"][effective_network][model_id][role] = True

#     save_tasks(tasks)

#     print(f"[green]Model role binding added successfully: {model_id} {role}[/green]")





# @app.command()
# def remove(
#     network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
# )

# @app.command()
# def activate(
#     network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
# )

# @app.command()
# def deactivate(
#     network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
# )


# @app.command()
# def update(
#     network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
# )

@app.command()
def explore(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
    update: bool = typer.Option(False, "--update", help="Update model info"),
):
    """
    Explore a model.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    cache_manifest(model_id, effective_network, True, update, True)
    
@model_owner_app.command("register") 
def register(
    ctx: typer.Context,
    taskCoordinator: str = typer.Option(None, "--taskCoordinator"),
    taskAuditor: str = typer.Option(None, "--taskAuditor"),
    manifestpath: str = typer.Option(None, "--manifestpath"),
    manifestCID: str = typer.Option(None, "--manifestCID"),
    isOpenSource: bool = typer.Option(False, "--isOpenSource"),
):
    """ 
    Register a model in DINRegistry
    """ 
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()


    if not taskCoordinator:
        key = effective_network.upper() + "_DINTaskCoordinator_Contract_Address"
        taskCoordinator = get_env_key(key)
        console.print(f"[gray]Task Coordinator not provided, using {key} : {taskCoordinator} from {os.getcwd()}/.env[/gray]")

    if not taskAuditor:
        key = effective_network.upper() + "_" + taskCoordinator + "_DINTaskAuditor_Contract_Address"
        taskAuditor = get_env_key(key)
        console.print(f"[gray]Task Auditor not provided, using {key} : {taskAuditor} from {os.getcwd()}/.env[/gray]")

    genesis_model_ipfs_hash = get_env_key(effective_network.upper() + "_" + taskCoordinator + "_GENESIS_MODEL_IPFS_HASH")
    if not genesis_model_ipfs_hash:
        console.print(f"[red]Error:[/red] Could not find {effective_network.upper()}_{taskCoordinator}_GENESIS_MODEL_IPFS_HASH in .env")
        raise typer.Exit(1)

    if not manifestCID:
        console.print("[gray]Manifest CID not provided, uploading manifest to IPFS...[/gray]")
        if not manifestpath:
            manifestpath = Path(os.getcwd()) / "tasks" /effective_network.lower() / taskCoordinator / "manifest.json"
            console.print(f"[gray]Custom manifest path not provided, using default manifest path: {manifestpath}[/gray]")
        if not os.path.exists(manifestpath):
            console.print("[red]Error:[/red] Manifest not found at path: {manifestpath}")
            raise typer.Exit(1)

        with open(manifestpath, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        if manifest_data["DINTaskCoordinator_Contract"] != taskCoordinator:
            manifest_data["DINTaskCoordinator_Contract"] = taskCoordinator
        
        if manifest_data["DINTaskAuditor_Contract"] != taskAuditor:
            manifest_data["DINTaskAuditor_Contract"] = taskAuditor

        if manifest_data["Genesis_Model_CID"] != genesis_model_ipfs_hash:
            manifest_data["Genesis_Model_CID"] = genesis_model_ipfs_hash

        with open(manifestpath, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=4)

        manifestCID = upload_to_ipfs(str(manifestpath), "manifest")
       
    dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()
    # Get nonce
    nonce = w3.eth.get_transaction_count(account.address)
    console.print(f"[green]Registering model in DINRegistry[/green]")
    console.print(f"[gray]Manifest CID: {manifestCID}[/gray]")
    console.print(f"[gray]Task Coordinator: {taskCoordinator}[/gray]")
    console.print(f"[gray]Task Auditor: {taskAuditor}[/gray]")
    console.print(f"[gray]Is Open Source: {isOpenSource}[/gray]")

    tx = dinregistry_contract.functions.registerModel(manifestCID, taskCoordinator, taskAuditor, isOpenSource).build_transaction({
        'value':  w3.to_wei(0.01, 'ether'),
        'from': account.address,
        'nonce': nonce,
        'gas': 1000000,
        'gasPrice': w3.eth.gas_price,
        'chainId': w3.eth.chain_id
    })

    signed_tx = account.sign_transaction(tx)


    # Send raw transaction
    tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    if tx_receipt.status == 1:
        console.print(f"[green]Model registered successfully in DINRegistry[/green]")

        events = dinregistry_contract.events.ModelRegistered().process_receipt(tx_receipt)

        if events:
            event = events[0]  # Usually one, but could be more in complex cases
            args = event['args']
            console.print("[bold cyan]ModelRegistered Event Emitted:[/bold cyan]")
            console.print(f"  Model ID: {args['modelId']}")
            console.print(f"  Owner: {args['owner']}")
            console.print(f"  Is Open Source: {args['isOpenSource']}")
            console.print(f"  Manifest CID: {args['manifestCID']}")
            console.print(f"  Transaction Hash: {tx_hash.hex()}")
    else:
        console.print("[yellow]Warning: ModelRegistered event not found in receipt.[/yellow]")

    
@model_owner_app.command("update-manifest")
def update_manifest(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
    manifestpath: str = typer.Option(None, "--manifestpath"),
    manifestCID: str = typer.Option(None, "--manifestCID"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()

    model_data = dinregistry_contract.functions.getModel(model_id).call()

    taskCoordinator = model_data[4]
    owner = model_data[0]

    if owner != account.address:
        console.print("[red]Error:[/red] You are not the owner of this model")
        raise typer.Exit(1)
    
    if not manifestCID:

        console.print("[gray]Manifest CID not provided, uploading manifest to IPFS...[/gray]")
        if not manifestpath:
            manifestpath = Path(os.getcwd()) / "tasks" /effective_network.lower() / taskCoordinator / "manifest.json"
            console.print(f"[gray]Custom manifest path not provided, using default manifest path: {manifestpath}[/gray]")
        if not os.path.exists(manifestpath):
            console.print("[red]Error:[/red] Manifest not found at path: {manifestpath}")
            raise typer.Exit(1)
        manifestCID = upload_to_ipfs(str(manifestpath), "manifest")

    curr_manifestCID = model_data[2]

    if curr_manifestCID == manifestCID:
        console.print("[yellow]Manifest CID is the same as the current manifest CID. No update needed.[/yellow]")
        typer.Exit(1)

    else:
        console.print("[green]Updating manifest CID for model ID {}...[/green]".format(model_id))
        console.print(f"[gray]Current manifest CID: {curr_manifestCID}[/gray]")
        console.print(f"[gray]New manifest CID: {manifestCID}[/gray]")

        nonce = w3.eth.get_transaction_count(account.address)

        tx = dinregistry_contract.functions.updateManifest(model_id, manifestCID).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 1000000,
            'gasPrice': w3.eth.gas_price,
            'chainId': w3.eth.chain_id
        })

        signed_tx = account.sign_transaction(tx)

        # Send raw transaction
        tx_hash = w3.eth.send_raw_transaction(signed_tx.raw_transaction)
        tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        if tx_receipt.status == 1:
            console.print("[green]Manifest CID updated successfully for model ID {}[/green]".format(model_id))
        else:
            console.print("[red]Error: Manifest CID update failed for model ID {}[/red]".format(model_id))
            raise typer.Exit(1)

        events = dinregistry_contract.events.ManifestUpdated().process_receipt(tx_receipt)

        if events:
            event = events[0]  # Usually one, but could be more in complex cases
            args = event['args']
            console.print("[bold cyan]ManifestUpdated Event Emitted:[/bold cyan]")
            console.print(f"  Model ID: {args['modelId']}")
            console.print(f"  New Manifest CID: {args['newManifestCID']}")
            console.print(f"  Transaction Hash: {tx_hash.hex()}")
        else:
            console.print("[yellow]Warning: ManifestUpdated event not found in receipt.[/yellow]")
            
@app.command("total-models")
def total_models(ctx: typer.Context,
    ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    models_length = DINModelRegistry_Contract.functions.totalModels().call()

    console.print(f"[bold green]Total models: {models_length}[/bold green]")
        
        



            
    
    
