import typer
from rich.console import Console
from dincli.log import logger, logging

# Import role-specific subcommands
from .system import app as system_app
from .dindao import app as dindao_app
from .modelowner import app as model_owner_app
from .aggregator import app as aggregators_app
from .auditor import app as auditor_app
from .client import app as client_app
from .task import app as task_app

from dincli.utils import get_config, resolve_network


from dincli import __version__

app = typer.Typer(help="DIN Command Line Interface (CLI) — Validators, Auditors, and Model Owners.",
                  )
console = Console()


# # Initialize logging
# log_level_str = get_config("log_level", default="INFO")
# logger.setLevel(getattr(logging, log_level_str.upper(), logging.INFO))
# Use default until config is loaded later (or accept that CLI logs use INFO by default)
logger.setLevel(logging.INFO)

# Add subcommands for roles
app.add_typer(system_app, name="system")
app.add_typer(dindao_app, name="dindao")
app.add_typer(model_owner_app, name="model-owner")
app.add_typer(aggregators_app, name="aggregator")
app.add_typer(auditor_app, name="auditor")
app.add_typer(client_app, name="client")
app.add_typer(task_app, name="task")

@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show DIN CLI version and exit.",
        callback=None,
        is_eager=True,
    ),
     network: bool = typer.Option(
         None, 
         "--network", 
         help="Specify network", 
         callback=None,
         is_eager=True,
     ),
    
):
    
    if version:
        console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")
        raise typer.Exit()
    if network:
        configured_network  = resolve_network(cli_network=None)
        if configured_network:
            print(f"[bold cyan]Active Network:[/bold cyan] {configured_network}")
            raise typer.Exit()
        else:
            console.print(f"[bold cyan]Network[/bold cyan] not configured")
            raise typer.Exit()
    
@app.command()
def version():
    """Show DIN CLI version."""
    console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")



if __name__ == "__main__":
    
    app()
    

