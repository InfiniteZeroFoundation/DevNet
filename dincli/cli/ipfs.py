
import typer
from rich.console import Console

from dincli.services.ipfs import retrieve_from_ipfs, upload_to_ipfs

console = Console()

app = typer.Typer(help="Commands for IPFS")


@app.command()
def upload(
    file_path: str = typer.Option(..., "-f", "--file-path", help="Path to file to upload"),
    name: str = typer.Option("File", "-n", "--name", help="Name of the file")
):

    console.print(f"Uploading {file_path} to IPFS")
    CID = upload_to_ipfs(file_path, name)
    console.print(f"File uploaded to IPFS with CID: {CID}")

@app.command()
def download(
    CID: str = typer.Option(..., "-c", "--cid", help="CID of file to download"),
    file_path: str = typer.Option(..., "-f", "--file-path", help="Path to file to save")
):

    retrieve_from_ipfs(CID, file_path )
