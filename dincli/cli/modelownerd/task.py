import os
import typer
from pathlib import Path

from dincli.cli.utils import resolve_task_coordinator_address, load_din_info

from dincli.services.ipfs import retrieve_from_ipfs

task_app = typer.Typer(help="task-level commands")


@task_app.command("create-task-dir")
def create_task_dir(ctx: typer.Context, task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address")):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )

    task_dir = Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address
    os.makedirs(task_dir, exist_ok=True)

    console.print(f"[bold green]Task directory created successfully![/bold green]")
    console.print(f"[cyan]Task directory:[/cyan] {task_dir}")


@task_app.command("cache-default-artifacts")
def cache_default_artifacts(
    ctx: typer.Context,
    task_coordinator_address: str = typer.Option(None, "--taskCoordinator", help="Task coordinator address"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    task_coordinator_address = resolve_task_coordinator_address(
        effective_network, task_coordinator_address, console
    )

    task_dir = Path(os.getcwd()) / 'tasks' / effective_network.lower() / task_coordinator_address
    if not task_dir.exists():
        console.print(f"[bold red]Task directory not found at {task_dir}[/bold red]")
        console.print(f"[bold yellow]Please create the task directory first using: dincli model-owner task create-task-dir[/bold yellow]")
        raise typer.Exit(1)

    services_dir = task_dir / "services"
    os.makedirs(services_dir, exist_ok=True)

    abis_dir = task_dir / "abis"
    os.makedirs(abis_dir, exist_ok=True) 

    try: 
        retrieve_from_ipfs(load_din_info()[effective_network]["default_manifest"], task_dir / "manifest.json")
        console.print(f"[bold green]Default manifest cached successfully! at {task_dir / 'manifest.json'}[/bold green]")
    except Exception as e:
        console.print(f"[bold red]Error caching default manifest: {e}[/bold red]")
        raise typer.Exit(1)

    for service_name, service_cid in load_din_info()[effective_network]["default_services"].items():
        try:
            retrieve_from_ipfs(service_cid, services_dir / service_name)
            console.print(f"[bold green]Default service {service_name} cached successfully! at {services_dir / service_name}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Error caching default service {service_name}: {e}[/bold red]")
            raise typer.Exit(1)
    console.print(f"[bold green]Default services cached successfully! at {services_dir}[/bold green]")

    for abi_name, abi_cid in load_din_info()[effective_network]["default_abis"].items():
        try:
            retrieve_from_ipfs(abi_cid, abis_dir / abi_name)
            console.print(f"[bold green]Default abi {abi_name} cached successfully! at {abis_dir / abi_name}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Error caching default abi {abi_name}: {e}[/bold red]")
            raise typer.Exit(1)
    console.print(f"[bold green]Default abis cached successfully! at {abis_dir}[/bold green]")

    requirements_dir = task_dir / "requirements"
    os.makedirs(requirements_dir, exist_ok=True)

    for stakeholder_name, requirements_cid in load_din_info()[effective_network]["default_requirements"].items():
        try:
            retrieve_from_ipfs(requirements_cid, requirements_dir / stakeholder_name / "requirements.txt")
            console.print(f"[bold green]Default requirements cached successfully! at {requirements_dir / stakeholder_name / 'requirements.txt'}[/bold green]")
        except Exception as e:
            console.print(f"[bold red]Error caching default requirements: {e}[/bold red]")
            raise typer.Exit(1)

    console.print(f"[bold yellow]Important Instructions![/bold yellow]")
    console.print(f"[bold yellow]1. Ensure to edit/modify the services as per your task/model specifications![/bold yellow]")
    console.print(f"[bold yellow]2. Ensure to edit/modify the abis as per your task/model specifications![/bold yellow]")
    console.print(f"[bold yellow]3. Ensure to edit/modify the requirements as per your task/model specifications![/bold yellow]")
    console.print(f"[bold yellow]4. Upload the edited/modified services, abis and requirements to IPFS and update the manifest with the new CIDs! use dincli ipfs upload -f path/to/file to upload and get the CID, then update the manifest file with the new CID![/bold yellow]")
    console.print(f"[bold yellow]5. Make sure to check/update other fields in the manifest as per your task/model specifications![/bold yellow]")
    console.print(f"[bold yellow]6. Upload the edited/modified manifest to IPFS [/bold yellow]")
    
        
