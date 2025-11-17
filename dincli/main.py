import typer
from rich.console import Console

# Import role-specific subcommands
from .model_owner import app as model_owner_app


__version__ = "0.1.0"

app = typer.Typer(help="DIN Command Line Interface (CLI) — Validators, Auditors, and Model Owners.",
                  )
console = Console()

# Add subcommands for roles
app.add_typer(model_owner_app, name="model-owner")

@app.callback(invoke_without_command=True)
def main(
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        help="Show DIN CLI version and exit.",
        callback=None,
        is_eager=True,
    )
):
    if version:
        console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")
        raise typer.Exit()
    
    
@app.command()
def version():
    """Show DIN CLI version."""
    console.print(f"[bold cyan]DIN CLI[/bold cyan] v{__version__} — Decentralized Intelligence Network")

if __name__ == "__main__":
    app()
