"""Tests for ensure_batch_seed_locked (issue #156 H-2, batch-assignment seed).

Covers the dincli-side counterpart of the ungrindable future-block-seed +
permissionless-lock pattern in DINTaskCoordinator: the CLI must wait for the
anchored seed block, then lock the seed itself only if nobody else already
has, and must not proceed with a zero seed if the lock call re-anchors
instead of setting it (>256 blocks elapsed since anchor).
"""
from unittest.mock import MagicMock, patch

import pytest
import typer

from dincli.cli.utils import (GIstatestrToIndex, ensure_batch_seed_locked,
                              lock_batch_seed_if_pending)

ZERO_SEED = b"\x00" * 32
LOCKED_SEED = b"\x11" * 32
GI = 1


class _Call:
    """Mimics a web3 contract function's bound call: `.call()` returns
    whatever the current state is at call time (not at construction time),
    matching real web3.py semantics where state can change between calls."""

    def __init__(self, read_fn):
        self._read_fn = read_fn

    def call(self):
        return self._read_fn()


def _make_contract(state):
    """state: dict with keys 'seed', 'seed_block', 'lock_calls' (list of gi)."""

    def functions_getattr(name):
        if name == "auditSeed":
            return lambda gi: _Call(lambda: state["seed"])
        if name == "auditSeedBlock":
            return lambda gi: _Call(lambda: state["seed_block"])
        if name == "lockAuditSeed":
            def _lock(gi):
                state["lock_calls"].append(gi)
                return MagicMock(name="lockAuditSeed_tx")
            return _lock
        raise AttributeError(name)

    class _Functions:
        def __getattr__(self, name):
            return functions_getattr(name)

    contract = MagicMock()
    contract.functions = _Functions()
    return contract


def _make_ctx(w3):
    ctx = MagicMock()
    console = MagicMock()
    ctx.obj.get_en_w3_account_console.return_value = ("local", w3, MagicMock(), console)
    return ctx, console


def _make_w3(block_number):
    w3 = MagicMock()
    w3.eth.block_number = block_number
    return w3


def _call(ctx, contract, poll_interval=0.0):
    ensure_batch_seed_locked(
        ctx, contract, GI,
        seed_getter="auditSeed",
        seed_block_getter="auditSeedBlock",
        lock_fn="lockAuditSeed",
        label="auditor-batch",
        poll_interval=poll_interval,
    )


@patch("dincli.cli.utils.build_and_send_tx")
def test_already_locked_skips_wait_and_lock(mock_build_and_send_tx):
    state = {"seed": LOCKED_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    ctx, console = _make_ctx(_make_w3(50))

    _call(ctx, contract)

    mock_build_and_send_tx.assert_not_called()
    assert state["lock_calls"] == []


@patch("dincli.cli.utils.build_and_send_tx")
def test_waits_for_seed_block_then_locks(mock_build_and_send_tx):
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(50)
    ctx, console = _make_ctx(w3)

    def _tick(_seconds):
        w3.eth.block_number += 60

    def _lock_side_effect(*args, **kwargs):
        state["seed"] = LOCKED_SEED
        return MagicMock()

    mock_build_and_send_tx.side_effect = _lock_side_effect

    with patch("dincli.cli.utils.time.sleep", side_effect=_tick):
        _call(ctx, contract)

    assert w3.eth.block_number > 100
    mock_build_and_send_tx.assert_called_once()
    assert state["lock_calls"] == [GI]
    assert state["seed"] == LOCKED_SEED


@patch("dincli.cli.utils.build_and_send_tx")
def test_locked_by_someone_else_while_waiting_skips_lock(mock_build_and_send_tx):
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(50)
    ctx, console = _make_ctx(w3)

    def _tick(_seconds):
        w3.eth.block_number += 60
        state["seed"] = LOCKED_SEED

    with patch("dincli.cli.utils.time.sleep", side_effect=_tick):
        _call(ctx, contract)

    mock_build_and_send_tx.assert_not_called()
    assert state["lock_calls"] == []


@patch("dincli.cli.utils.build_and_send_tx")
def test_reanchor_during_lock_recurses_instead_of_proceeding_with_zero_seed(mock_build_and_send_tx):
    # Seed block already mined; first lock attempt re-anchors (seed stays
    # zero, seed_block moves forward) rather than setting the seed --
    # e.g. because >256 blocks elapsed since the original anchor.
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(150)
    ctx, console = _make_ctx(w3)

    call_count = {"n": 0}

    def _lock_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            state["seed_block"] = 200  # re-anchored, seed left at zero
        else:
            state["seed"] = LOCKED_SEED
        return MagicMock()

    mock_build_and_send_tx.side_effect = _lock_side_effect

    def _tick(_seconds):
        w3.eth.block_number += 60

    with patch("dincli.cli.utils.time.sleep", side_effect=_tick):
        _call(ctx, contract)

    assert mock_build_and_send_tx.call_count == 2
    assert state["lock_calls"] == [GI, GI]
    assert state["seed"] == LOCKED_SEED


@patch("dincli.cli.utils.build_and_send_tx")
def test_lock_call_race_does_not_abort_once_seed_is_set(mock_build_and_send_tx):
    """PR #191 review, finding No. 5: if someone else's lock lands between
    our re-check and our own lock tx, our tx reverts with
    TC_...SeedAlreadyLocked. That must not abort the whole create command --
    the seed is locked either way, so the lock call passes
    exit_on_failure=False and re-checks afterward instead of propagating."""
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(150)
    ctx, console = _make_ctx(w3)

    def _lock_side_effect(*args, **kwargs):
        # Our own tx reverted (build_and_send_tx already caught it and
        # returned None, since exit_on_failure=False) while a concurrent
        # caller's lock tx landed first.
        state["seed"] = LOCKED_SEED
        return None

    mock_build_and_send_tx.side_effect = _lock_side_effect

    _call(ctx, contract)

    mock_build_and_send_tx.assert_called_once()
    _, kwargs = mock_build_and_send_tx.call_args
    assert kwargs.get("exit_on_failure") is False
    assert state["seed"] == LOCKED_SEED


@patch("dincli.cli.utils.build_and_send_tx")
def test_persistent_lock_failure_exits_after_one_attempt(mock_build_and_send_tx):
    """PR #191 review, finding No. 6: a lock call that keeps failing (no gas
    funds, RPC down, any non-race revert) with the seed block already mined
    and unchanged must not be retried -- the retry would fail the same way
    at once, recursing ~1,000 deep into a RecursionError. Exactly one
    attempt, then typer.Exit."""
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(150)
    ctx, console = _make_ctx(w3)

    def _lock_side_effect(*args, exit_on_failure=True, **kwargs):
        # Follows build_and_send_tx's real failure branch; the seed and
        # seed block are both left untouched.
        if exit_on_failure:
            raise typer.Exit(1)
        return None

    mock_build_and_send_tx.side_effect = _lock_side_effect

    with pytest.raises(typer.Exit):
        _call(ctx, contract)

    mock_build_and_send_tx.assert_called_once()
    assert state["lock_calls"] == [GI]
    assert state["seed"] == ZERO_SEED



@pytest.mark.parametrize("failure", ["mined_revert", "receipt_timeout"])
@patch("dincli.cli.utils.print_tx_info")
def test_persistent_lock_failure_after_send_spends_gas_once(_mock_print_tx_info, failure):
    """PR #191 review, No. 6 gas-spending variant: estimation succeeds, the
    lock tx is actually sent, then mines as a revert or its receipt times
    out. Runs the real build_and_send_tx (only w3 is faked) -- exactly one
    tx must be sent, then typer.Exit, rather than one paid tx per retry."""
    state = {"seed": ZERO_SEED, "seed_block": 100, "lock_calls": []}
    contract = _make_contract(state)
    w3 = _make_w3(150)
    w3.eth.estimate_gas.return_value = 100_000
    if failure == "mined_revert":
        w3.eth.wait_for_transaction_receipt.return_value = MagicMock(status=0)
    else:
        w3.eth.wait_for_transaction_receipt.side_effect = TimeoutError("receipt timeout")
    ctx, console = _make_ctx(w3)
    ctx.obj.get_tx_params.return_value = {}

    with pytest.raises(typer.Exit):
        _call(ctx, contract)

    assert w3.eth.send_raw_transaction.call_count == 1
    assert state["lock_calls"] == [GI]
    assert state["seed"] == ZERO_SEED

# --- lock_batch_seed_if_pending: validator-side lock (BL-26) ---------------


@patch("dincli.cli.utils.ensure_batch_seed_locked")
def test_validator_lock_audit_seed_when_pending(mock_ensure):
    ctx, contract = MagicMock(), MagicMock()

    assert lock_batch_seed_if_pending(ctx, contract, GI, GI, GIstatestrToIndex("LMSclosed"), "audit") is True

    mock_ensure.assert_called_once_with(
        ctx, contract, GI, "auditSeed", "auditSeedBlock", "lockAuditSeed", "auditor-batch",
    )


@patch("dincli.cli.utils.ensure_batch_seed_locked")
def test_validator_lock_agg_seed_when_pending(mock_ensure):
    ctx, contract = MagicMock(), MagicMock()

    assert lock_batch_seed_if_pending(ctx, contract, GI, GI, GIstatestrToIndex("LMSevaluationClosed"), "agg") is True

    mock_ensure.assert_called_once_with(
        ctx, contract, GI, "aggSeed", "aggSeedBlock", "lockAggSeed", "T1/T2 batch",
    )


@patch("dincli.cli.utils.ensure_batch_seed_locked")
def test_validator_lock_noop_outside_pending_state_or_past_gi(mock_ensure):
    ctx, contract = MagicMock(), MagicMock()

    # Batches already created, or the other seed's pending state.
    assert lock_batch_seed_if_pending(ctx, contract, GI, GI, GIstatestrToIndex("AuditorsBatchesCreated"), "audit") is False
    assert lock_batch_seed_if_pending(ctx, contract, GI, GI, GIstatestrToIndex("LMSclosed"), "agg") is False
    # A past GI (e.g. show-batch --gi <old>) never locks.
    assert lock_batch_seed_if_pending(ctx, contract, GI, GI + 1, GIstatestrToIndex("LMSclosed"), "audit") is False

    mock_ensure.assert_not_called()
