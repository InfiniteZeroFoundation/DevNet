import time
from pathlib import Path
from typing import Optional

import typer

from dincli.cli.modelownerd.auditor_batches import (
    _auditors_missing_encryption_key, _encrypt_batch_testdata,
    _load_owner_x25519_key, _load_testdata_secret, _save_testdata_secret)
from dincli.cli.utils import (build_and_send_tx, get_manifest_key,
                              parse_tier_kind, require_custom_manifest_service,
                              resolve_manifest_path)

disputes_app = typer.Typer(help="Answer and settle test-data and aggregation disputes")

ZERO_BYTES32 = b"\x00" * 32


# ── Test-data disputes (DINTaskAuditor) ─────────────────────────────────────

def _active_testdata_dispute(console, task_auditor, gi: int, batch_id: int):
    # testDataDisputes getter: (disputer, bond, expiresAtBlock, active, pendingReassignment)
    d = task_auditor.functions.testDataDisputes(gi, batch_id).call()
    if not d[3]:
        console.print(f"[bold red]✗ No active test-data dispute for GI {gi} batch {batch_id}.[/bold red]")
        raise typer.Exit(1)
    return d


@disputes_app.command("resolve-test-data", help="Answer a test-data dispute by revealing the batch's K and plaintext hash (owner only)")
def resolve_test_data(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI of the disputed batch"),
    batch_id: int = typer.Option(..., "--batch", help="Disputed auditor batch ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    d = _active_testdata_dispute(console, task_auditor, gi, batch_id)
    if w3.eth.block_number > d[2]:
        console.print(f"[bold red]✗ The answer window closed at block {d[2]}; the dispute is upheld. Close it with `close-expired`.[/bold red]")
        raise typer.Exit(1)

    secret = _load_testdata_secret(ctx.obj.get_model_base_dir(model_id), gi, batch_id)
    if secret is None:
        console.print(f"[bold red]✗ No saved K for GI {gi} batch {batch_id}. It is written by `auditor-batches create-testdataset --submit` on this machine.[/bold red]")
        raise typer.Exit(1)
    K, plaintext_keccak = secret

    build_and_send_tx(
        ctx,
        task_auditor.functions.resolveTestDataDispute(gi, batch_id, K, plaintext_keccak),
        f"Answering the test-data dispute on GI {gi} batch {batch_id}",
        "Dispute answered.",
        "Could not answer the dispute",
    )

    d = task_auditor.functions.testDataDisputes(gi, batch_id).call()
    if d[4]:
        console.print(f"[yellow]The reveal didn't match the commitment, so the dispute was upheld. Reassign the batch with: dincli model-owner disputes reassign-test-data {model_id} --gi {gi} --batch {batch_id}[/yellow]")
    else:
        console.print("[bold green]The reveal matched the commitment; the disputer's bond is forfeited.[/bold green]")


@disputes_app.command("close-expired", help="Close a test-data dispute the owner didn't answer in time; it is upheld (permissionless)")
def close_expired(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI of the disputed batch"),
    batch_id: int = typer.Option(..., "--batch", help="Disputed auditor batch ID"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)

    d = _active_testdata_dispute(console, task_auditor, gi, batch_id)
    if w3.eth.block_number <= d[2]:
        console.print(f"[bold red]✗ The answer window is open until block {d[2]} (now {w3.eth.block_number}).[/bold red]")
        raise typer.Exit(1)

    build_and_send_tx(
        ctx,
        task_auditor.functions.closeExpiredDispute(gi, batch_id),
        f"Closing the expired test-data dispute on GI {gi} batch {batch_id}",
        "Dispute closed and upheld; the batch now needs reassignment.",
        "Could not close the dispute",
    )


@disputes_app.command("reassign-test-data", help="Assign fresh test data to a batch after an upheld test-data dispute (owner only)")
def reassign_test_data(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: Optional[int] = typer.Option(None, "--gi", help="GI of the batch (must be the current GI)"),
    batch_id: int = typer.Option(..., "--batch", help="Auditor batch ID to reassign"),
    test_data_path: str = typer.Option(None, "--test-data-path", help="Path to test dataset"),
):
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)
    task_auditor = ctx.obj.get_deployed_din_task_auditor_contract(True, model_id)
    stake_contract = ctx.obj.get_deployed_din_stake_contract(verbose=False)

    curr_GI, _ = ctx.obj.get_current_gi_and_state(task_coordinator)
    ref_gi = ctx.obj.validate_gi_ET_curr_GI(gi, curr_GI)

    if not task_auditor.functions.testDataDisputes(ref_gi, batch_id).call()[4]:
        console.print(f"[bold red]✗ GI {ref_gi} batch {batch_id} isn't pending reassignment.[/bold red]")
        raise typer.Exit(1)

    batch_auditors = task_auditor.functions.getAuditorsBatch(ref_gi, batch_id).call()[1]
    missing_keys = _auditors_missing_encryption_key(stake_contract, batch_auditors)
    if missing_keys:
        console.print(f"[bold red]✗ Batch auditors without an encryption key: {', '.join(missing_keys)}[/bold red]")
        raise typer.Exit(1)

    model_base_path = ctx.obj.get_model_base_dir(model_id)
    manifest = get_manifest_key(effective_network, "create_audit_testDataCIDs", model_id)
    require_custom_manifest_service(manifest, "create_audit_testDataCIDs")
    service_path = resolve_manifest_path(model_base_path, manifest["path"], what="create_audit_testDataCIDs path")
    ctx.obj.ensure_file_exists(service_path, manifest["ipfs"], "model owner service", base_dir=model_base_path)
    fn = ctx.obj.load_custom_fn(service_path, "create_audit_testDataCIDs", base_dir=model_base_path)

    test_data_path = Path(test_data_path) if test_data_path else model_base_path / "dataset" / "test" / "test_dataset.pt"
    if not test_data_path.exists():
        raise FileNotFoundError(f"Test dataset not found at {test_data_path.resolve()}")

    # The service builds every batch's data with a fresh K each call; only
    # this batch's entry is used.
    batch_count = task_auditor.functions.AuditorsBatchCount(ref_gi).call()
    batch_info = dict(fn(batch_count, ref_gi, str(model_base_path), str(test_data_path))[batch_id], batch_id=batch_id)

    owner_privkey = _load_owner_x25519_key(console)
    encrypted_cid, encrypted_keys, commitment = _encrypt_batch_testdata(
        account, stake_contract, owner_privkey, ref_gi, batch_auditors, batch_info,
    )
    _save_testdata_secret(model_base_path, ref_gi, batch_id, batch_info["K"], batch_info["plaintext_keccak"])

    build_and_send_tx(
        ctx,
        task_auditor.functions.reassignAuditTestDataset(ref_gi, batch_id, encrypted_cid, encrypted_keys, commitment),
        f"Reassigning test data for GI {ref_gi} batch {batch_id}",
        f"Test data reassigned for batch {batch_id}.",
        f"Could not reassign test data for batch {batch_id}",
    )


# ── Aggregation disputes (DINTaskCoordinator, S4) ───────────────────────────

def _get_dispute(console, task_coordinator, gi: int, tier_kind: int, batch_id: int):
    # disputes getter: (challenger, bond, openedAt, resolutionDeadline,
    # seedBlock, resolved, upheld, finalized, seed)
    d = task_coordinator.functions.disputes(gi, tier_kind, batch_id).call()
    if d[0] == "0x0000000000000000000000000000000000000000":
        console.print(f"[bold red]✗ No dispute on GI {gi} {('T1', 'T2')[tier_kind]} batch {batch_id}.[/bold red]")
        raise typer.Exit(1)
    return d


def _lock_dispute_seed(ctx, task_coordinator, gi: int, tier_kind: int, batch_id: int, poll_interval: float = 2.0):
    """resolveDispute(upheld=true) needs the dispute's future-block seed
    locked first. lockDisputeSeed is permissionless and may re-anchor once
    more than 256 blocks have passed, so re-check after every attempt."""
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console()
    while True:
        d = task_coordinator.functions.disputes(gi, tier_kind, batch_id).call()
        if d[8] != ZERO_BYTES32:
            return
        seed_block = d[4]
        if w3.eth.block_number <= seed_block:
            console.print(f"[cyan]Waiting for block {seed_block} to lock the dispute seed (current: {w3.eth.block_number})...[/cyan]")
            while w3.eth.block_number <= seed_block:
                time.sleep(poll_interval)
        receipt = build_and_send_tx(
            ctx,
            task_coordinator.functions.lockDisputeSeed(gi, tier_kind, batch_id),
            "Locking the dispute seed",
            "Dispute seed lock sent.",
            "Could not lock the dispute seed",
            exit_on_failure=False,
        )
        # A failed lock is fine only if someone else locked it meanwhile;
        # the loop's re-check returns in that case.
        if receipt is None and task_coordinator.functions.disputes(gi, tier_kind, batch_id).call()[8] == ZERO_BYTES32:
            raise typer.Exit(1)


@disputes_app.command("resolve-aggregation", help="Uphold or reject an aggregation dispute (owner only). Upholding assigns a fresh aggregator subgroup")
def resolve_aggregation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI of the disputed batch"),
    tier: str = typer.Option(..., "--tier", help="t1 or t2"),
    batch_id: int = typer.Option(..., "--batch", help="Disputed batch ID"),
    upheld: bool = typer.Option(..., "--upheld/--rejected", help="Uphold the dispute (fresh subgroup recomputes) or reject it (bond forfeited)"),
):
    tier_kind = parse_tier_kind(tier)
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    d = _get_dispute(console, task_coordinator, gi, tier_kind, batch_id)
    if d[5]:
        console.print("[bold red]✗ This dispute is already resolved.[/bold red]")
        raise typer.Exit(1)

    if upheld:
        _lock_dispute_seed(ctx, task_coordinator, gi, tier_kind, batch_id)

    build_and_send_tx(
        ctx,
        task_coordinator.functions.resolveDispute(gi, tier_kind, batch_id, upheld),
        f"{'Upholding' if upheld else 'Rejecting'} the dispute",
        f"Dispute {'upheld: a fresh subgroup must recompute before the resolution deadline' if upheld else 'rejected: bond forfeited'}.",
        "Could not resolve the dispute",
    )


@disputes_app.command("settle-recomputation", help="Final verdict on an upheld aggregation dispute after the fresh subgroup recomputed (owner only)")
def settle_recomputation(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI of the disputed batch"),
    tier: str = typer.Option(..., "--tier", help="t1 or t2"),
    batch_id: int = typer.Option(..., "--batch", help="Disputed batch ID"),
    confirmed: bool = typer.Option(..., "--confirmed/--dismissed", help="Recomputation confirmed the original CID was wrong (slash its aggregators) or matched it (bond forfeited)"),
):
    tier_kind = parse_tier_kind(tier)
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    d = _get_dispute(console, task_coordinator, gi, tier_kind, batch_id)
    if not (d[5] and d[6]) or d[7]:
        console.print("[bold red]✗ This dispute isn't awaiting recomputation (it must be upheld and not yet finalized).[/bold red]")
        raise typer.Exit(1)

    build_and_send_tx(
        ctx,
        task_coordinator.functions.settleRecomputation(gi, tier_kind, batch_id, confirmed),
        "Settling the recomputation",
        f"Recomputation settled ({'original aggregators slashed, bond claimable by the challenger' if confirmed else 'bond forfeited'}).",
        "Could not settle the recomputation",
    )


@disputes_app.command("expire", help="Time out an upheld aggregation dispute whose fresh subgroup didn't recompute (permissionless)")
def expire(
    ctx: typer.Context,
    model_id: int = typer.Argument(..., help="Model ID"),
    gi: int = typer.Option(..., "--gi", help="GI of the disputed batch"),
    tier: str = typer.Option(..., "--tier", help="t1 or t2"),
    batch_id: int = typer.Option(..., "--batch", help="Disputed batch ID"),
):
    tier_kind = parse_tier_kind(tier)
    effective_network, w3, account, console = ctx.obj.get_en_w3_account_console(model_id)

    task_coordinator = ctx.obj.get_deployed_din_task_coordinator_contract(True, model_id)

    d = _get_dispute(console, task_coordinator, gi, tier_kind, batch_id)
    if not (d[5] and d[6]) or d[7]:
        console.print("[bold red]✗ This dispute isn't awaiting recomputation (it must be upheld and not yet finalized).[/bold red]")
        raise typer.Exit(1)
    now = w3.eth.get_block("latest")["timestamp"]
    if now <= d[3]:
        console.print(f"[bold red]✗ The resolution window is still open (deadline {d[3]}, now {now}).[/bold red]")
        raise typer.Exit(1)

    build_and_send_tx(
        ctx,
        task_coordinator.functions.expireDispute(gi, tier_kind, batch_id),
        "Expiring the dispute",
        "Dispute expired: the fresh subgroup is slashed and the challenger's bond is claimable.",
        "Could not expire the dispute",
    )
