import typer
from rich import print
from dincli.utils import resolve_network, CONFIG_DIR, load_tasks, save_tasks

app = typer.Typer(help="Manage DIN tasks/models across networks.")

model_owner_app = typer.Typer( help="model owner commands")


app.add_typer(model_owner_app, name="model-owner")



@app.command()
def list(
    network: str = typer.Option(None, help="Target network"),
    models: bool = typer.Option(False, "--models", help="List models"),
    roles: bool = typer.Option(False, "--roles", help="List roles for a model"),
    model_id: str = typer.Option(None, "--model-id", help="Model ID (e.g. model_0)"),
):
    """
    List networks, models, or roles depending on flags.
    """

    effective_network = resolve_network(network)

    tasks = load_tasks()

    if "networks" not in tasks:
        tasks["networks"] = {}

    if effective_network not in tasks["networks"]:
        tasks["networks"][effective_network] = {}



@app.command()
def add(
    network: str = typer.Option(...),
    model_id: int = typer.Option(...),
    role: str = typer.Option(...),
):
    """
    Add a model role binding.
    """

    if role not in ["aggregator", "auditor", "client", "model-owner"]:
        print(f"[red]Error:[/red] Invalid role: {role}")
        raise typer.Exit(1)

    effective_network = resolve_network(network)

    tasks = load_tasks()

    if "networks" not in tasks:
        tasks["networks"] = {}

    if effective_network not in tasks["networks"]:
        tasks["networks"][effective_network] = {}

    if "model_" + str(model_id) not in tasks["networks"][effective_network]:

        roles = []
        manifesto_cid = "None"
        genesis_model_cid = "None"
        
        if role not in roles:
            roles.append(role)
        
        tasks["networks"][effective_network]["model_" + str(model_id)] = {
            "manifesto_cid": manifesto_cid,
            "genesis_model_cid": genesis_model_cid,
            "roles": roles
        }

    

    tasks["networks"][effective_network][model_id][role] = True

    save_tasks(tasks)

    print(f"[green]Model role binding added successfully: {model_id} {role}[/green]")





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
    network: str = typer.Option(None, "--network", help="Target network (local|sepolia|mainnet)"),
    model_id: int = typer.Option(..., "--model-id", help="Model ID (e.g. 0,1,2)"),
):
    """
    Explore a model.
    """
    effective_network = resolve_network(network)

    w3 = get_w3(effective_network)
    
@model_owner_app.command("register") 
def register(
    network: str = typer.Option(None, "--network"),
    taskCoordinator: str = typer.Option(..., "--taskCoordinator"),
):
    """
    Register a model owner.
    """
    effective_network = resolve_network(network)

    w3 = get_w3(effective_network)

    taskCoordinator_contract = w3.eth.contract(address=taskCoordinator, abi=taskCoordinator_abi)

    taskCoordinator_contract.functions.registerModelOwner().transact()
