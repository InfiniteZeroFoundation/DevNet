import typer

from dincli import __version__
from dincli.cli.aggregator import app as aggregators_app
from dincli.cli.auditor import app as auditor_app
from dincli.cli.client import app as client_app
from dincli.cli.context import DinContext
from dincli.cli.core import GlobalOptionsGroup
from dincli.cli.dindao import app as dindao_app
from dincli.cli.ipfs import app as ipfs_app
from dincli.cli.modelowner import app as model_owner_app
# Import role-specific subcommands
from dincli.cli.system import app as system_app
from dincli.cli.task import app as task_app

app = typer.Typer(
    help="DIN Command Line Interface (CLI) — Validators, Auditors, and Model Owners.",
    pretty_exceptions_enable=False,
    cls=GlobalOptionsGroup,
    )

# Add subcommands for roles
app.add_typer(system_app, name="system")
app.add_typer(dindao_app, name="dindao")
app.add_typer(model_owner_app, name="model-owner")
app.add_typer(aggregators_app, name="aggregator")
app.add_typer(auditor_app, name="auditor")
app.add_typer(client_app, name="client")
app.add_typer(task_app, name="task")
app.add_typer(ipfs_app, name="ipfs")

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show DIN CLI version and exit.",
        callback=None,
        is_eager=True,
    ),
    network: str = typer.Option(
        None,
        "--network",
        help="Specify network (local | sepolia_devnet | sepolia_testnet | mainnet)",
        callback=None,
        is_eager=True,
    ),
    
):
    ctx.obj = DinContext()
    console = ctx.obj.console

    configured_network  = ctx.obj.select_network(network).network
    if configured_network:
        console.print(f"[bold cyan]Active Network:[/bold cyan] {configured_network}")
    else:
        console.print(f"[bold cyan]Network[/bold cyan] not configured")
    
    if version:
        console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")
        raise typer.Exit()
    
@app.command()
def version(ctx: typer.Context):
    """Show DIN CLI version."""
    ctx.obj.console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")



if __name__ == "__main__":
    
    app()
    

