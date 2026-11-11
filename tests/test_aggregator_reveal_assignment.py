"""`aggregator reveal-t1/-t2` check the seat before the local commit cache
(PR No. 313 review).

Before this, both commands skipped every batch with no cached commit and
printed one generic "No local ... commits found" line, whether or not the
wallet was seated. A seated aggregator that had lost its cache exited 0
without revealing, and the full-GI walk passed, because a T1 batch can
finalize on 2 of 3 reveals. Now:

- seated, no cache  -> "No local commit found for T{1,2} batch <id>", no tx
  (the integration walk rejects this message);
- not seated        -> "Not assigned to ... nothing to reveal", no tx;
- seated, cached    -> the reveal tx is sent.
"""
from unittest.mock import MagicMock, patch

import pytest

from dincli.cli import aggregator
from dincli.cli.aggregator import TIER1, TIER2, _save_agg_commit, reveal_t1, reveal_t2

GI = 1
ACCOUNT = "0x" + "11" * 20
OTHER = "0x" + "22" * 20
CID = b"\xab" * 32
SALT = b"\xee" * 32


class _Call:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


def _make_contract(t1_seats, t2_seats, reveals):
    """t1_seats: one validator list per T1 batch. t2_seats: the T2 batch's
    aggregators, or None for a GI with no T2 batch (getTier2Batch reverts)."""

    def getter(name):
        if name == "tier1BatchCount":
            return lambda gi: _Call(len(t1_seats))
        if name == "getTier1Batch":
            return lambda gi, i: _Call((i, t1_seats[i], [], False, b"\x00" * 32))
        if name == "getTier2Batch":
            def _t2(gi, i):
                if t2_seats is None:
                    raise Exception("execution reverted: TC_BatchNotFound")
                return _Call((0, t2_seats, False, b"\x00" * 32))
            return _t2
        if name in ("revealT1Aggregation", "revealT2Aggregation"):
            def _reveal(*args):
                reveals.append((name, args))
                return MagicMock(name=f"{name}_tx")
            return _reveal
        raise AttributeError(name)

    class _Functions:
        def __getattr__(self, name):
            return getter(name)

    contract = MagicMock()
    contract.functions = _Functions()
    return contract


def _make_ctx(contract, model_base_dir):
    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    console = MagicMock()
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, console)
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = contract
    ctx.obj.get_current_gi_and_state.return_value = (GI, 0)
    ctx.obj.get_model_base_dir.return_value = model_base_dir
    return ctx, console


def _printed(console) -> str:
    return "\n".join(str(c.args[0]) for c in console.print.call_args_list if c.args)


def _run(tier, ctx):
    if tier == TIER1:
        reveal_t1(ctx, 1, None, None)
    else:
        reveal_t2(ctx, 1, None)


def _seats(tier, seated):
    """Layout with ACCOUNT seated in batch 0 of the given tier (or nowhere)."""
    batch = [ACCOUNT, OTHER] if seated else [OTHER]
    if tier == TIER1:
        return [[OTHER], batch], [OTHER]  # ACCOUNT, if seated, is in T1 batch 1
    return [[OTHER]], batch


@pytest.mark.parametrize("tier,label,bid", [(TIER1, "T1", 1), (TIER2, "T2", 0)])
def test_seated_without_cache_reports_missing_commit(tmp_path, tier, label, bid):
    reveals = []
    t1, t2 = _seats(tier, seated=True)
    ctx, console = _make_ctx(_make_contract(t1, t2, reveals), tmp_path)

    with patch.object(aggregator, "build_and_send_tx") as send:
        _run(tier, ctx)

    out = _printed(console)
    assert f"No local commit found for {label} batch {bid}" in out
    assert "Not assigned" not in out
    send.assert_not_called()
    assert reveals == []


@pytest.mark.parametrize("tier,label", [(TIER1, "T1"), (TIER2, "T2")])
def test_unseated_is_a_quiet_no_op(tmp_path, tier, label):
    reveals = []
    t1, t2 = _seats(tier, seated=False)
    ctx, console = _make_ctx(_make_contract(t1, t2, reveals), tmp_path)

    with patch.object(aggregator, "build_and_send_tx") as send:
        _run(tier, ctx)

    out = _printed(console)
    assert f"Not assigned to {'any' if tier == TIER1 else 'the'} {label} batch" in out
    assert "No local commit found" not in out
    send.assert_not_called()
    assert reveals == []


def test_t2_with_no_t2_batch_is_not_assigned(tmp_path):
    """getTier2Batch reverts when the GI has no T2 batch (seats too few)."""
    reveals = []
    ctx, console = _make_ctx(_make_contract([[ACCOUNT]], None, reveals), tmp_path)

    with patch.object(aggregator, "build_and_send_tx") as send:
        reveal_t2(ctx, 1, None)

    assert "Not assigned to the T2 batch" in _printed(console)
    send.assert_not_called()


@pytest.mark.parametrize("tier,reveal_fn,bid", [
    (TIER1, "revealT1Aggregation", 1),
    (TIER2, "revealT2Aggregation", 0),
])
def test_seated_with_cache_reveals(tmp_path, tier, reveal_fn, bid):
    reveals = []
    t1, t2 = _seats(tier, seated=True)
    ctx, console = _make_ctx(_make_contract(t1, t2, reveals), tmp_path)
    _save_agg_commit(tmp_path, tier, GI, bid, CID, SALT, ACCOUNT)

    with patch.object(aggregator, "build_and_send_tx") as send:
        _run(tier, ctx)

    send.assert_called_once()
    assert reveals == [(reveal_fn, (GI, bid, CID, SALT))]
    out = _printed(console)
    assert "No local commit found" not in out
    assert "Not assigned" not in out


def test_t1_skips_unseated_batches_without_reporting_them(tmp_path):
    """Seated in batch 1 only: batch 0 (no cache, not seated) stays silent."""
    reveals = []
    ctx, console = _make_ctx(_make_contract([[OTHER], [ACCOUNT]], [OTHER], reveals), tmp_path)
    _save_agg_commit(tmp_path, TIER1, GI, 1, CID, SALT, ACCOUNT)

    with patch.object(aggregator, "build_and_send_tx"):
        reveal_t1(ctx, 1, None, None)

    assert reveals == [("revealT1Aggregation", (GI, 1, CID, SALT))]
    assert "No local commit found for T1 batch 0" not in _printed(console)
