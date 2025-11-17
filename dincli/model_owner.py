import typer
from rich import print

app = typer.Typer(help="Commands for Model Owners in DIN.")

@app.command()
def deploy(contract_abi_path: str, contract_type: str):
    """
    Deploy a FL task contract
    """
    print("contact deployed succesfully")