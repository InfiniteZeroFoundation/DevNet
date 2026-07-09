from pathlib import Path
from typing import Optional

import typer
from web3 import Web3

from dincli.cli.utils import CACHE_DIR, build_and_send_tx, require_custom_manifest_service, _confirm_or_exit
from dincli.cli.worker import (
    ensure_worker_image,
    ensure_worker_packages_installed,
    get_worker_packages_dir,
    get_worker_requirements_path,
    read_worker_result,
    run_worker_container,
    write_worker_job,
)
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32
from dincli.services.ipfs import upload_to_ipfs

app = typer.Typer(help="Commands for DIN clients in DIN.")
lms_app = typer.Typer(help="LMS related commands")
app.add_typer(lms_app, name="lms")

DISABLED_DP_MODES = {"disabled", "none", "off", "false"}
DP_MECHANISM_ALIASES = {
    "gaussian": "post_training_gaussian",
    "post-training-gaussian": "post_training_gaussian",
    "laplace": "post_training_laplace",
    "post-training-laplace": "post_training_laplace",
    "update": "update_gaussian",
    "update-gaussian": "update_gaussian",
}


def _normalize_dp_mechanism(dp_mechanism: str) -> str:
    normalized_mechanism = str(dp_mechanism).strip().lower()
    return DP_MECHANISM_ALIASES.get(normalized_mechanism, normalized_mechanism)


def resolve_dp_config(manifest: dict) -> dict:
    """Small CLI-side DP resolver used only to locate the local LMS artifact."""

    dp_block = manifest.get("dp") or {}
    if dp_block:
        enabled = dp_block.get("enabled")
        mode = str(dp_block.get("mode", "disabled")).strip().lower()

        if enabled is False or (enabled is not True and mode in DISABLED_DP_MODES):
            return {"enabled": False, "mechanism": "none"}

        if enabled is True or mode not in DISABLED_DP_MODES:
            return {
                "enabled": True,
                "mechanism": _normalize_dp_mechanism(
                    dp_block.get("mechanism", "post_training_gaussian")
                ),
            }

    legacy_mode = str(manifest.get("dp_mode", "disabled")).strip().lower()
    if legacy_mode in DISABLED_DP_MODES:
        return {"enabled": False, "mechanism": "none"}

    return {
        "enabled": True,
        "mechanism": _normalize_dp_mechanism(
            manifest.get("dp_mechanism", "post_training_gaussian")
        ),
    }


def get_local_model_path(model_base_dir: Path, account_address: str, gi: int, dp_config: dict) -> Path:
    client_model_dir = model_base_dir / "models" / "clients" / account_address
    if dp_config["enabled"]:
        return client_model_dir / f"lm_{gi}_{dp_config['mechanism']}.pth"
    return client_model_dir / f"lm_{gi}.pth"


@app.command("create-client-dataset-dir")
def create_client_dataset_dir(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    model_base_dir = ctx.obj.get_model_base_dir(model_id)
    client_dataset_dir = model_base_dir / "dataset" / "clients" / account.address

    if client_dataset_dir.exists():
        console.print(f"[bold yellow]Client dataset directory already exists: [/bold yellow]{client_dataset_dir}")
    else:
        client_dataset_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[bold green]Created client dataset directory: [/bold green]{client_dataset_dir}")


@app.command("train-lms")
def train_lms(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
    gi: Optional[int] = typer.Option(None, "--gi", help="Global iteration to use"),
    packages_dir: Optional[str] = typer.Option(None, "--packages-dir", help="Packages directory"),
    no_cache: bool = typer.Option(False, "--no-cache", help="Do not use cached packages"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    runtime = ctx.obj.build_service_runtime(role="client", model_id=model_id)
    current_GI, current_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ctx.obj.validate_gi_ET_curr_GI(gi, current_GI)

    console.print("Training local model ...")

    genesis_model_ipfs_hash_raw = taskCoordinator_contract.functions.genesisModelIpfsHash().call()
    genesis_model_ipfs_hash = get_cid_from_bytes32(genesis_model_ipfs_hash_raw.hex())
    console.print("Using Genesis Model IPFS Hash: ", genesis_model_ipfs_hash)

    initial_model_ipfs_hash = None
    if current_GI > 1:
        (_, _, _, cid_raw) = taskCoordinator_contract.functions.getTier2Batch(current_GI - 1, 0).call()
        initial_model_ipfs_hash = get_cid_from_bytes32(cid_raw.hex()) if cid_raw and cid_raw != bytes(32) else None

    console.print("Using Latest Global Model IPFS Hash: ", initial_model_ipfs_hash)

    model_base_dir = ctx.obj.get_model_base_dir(model_id)
    manifest = runtime.require_manifest_key("train_client_model")
    model_manifest = runtime.require_manifest_key("ModelArchitecture")
    client_service_path = model_base_dir / Path(manifest["path"])
    model_service_path = model_base_dir / Path(model_manifest["path"])

    require_custom_manifest_service(manifest, "train_client_model")
    ctx.obj.ensure_file_exists(client_service_path, manifest["ipfs"], "client service")
    ctx.obj.ensure_file_exists(model_service_path, model_manifest["ipfs"], "model architecture service")

    client_requirements_cid = runtime.get_manifest_key("requirements.txt", {}).get("clients")
    requirements_path = get_worker_requirements_path(model_base_dir, "clients")
    packages_dir = Path(packages_dir) if packages_dir else None
    if client_requirements_cid:
        ctx.obj.ensure_file_exists(requirements_path, client_requirements_cid, "client requirements")
        try:
            ensure_worker_image(console)

            if not no_cache and packages_dir is None:
                packages_dir = ensure_worker_packages_installed(
                    requirements_path,
                    get_worker_packages_dir(effective_network, model_id),
                    console,
                )
        except RuntimeError as e:
            console.print(f"[bold red]{e}[/bold red]")
            raise typer.Exit(1)

    # Always refresh the genesis model file locally from IPFS so the client has
    # the base model object needed for deserialization and potential fallback.
    ctx.obj.ensure_file_exists(
        model_base_dir / "models" / "genesis_model.pth",
        genesis_model_ipfs_hash,
        "genesis model",
    )

    if initial_model_ipfs_hash:
        ctx.obj.ensure_file_exists(
            model_base_dir / "models" / f"gm_{current_GI-1}.pt",
            initial_model_ipfs_hash,
            "latest global model",
        )

    client_dataset_path = model_base_dir / "dataset" / "clients" / account.address / "data.pt"

    _confirm_or_exit("Have you placed your client dataset at" + str(client_dataset_path.resolve()) + "?", "Please ensure that the client dataset is placed at" + str(client_dataset_path.resolve()) + ".", console=console)

    if not client_dataset_path.exists():
        console.print(f"[bold red]Error:[/bold red] No client dataset found at {client_dataset_path}")
        console.print(f"[bold green]Creating client dataset directory at {client_dataset_path.parent}...[/bold green]")
        try:
            client_dataset_path.parent.mkdir(parents=True, exist_ok=True)
            console.print(f"[bold yellow]Please place your client dataset at {client_dataset_path}[/bold yellow]")
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(0)

    _confirm_or_exit(f"Creating a job to train a local model using containerized service. Are you sure that {client_dataset_path} is updated with your latest dataset? This may take a while. Do you want to continue?", "Aborted by user.", console=console)

    jobs_dir = model_base_dir / "jobs" / "clients" / account.address
    job_path, output_dir = write_worker_job(
        jobs_dir,
        f"client_lms_gi_{current_GI}",
        {
            "network": effective_network,
            "model_base_dir": "/din/model",
            "manifest_path": "/din/model/manifest.json",
            "role": "client",
            "service_path": manifest["path"],
            "function_name": "train_client_model",
            "args": [genesis_model_ipfs_hash, account.address, effective_network],
            "kwargs": {
                "initial_model_ipfs_hash": initial_model_ipfs_hash,
                "model_base_dir": "/din/model",
                "gi": current_GI,
            },
        },
    )
    console.print(f"Created client training job at {job_path}")

    _confirm_or_exit("Starting training a local model using containerized service. This may take a while. Do you want to continue?", "Aborted by user.", console=console)

    docker_result = run_worker_container(
        container_name=f"din-worker-client-model-{model_id}-gi-{current_GI}",
        model_base_dir=model_base_dir,
        job_path=job_path,
        output_dir=output_dir,
        writable_subdirs=[model_base_dir / "models" / "clients" / account.address],
        packages_dir=packages_dir,
    )

    if docker_result.stdout:
        console.print(docker_result.stdout)
    if docker_result.returncode != 0:
        if docker_result.stderr:
            console.print(docker_result.stderr)
        console.print("[bold red]Client worker container failed.[/bold red]")
        raise typer.Exit(docker_result.returncode)

    worker_result = read_worker_result(output_dir)
    if worker_result.get("status") != "ok":
        console.print(f"[bold red]Client worker failed:[/bold red] {worker_result.get('error')}")
        traceback = worker_result.get("traceback")
        if traceback:
            console.print(traceback)
        raise typer.Exit(1)

    container_model_path = Path(worker_result["result"])
    local_model_path = model_base_dir / container_model_path.relative_to("/din/model")
    console.print(f"[bold green]Local model generated at {local_model_path}[/bold green]")


        


@app.command("submit-lm")
def submit_lms(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
    gi: Optional[int] = typer.Option(None, "--gi", help="Global iteration to use"),
):

    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    runtime = ctx.obj.build_service_runtime(role="client", model_id=model_id)

    current_GI, current_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, current_GI)

    console.print("Submitting local model ...")

    model_base_dir = ctx.obj.get_model_base_dir(model_id)
    dp_config = resolve_dp_config(runtime.manifest)
    local_model_path = get_local_model_path(model_base_dir, account.address, ref_gi, dp_config)

    if not local_model_path.exists():
        console.print(f"[bold red]Error:[/bold red] No local model found at {local_model_path}")
        raise typer.Exit(1)

    if dp_config["enabled"]:
        console.print(f"DP mode is enabled with {dp_config['mechanism']} mechanism")
        console.print(f"Model file: {local_model_path}")
    else:
        console.print("DP mode is disabled")
        console.print(f"Model file: {local_model_path}")

    client_model_ipfs_hash = upload_to_ipfs(
        local_model_path,
        f"Client {account.address} model uploaded to IPFS",
    )

    try:
        client_model_ipfs_hash_bytes32 = Web3.to_bytes(hexstr=get_bytes32_from_cid(client_model_ipfs_hash))

        build_and_send_tx(
            ctx,
            taskAuditor_contract.functions.submitLocalModel(client_model_ipfs_hash_bytes32, ref_gi),
            f"Submitting local model with IPFS hash: {client_model_ipfs_hash} to task auditor",
            f"Local model submitted to task auditor with IPFS hash: {client_model_ipfs_hash}",
            f"Local model submission failed to task auditor with IPFS hash: {client_model_ipfs_hash}",
            exit_on_failure=False
        )
    except Exception as e:
        console.print(f"[bold red] Error submitting local model to task auditor: {e}[/bold red]")

@lms_app.command()
def show_models(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model index"),
    gi: int = typer.Option(None, "--gi", help="Global iteration to use"),
):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskAuditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, curr_GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)
    
    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    console.print(f"[bold green]Showing local model submissions for global iteration {ref_gi}![/bold green]")

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, curr_GIstate, "LMSstarted", "Its not time for model submissions yet.")
    
    has_submitted = taskAuditor_contract.functions.clientHasSubmitted(ref_gi, account.address).call()
    if has_submitted:
        console.print(f"[green]✓ Client {account.address} has submitted ![/green]")
    else:
        console.print(f"[red]Error:[/red] No local model submission found")
        raise typer.Exit(1)

    has_index = taskAuditor_contract.functions.clientSubmissionIndex(ref_gi, account.address).call()

    lm_submission = taskAuditor_contract.functions.lmSubmissions(ref_gi, has_index).call()
    
    console.print(f"[green]✓ Client {lm_submission[0]} submitted model {get_cid_from_bytes32(lm_submission[1].hex())}![/green]")

    console.print(f"[bold green]✓ Local model submissions shown![/bold green]")
