import secrets
from pathlib import Path
import time
from typing import List
import typer
from rich.table import Table
from web3 import Web3
from nacl.public import Box, PublicKey, PrivateKey
import nacl.encoding
from eth_abi.packed import encode_packed
from eth_account.messages import encode_defunct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from dincli.cli.utils import CONFIG_DIR, GIstateToStr, build_and_send_tx, ensure_batch_seed_locked, get_manifest_key, require_custom_manifest_service, resolve_manifest_path
from dincli.services.cid_utils import get_bytes32_from_cid, get_cid_from_bytes32

auditor_batches_app = typer.Typer(help="Auditor Batches commands")

_TA_FLAG_ALREADY_SET_SELECTOR = Web3.keccak(text="TA_FlagAlreadySet()").hex()[:8].lower()


def _is_flag_already_set_revert(exc: Exception) -> bool:
    """Best-effort detection of DINTaskAuditor's TA_FlagAlreadySet() custom error.

    setTestDataAssignedFlag has no getter for Is_testdataCIDs_Assigned, so
    inspecting the revert data is the only way to tell "already set" (safe to
    skip) apart from a real failure (should exit non-zero).
    """
    data = getattr(exc, "data", None)
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, str):
        return False
    data_hex = data[2:] if data.startswith("0x") else data
    return data_hex.lower().startswith(_TA_FLAG_ALREADY_SET_SELECTOR)

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

    # issue #156 H-2: createAuditorsBatches now requires an ungrindable,
    # future-block-anchored seed to already be locked. Lock it here (or
    # skip if someone else already has) before attempting the real call.
    ensure_batch_seed_locked(
        ctx, taskCoordinator_contract, ref_gi,
        seed_getter="auditSeed", seed_block_getter="auditSeedBlock",
        lock_fn="lockAuditSeed", label="auditor-batch",
    )

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
    batch: List[int] = typer.Option(
        [],
        "--batch",
        help=(
            "Retry assignAuditTestDataset for only this batch ID (repeatable, e.g. "
            "--batch 2 --batch 5). Combine with --submit to retry batches that failed "
            "on a previous run; the test-dataset-assigned flag is then (re-)attempted "
            "for all batches as usual. If omitted, --submit sends every batch."
        ),
    ),
):
    """Create per-batch encrypted audit test datasets and optionally submit them on-chain.

    Safe to re-run with --submit: if any batch's assignAuditTestDataset tx fails,
    the failed batch IDs are printed and the command exits 1 without touching the
    test-dataset-assigned flag. Retry just those batches with `--batch <id>`
    (repeatable). The flag itself is one-shot on-chain; if it's already set,
    re-running --submit (with or without --batch) detects that and skips it.
    """
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)
    
    taskCoordinator_contract, taskauditor_contract = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id), ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    
    curr_GI, GIstate = ctx.obj.get_current_gi_and_state(taskCoordinator_contract)

    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    # Richer GI states (task_061026_21, not always present -- see git history
    # around issues #243/#272/#273/#287) advance GIstate to
    # AuditTestDataAssigned once setTestDataAssignedFlag succeeds on-chain.
    # When that state exists and is current, the flag is already set and
    # there is nothing left for this command to do -- treat it the same way
    # as the informational "already set" case below, rather than falling
    # through to the exact-match gate (which would otherwise reject a safe
    # re-run with a generic "wrong state" error, contradicting the
    # re-run-safety documented on this command).
    curr_GIstate_str = GIstate if isinstance(GIstate, str) else GIstateToStr(GIstate)
    if curr_GIstate_str == "AuditTestDataAssigned":
        console.print(
            "[yellow]Test dataset already assigned and the flag already set for this "
            "GI (GIstate is AuditTestDataAssigned) — nothing further to do.[/yellow]"
        )
        return
    if curr_GIstate_str != "AuditorsBatchesCreated":
        console.print(
            f"[bold red]✗ Can not create test dataset at this time. "
            f"Current state: {curr_GIstate_str} [/bold red]"
        )
        raise typer.Exit(1)

    console.print(f"[bold green]Creating test dataset![/bold green]")

    audtor_batch_count = taskauditor_contract.functions.AuditorsBatchCount(ref_gi).call()

    model_base_path = ctx.obj.get_model_base_dir(model_id)
    manifest = get_manifest_key(effective_network, "create_audit_testDataCIDs", model_id)
    modelowner_service_path = resolve_manifest_path(model_base_path, manifest["path"], what="create_audit_testDataCIDs path")

    require_custom_manifest_service(manifest, "create_audit_testDataCIDs")
    ctx.obj.ensure_file_exists(modelowner_service_path, manifest["ipfs"], "model owner service", base_dir=model_base_path)
    fn = ctx.obj.load_custom_fn(modelowner_service_path, "create_audit_testDataCIDs", base_dir=model_base_path)

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

        batch_ids_to_process = list(batch) if batch else list(range(audtor_batch_count))

        failed_batch_ids = []
        try:
            for batch_id in batch_ids_to_process:
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

                # K encrypted to each auditor's registered X25519 pubkey via authenticated Box.
                # Build address-keyed first, then reorder to the authoritative on-chain ordering
                # so a future RPC or contract change that returns auditors in a different order
                # cannot silently mismatch keys to recipients (BL-13, closes #115).
                encrypted_key_by_addr = {}
                for auditor_addr in batch_auditors:
                    pubkey_bytes = stake_contract.functions.getEncryptionKey(auditor_addr).call()
                    encrypted_key_by_addr[auditor_addr.lower()] = (
                        Box(owner_privkey, PublicKey(bytes(pubkey_bytes))).encrypt(K)
                    )
                encrypted_keys = [encrypted_key_by_addr[addr.lower()] for addr in batch_auditors]

                # commitment = keccak256(abi.encodePacked(gi, batchId, keccak256(K), plaintext_keccak))
                keccak_K = bytes(Web3.keccak(K))
                commitment = bytes(Web3.keccak(
                    encode_packed(
                        ["uint256", "uint256", "bytes32", "bytes32"],
                        [ref_gi, batch_id, keccak_K, bytes(plaintext_keccak)],
                    )
                ))

                time.sleep(5)
                tx_receipt = build_and_send_tx(
                    ctx,
                    taskauditor_contract.functions.assignAuditTestDataset(
                        curr_GI, batch_id, encrypted_cid, encrypted_keys, commitment
                    ),
                    f"Assigning test dataset for auditor batch {batch_id}",
                    f"Test dataset assigned for auditor batch : {batch_id}",
                    f"Failed to assign test dataset for auditor batch : {batch_id}",
                    exit_on_failure=False,
                )
                if tx_receipt is None:
                    failed_batch_ids.append(batch_id)
        except Exception as e:
            console.print(f"[red]Error:[/red] Failed to assign test dataset for auditor batches: {e}")
            raise typer.Exit(1)

        if failed_batch_ids:
            retry_flags = " ".join(f"--batch {b}" for b in failed_batch_ids)
            console.print(
                f"[bold red]✗ Failed to assign test dataset for auditor batch(es): "
                f"{', '.join(str(b) for b in failed_batch_ids)}[/bold red]"
            )
            console.print(
                f"[yellow]Skipping the test-dataset-assigned flag. Retry just the failed "
                f"batch(es) with: dincli model-owner auditor-batches create-testdataset "
                f"{model_id} --submit {retry_flags}[/yellow]"
            )
            raise typer.Exit(1)

        time.sleep(5)
        flag_already_set = False
        try:
            taskCoordinator_contract.functions.setTestDataAssignedFlag(curr_GI, True).call({"from": account.address})
        except Exception as e:
            if _is_flag_already_set_revert(e):
                flag_already_set = True
            else:
                console.print(f"[bold red]✗ Failed to set test dataset assigned flag: {e}[/bold red]")
                raise typer.Exit(1)

        if flag_already_set:
            console.print("[yellow]Test dataset assigned flag was already set for this GI — skipping.[/yellow]")
        else:
            flag_receipt = build_and_send_tx(
                ctx,
                taskCoordinator_contract.functions.setTestDataAssignedFlag(curr_GI, True),
                "Setting test dataset assigned flag",
                "Test dataset assigned for auditor batches",
                "Failed to set test dataset assigned flag",
                exit_on_failure=False,
            )
            if flag_receipt is None:
                console.print("[bold red]✗ Failed to set test dataset assigned flag.[/bold red]")
                raise typer.Exit(1)
