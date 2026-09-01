import secrets
from pathlib import Path
import time
import typer
from rich.table import Table
from web3 import Web3
from nacl.public import Box, PublicKey, PrivateKey
import nacl.encoding
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dincli.cli.utils import CACHE_DIR, CONFIG_DIR, build_and_send_tx, get_manifest_key, require_custom_manifest_service
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32

auditor_batches_app = typer.Typer(help="Auditor Batches commands")

@auditor_batches_app.command()
def create(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    taskCoordinator_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "LMSclosed", "Can not create auditor batches at this time")
    
    console.print(f"[bold green]Creating auditor batches [/bold green]")

    try:
        tx_receipt = build_and_send_tx(
            ctx,
            taskCoordinator_contract.functions.createAuditorsBatches(ref_gi),
            "Creating auditor batches",
            "Auditor batches created!",
            "Auditor batches creation failed",
            exit_on_failure=False
        )
        console.print(f"[dim]Auditor batches created tx:[/dim] {tx_receipt.transactionHash.hex()}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

@auditor_batches_app.command()
def show(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
):
    
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskauditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_LTE_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_LTE_given_GIstate(ref_gi, curr_GI, GIstate, "AuditorsBatchesCreated", "Can not show auditor batches at this time")

    
    console.print(f"[bold green]Showing auditor batches for global iteration {ref_gi}![/bold green]")

    try:
        audtor_batch_count = taskauditor_contract.functions.AuditorsBatchCount(ref_gi).call()

        console.print(f"[bold green]Auditor batches count:[/bold green] {audtor_batch_count}")

        raw_audit_batches = []
        processed_audit_batches = []
    
        for i in range(audtor_batch_count):
            raw_audit_batches.append(taskauditor_contract.functions.getAuditorsBatch(ref_gi, i).call())

        for batch in raw_audit_batches:
            batch_id, auditors, model_indexes, test_cid_raw = batch
            # testDataCID is now bytes (encryptedCID blob), not a raw bytes32 CID pointer.
            # Show length only — the plaintext rawCID is not directly readable from the encrypted blob.
            test_cid = f"<encrypted, {len(test_cid_raw)} bytes>" if test_cid_raw else "None"
            processed_audit_batches.append({"batch_id": batch_id, "auditors": auditors, "model_indexes": model_indexes, "test_cid": test_cid})
            
        if not processed_audit_batches:
            console.print("[yellow]No auditor batches found.[/yellow]")
        else:
            table = Table(title=f"Auditor Batches for GI {curr_GI}", show_header=True, header_style="bold magenta")
            table.add_column("Batch ID", style="dim")
            table.add_column("Auditors", overflow="fold")
            table.add_column("Model Indexes", overflow="fold")
            table.add_column("Test CID")

            for batch in processed_audit_batches:
                table.add_row(
                    str(batch["batch_id"]),
                    ", ".join(batch["auditors"]) if batch["auditors"] else "—",
                    ", ".join(map(str, batch["model_indexes"])) if batch["model_indexes"] else "—",
                    batch["test_cid"] if batch["test_cid"] != "None" else "—"
                )
            console.print(table)
            console.print("[green]✓ Auditor batches shown![/green]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

@auditor_batches_app.command("create-testdataset")
def create_testdataset(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(None, "--gi", help="Global iteration number"),
    submit: bool = typer.Option(False, "--submit", help="Submit test dataset to TaskCoordinator"),
    test_data_path: str = typer.Option(None, "--test-data-path", help="Path to test dataset"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskauditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    ctx.obj.validate_GIstate_ET_given_GIstate(GIstate, "AuditorsBatchesCreated", "Can not create test dataset at this time")

    console.print(f"[bold green]Creating test dataset![/bold green]")

    audtor_batch_count = taskauditor_contract.functions.AuditorsBatchCount(ref_gi).call()

    model_base_path = Path(CACHE_DIR) / effective_network /  f"model_{model_id}"
    manifest = get_manifest_key(effective_network, "create_audit_testDataCIDs", model_id)
    modelowner_service_path = model_base_path / Path(manifest["path"])

    require_custom_manifest_service(manifest, "create_audit_testDataCIDs")
    ctx.obj.ensure_file_exists(modelowner_service_path, manifest["ipfs"], "model owner service")
    fn = ctx.obj.load_custom_fn(modelowner_service_path, "create_audit_testDataCIDs")

    if test_data_path is None:
        test_data_path = model_base_path / "dataset" / "test" / "test_dataset.pt"
    else:
        test_data_path = Path(test_data_path)

    if not test_data_path.exists():
        raise FileNotFoundError(
            f"Test dataset not found at {test_data_path.resolve()}"
        )
    
    audit_testDataCIDs = fn(audtor_batch_count, curr_GI, str(model_base_path), str(test_data_path))
    
    console.print("audit_testDataCIDs", audit_testDataCIDs)
    
    console.print(f"[bold green] ✓ Created test subdatasets![/bold green]")

    if submit:

        console.print(f"[bold green]Assigning test dataset![/bold green]")

        # Load (or generate) the owner's dedicated X25519 private key.
        owner_key_path = Path(CONFIG_DIR) / "owner_x25519.key"
        if not owner_key_path.exists():
            new_key = PrivateKey.generate()
            owner_key_path.write_text(
                new_key.encode(encoder=nacl.encoding.HexEncoder).decode()
            )
            console.print(f"[yellow]Generated owner X25519 key → {owner_key_path}[/yellow]")
        owner_privkey = PrivateKey(bytes.fromhex(owner_key_path.read_text().strip()))

        # Write owner's X25519 pubkey into the local manifest cache so auditors
        # can read it via get_manifest_key("owner_encryption_pubkey"). The owner
        # must re-upload the manifest and update the on-chain CID for auditors on
        # other machines to receive it (standard manifest update workflow).
        import json as _json
        from dincli.cli.utils import get_manifest_path
        owner_pubkey_hex = bytes(owner_privkey.public_key).hex()
        _manifest_path = get_manifest_path(effective_network, model_id=model_id)
        if _manifest_path.exists():
            _manifest = _json.loads(_manifest_path.read_text())
            if _manifest.get("owner_encryption_pubkey") != owner_pubkey_hex:
                _manifest["owner_encryption_pubkey"] = owner_pubkey_hex
                _manifest_path.write_text(_json.dumps(_manifest, indent=2))
                console.print(f"[dim]owner_encryption_pubkey written to manifest — re-upload manifest to distribute to auditors[/dim]")

        stake_contract = ctx.obj.get_deployed_din_stake_contract(verbose=False)

        try:
            for batch_id in range(audtor_batch_count):
                batch_info = audit_testDataCIDs[batch_id]
                raw_cid = batch_info["raw_cid"]
                K = batch_info["K"]
                plaintext_keccak = batch_info["plaintext_keccak"]

                # encryptedCID = AES-256-GCM(K, rawCID_bytes || eth_sign(ownerSK, rawCID_bytes))
                raw_cid_bytes = Web3.to_bytes(hexstr=get_bytes32_from_cid(raw_cid))
                sig = account.sign_message(encode_defunct(raw_cid_bytes)).signature
                nonce = secrets.token_bytes(12)
                encrypted_cid = nonce + AESGCM(K).encrypt(nonce, raw_cid_bytes + sig, None)

                _, batch_auditors, _, _ = taskauditor_contract.functions.getAuditorsBatch(ref_gi, batch_id).call()

                # K encrypted to each auditor's registered X25519 pubkey via authenticated Box
                encrypted_keys = []
                for auditor_addr in batch_auditors:
                    pubkey_bytes = stake_contract.functions.getEncryptionKey(auditor_addr).call()
                    encrypted_keys.append(
                        Box(owner_privkey, PublicKey(bytes(pubkey_bytes))).encrypt(K)
                    )

                # commitment = keccak256(abi.encodePacked(gi, batchId, keccak256(K), plaintext_keccak))
                keccak_K = bytes(Web3.keccak(K))
                commitment = bytes(Web3.keccak(
                    encode_packed(
                        ["uint256", "uint256", "bytes32", "bytes32"],
                        [ref_gi, batch_id, keccak_K, bytes(plaintext_keccak)],
                    )
                ))

                time.sleep(5)
                build_and_send_tx(
                    ctx,
                    taskauditor_contract.functions.assignAuditTestDataset(
                        curr_GI, batch_id, encrypted_cid, encrypted_keys, commitment
                    ),
                    f"Assigning test dataset for auditor batch {batch_id}",
                    f"Test dataset assigned for auditor batch : {batch_id}",
                    f"Failed to assign test dataset for auditor batch : {batch_id}",
                    exit_on_failure=False,
                )

            time.sleep(5)
            build_and_send_tx(
                ctx,
                taskCoordinator_contract.functions.setTestDataAssignedFlag(curr_GI, True),
                "Setting test dataset assigned flag",
                "Test dataset assigned for auditor batches",
                "Failed to set test dataset assigned flag",
                exit_on_failure=False,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to assign test dataset for auditor batches: {e}")
            raise typer.Exit(1)
            