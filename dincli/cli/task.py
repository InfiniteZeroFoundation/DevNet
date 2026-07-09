import os
from pathlib import Path
import json
import typer
from web3 import Web3

from dincli.cli.utils import (CACHE_DIR, build_and_send_tx, cache_manifest, _confirm_or_exit,
                               get_env_key, GIstateToStr,
                               resolve_task_coordinator_address)
from dincli.services.ipfs import upload_to_ipfs
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32

app = typer.Typer(help="Manage DIN tasks/models across networks.")

model_owner_app = typer.Typer( help="model owner commands")
gi_app = typer.Typer(help="Global iteration commands")


app.add_typer(model_owner_app, name="model-owner")
app.add_typer(gi_app, name="gi")


def _request_status(processed: bool, approved: bool) -> str:
    if not processed:
        return "pending"
    return "approved" if approved else "rejected"


def _print_model_request(console, w3, request_id: int, req):
    console.print(f"[bold cyan]Model Registration Request {request_id}[/bold cyan]")
    console.print(f"  Requester: {req[0]}")
    console.print(f"  Is Open Source: {req[1]}")
    console.print(f"  Manifest CID: {get_cid_from_bytes32(req[2].hex())}")
    console.print(f"  Task Coordinator: {req[3]}")
    console.print(f"  Task Auditor: {req[4]}")
    console.print(f"  Fee Paid: {w3.from_wei(req[5], 'ether')} ETH")
    console.print(f"  Status: {_request_status(req[6], req[7])}")
    console.print(f"  Created At: {req[8]}")


def _print_manifest_request(console, w3, request_id: int, req):
    console.print(f"[bold cyan]Manifest Update Request {request_id}[/bold cyan]")
    console.print(f"  Model ID: {req[0]}")
    console.print(f"  New Manifest CID: {get_cid_from_bytes32(req[1].hex())}")
    console.print(f"  Requester: {req[2]}")
    console.print(f"  Fee Paid: {w3.from_wei(req[3], 'ether')} ETH")
    console.print(f"  Status: {_request_status(req[4], req[5])}")


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
    

@gi_app.command("show-state")
def show_state(
    ctx: typer.Context,
    model_id: str = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    """
    Show the state of a global iteration.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(task_coordinator)

    target_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    console.print(f"[bold green]Showing global iteration state for global iteration {curr_GI}[/bold green]")
    console.print(f"[cyan]Global iteration numerical state:[/cyan] {curr_GIstate}")
    console.print(f"[cyan]Global iteration state:[/cyan] {GIstateToStr(curr_GIstate)}")
    console.print("[green]✓ Global iteration state shown![/green]")


@model_owner_app.command("register-request")
def register_request(
    ctx: typer.Context,
    taskCoordinator: str = typer.Option(None, "--taskCoordinator"),
    taskAuditor: str = typer.Option(None, "--taskAuditor"),
    manifestpath: str = typer.Option(None, "--manifestpath"),
    manifestCID: str = typer.Option(None, "--manifestCID"),
    isOpenSource: bool = typer.Option(False, "--isOpenSource"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    console.print(f"[bold green]Submitting model registration request to DINRegistry ...[/bold green]")

    if not taskCoordinator:
        taskCoordinator = resolve_task_coordinator_address(
            effective_network, None, console, verbose=True
        )
    
    if not taskAuditor:
        key = effective_network.upper() + "_" + taskCoordinator + "_DINTaskAuditor_Contract_Address"
        taskAuditor = get_env_key(key)
        console.print(f"[gray]Task Auditor not provided, using {key} : {taskAuditor} from {os.getcwd()}/.env[/gray]")

    
    if not manifestCID:
        console.print("[gray]Manifest CID not provided, uploading manifest to IPFS...[/gray]")
        if not manifestpath:
            manifestpath = Path(os.getcwd()) / "tasks" / effective_network.lower() / taskCoordinator / "manifest.json"
            console.print(f"[gray]Custom manifest path not provided, using default manifest path[/gray]")

        if not os.path.exists(manifestpath):
            console.print(f"[red]Error:[/red] Manifest not found at path: {manifestpath}")
            raise typer.Exit(1)
        console.print(f" [blue]Manifest path:[/blue] [magenta] {manifestpath}[/magenta]")

    
        _confirm_or_exit(
                f"Have you run dincli m dincli.main model-owner model validate-update-manifest to update the manifest from the {os.getcwd()}/.env?",
                "Please run dincli m dincli.main model-owner model validate-update-manifest to update the manifest from the .env file.",
                console,
            )
        
        _confirm_or_exit(
                "Have you throughly read/modify all the parameters/CID values in the manifest file above as needed?",
                "Please edit/modify all the parameters/CID values in the manifest file.",
                console,
            )

        manifestCID = upload_to_ipfs(str(manifestpath), "manifest")

        dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()

    console.print(f"[green]Requesting model registration in DINRegistry[/green]")
    console.print(f"[gray]Manifest CID: {manifestCID}[/gray]")
    console.print(f"[gray]Task Coordinator: {taskCoordinator}[/gray]")
    console.print(f"[gray]Task Auditor: {taskAuditor}[/gray]")
    console.print(f"[gray]Is Open Source: {isOpenSource}[/gray]")

    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    console.print(f"[green]ETH Balance:[/green] {balance_eth} ETH")

    manifestCID_bytes32 = get_bytes32_from_cid(manifestCID)
    bytes32_value = Web3.to_bytes(hexstr=manifestCID_bytes32)
    required_fee = (
        dinregistry_contract.functions.openSourceFee().call()
        if isOpenSource
        else dinregistry_contract.functions.proprietaryFee().call()
    )
    console.print(f"[gray]Required fee: {w3.from_wei(required_fee, 'ether')} ETH[/gray]")

    _confirm_or_exit(
        "Proceed with submitting the model registration request on-chain?",
        "Model registration request aborted by user.",
        console,
    )

    tx_receipt = build_and_send_tx(
        ctx,
        dinregistry_contract.functions.requestModelRegistration(
            bytes32_value,
            taskCoordinator,
            taskAuditor,
            isOpenSource,
        ),
        "Submitting model registration request in DINRegistry",
        "Model registration request submitted successfully in DINRegistry",
        "Model registration request failed in DINRegistry",
        tx_params={"value": required_fee},
    )

    balance_wei = w3.eth.get_balance(account.address)
    balance_eth = w3.from_wei(balance_wei, "ether")
    console.print(f"[green]ETH Balance after request:[/green] {balance_eth} ETH")

    events = dinregistry_contract.events.ModelRegistrationRequested().process_receipt(tx_receipt)

    if events:
        event = events[0]
        args = event['args']
        console.print("[bold cyan]ModelRegistrationRequested Event Emitted:[/bold cyan]")
        console.print(f"  Request ID: {args['requestId']}")
        console.print(f"  Requester: {args['requester']}")
        console.print("  Status: pending")
        console.print("[yellow]The model is not registered until DIN DAO approves this request.[/yellow]")
    else:
        console.print("[yellow]Warning: ModelRegistrationRequested event not found in receipt.[/yellow]")


@model_owner_app.command("update-manifest-request")
def update_manifest_request(
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
    is_open_source = model_data[1]

    if owner.lower() != account.address.lower():
        console.print("[red]Error:[/red] You are not the owner of this model")
        raise typer.Exit(1)

    if not manifestCID:
        console.print("[gray]Manifest CID not provided, uploading manifest to IPFS...[/gray]")
        if not manifestpath:
            manifestpath = ctx.obj.get_model_base_dir(model_id) / "manifest.json"
            console.print(f"[gray]Custom manifest path not provided, using default manifest path: {manifestpath}[/gray]")
        if not os.path.exists(manifestpath):
            console.print(f"[red]Error:[/red] Manifest not found at path: {manifestpath}")
            raise typer.Exit(1)
        manifestCID = upload_to_ipfs(str(manifestpath), "manifest")

    curr_manifestCID = get_cid_from_bytes32(model_data[2].hex())

    if curr_manifestCID == manifestCID:
        console.print("[yellow]Manifest CID is the same as the current manifest CID. No update needed.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[green]Submitting manifest update request for model ID {model_id}...[/green]")
    console.print(f"[gray]Current manifest CID: {curr_manifestCID}[/gray]")
    console.print(f"[gray]New manifest CID: {manifestCID}[/gray]")

    manifestCID_bytes32 = get_bytes32_from_cid(manifestCID)
    bytes32_value = Web3.to_bytes(hexstr=manifestCID_bytes32)
    required_fee = (
        dinregistry_contract.functions.openSourceUpdateFee().call()
        if is_open_source
        else dinregistry_contract.functions.proprietaryUpdateFee().call()
    )
    console.print(f"[gray]Required fee: {w3.from_wei(required_fee, 'ether')} ETH[/gray]")

    _confirm_or_exit(
        "Proceed with submitting the manifest update request on-chain?",
        "Manifest update request aborted by user.",
        console,
    )

    tx_receipt = build_and_send_tx(
        ctx,
        dinregistry_contract.functions.requestManifestUpdate(model_id, bytes32_value),
        f"Submitting manifest update request for model ID {model_id}",
        f"Manifest update request submitted successfully for model ID {model_id}",
        f"Manifest update request failed for model ID {model_id}",
        tx_params={"value": required_fee},
    )

    events = dinregistry_contract.events.ManifestUpdateRequested().process_receipt(tx_receipt)

    if events:
        event = events[0]
        args = event['args']
        console.print("[bold cyan]ManifestUpdateRequested Event Emitted:[/bold cyan]")
        console.print(f"  Request ID: {args['requestId']}")
        console.print(f"  Model ID: {args['modelId']}")
        console.print("  Status: pending")
        console.print("[yellow]The manifest is not updated until DIN DAO approves this request.[/yellow]")
        console.print(f"  Transaction Hash: {tx_receipt.transactionHash.hex()}")
    else:
        console.print("[yellow]Warning: ManifestUpdateRequested event not found in receipt.[/yellow]")


@model_owner_app.command("show-registration-request")
def show_registration_request(
    ctx: typer.Context,
    request_id: int = typer.Argument(..., help="Registration request ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()
    req = dinregistry_contract.functions.modelRequests(request_id).call()
    if req[0].lower() != account.address.lower():
        console.print("[red]Error:[/red] This registration request was not submitted by the active account")
        raise typer.Exit(1)
    _print_model_request(console, w3, request_id, req)
    if req[6] and req[7]:
        exists, approved_model_id = dinregistry_contract.functions.getModelIdByTaskCoordinator(req[3]).call()
        if exists:
            console.print(f"[green]Approved model ID: {approved_model_id}[/green]")


@model_owner_app.command("show-manifest-update-request")
def show_manifest_update_request(
    ctx: typer.Context,
    request_id: int = typer.Argument(..., help="Manifest update request ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()
    req = dinregistry_contract.functions.manifestRequests(request_id).call()
    if req[2].lower() != account.address.lower():
        console.print("[red]Error:[/red] This manifest update request was not submitted by the active account")
        raise typer.Exit(1)
    _print_manifest_request(console, w3, request_id, req)


@model_owner_app.command("my-requests")
def my_requests(
    ctx: typer.Context,
    request_type: str = typer.Option(None, "--type", "-t", help="Type of request: [model, manifest]"),
    include_processed: bool = typer.Option(False, "--include-processed", "--ip", help="Include approved and rejected requests"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    dinregistry_contract = ctx.obj.get_deployed_din_registry_contract()
    normalized_type = request_type.lower() if request_type else None

    if normalized_type not in (None, "model", "manifest"):
        console.print("[red]Error:[/red] --type must be 'model' or 'manifest'")
        raise typer.Exit(1)

    if normalized_type in (None, "model"):
        total = dinregistry_contract.functions.totalModelRequests().call()
        console.print("[bold cyan]Your Model Registration Requests[/bold cyan]")
        found = False
        for request_id in range(total):
            req = dinregistry_contract.functions.modelRequests(request_id).call()
            if req[0].lower() == account.address.lower() and (include_processed or not req[6]):
                console.print(f"  Request ID {request_id}: {_request_status(req[6], req[7])}, manifest {get_cid_from_bytes32(req[2].hex())}")
                found = True
        if not found:
            console.print("  [gray]No matching model registration requests[/gray]")

    if normalized_type in (None, "manifest"):
        total = dinregistry_contract.functions.totalManifestRequests().call()
        console.print("[bold cyan]Your Manifest Update Requests[/bold cyan]")
        found = False
        for request_id in range(total):
            req = dinregistry_contract.functions.manifestRequests(request_id).call()
            if req[2].lower() == account.address.lower() and (include_processed or not req[4]):
                console.print(f"  Request ID {request_id}: {_request_status(req[4], req[5])}, model {req[0]}, new manifest {get_cid_from_bytes32(req[1].hex())}")
                found = True
        if not found:
            console.print("  [gray]No matching manifest update requests[/gray]")


@app.command("sum-registered-models")
def sum_registered_models(ctx: typer.Context,
    ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    models_length = DINModelRegistry_Contract.functions.totalModels().call()

    console.print(f"[bold green]Total registered models: {models_length}[/bold green]")


@app.command("sum-model-registration-requests")
def sum_model_registration_requests(ctx: typer.Context,
    ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    models_length = DINModelRegistry_Contract.functions.totalModelRequests().call()

    console.print(f"[bold green]Total model registration requests: {models_length}[/bold green]")  

@app.command("sum-manifest-update-requests")
def sum_manifest_update_requests(ctx: typer.Context,
    ):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()

    DINModelRegistry_Contract = ctx.obj.get_deployed_din_registry_contract()

    models_length = DINModelRegistry_Contract.functions.totalManifestRequests().call()

    console.print(f"[bold green]Total manifest update requests: {models_length}[/bold green]")  
        



            
    
    
