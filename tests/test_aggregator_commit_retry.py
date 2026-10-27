"""Retry safety for `aggregator aggregate-t1/-t2 --submit` (PR No. 197 review,
finding No. 1).

The commit-then-reveal flow caches the committed (cid, salt) locally so the
later reveal can reproduce the commit hash. Two properties keep a retry from
stranding an honest aggregator (whose reveal would otherwise revert
TC_T{1,2}RevealHashMismatch and get them S2-slashed):

- a batch already committed on-chain is skipped before re-aggregating, and
  its cached (cid, salt) is left untouched;
- for an uncommitted batch, the cache is written *before* the commit tx is
  sent, so a tx whose receipt wait fails but which still mines never loses
  its preimage (build_and_send_tx returns None in that case, same as on a
  revert).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from dincli.cli import aggregator
from dincli.cli.aggregator import (TIER1, TIER2, _agg_commit_hash,
                                   _agg_commit_store_path, _save_agg_commit,
                                   aggregate_t1, aggregate_t2)

GI = 1
ACCOUNT = "0x" + "11" * 20
AGG_CID_BYTES32 = "0x" + "ab" * 32
OLD_CID = b"\xcd" * 32
OLD_SALT = b"\xee" * 32


class _Call:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


def _make_contract(state):
    """state: 'committed' (bool), 'commits' (list of (fn, args))."""

    def getter(name):
        if name == "tier1BatchCount":
            return lambda gi: _Call(1)
        if name == "genesisModelIpfsHash":
            return lambda: _Call(b"\x00" * 32)
        if name == "getTier1Batch":
            return lambda gi, i: _Call((0, [ACCOUNT], [], False, b"\x00" * 32))
        if name == "getTier2Batch":
            return lambda gi, i: _Call((0, [ACCOUNT], False, b"\x00" * 32))
        if name == "getAggregatorSubmission":
            # (committed, commitHash, submitted, cid, votes)
            return lambda gi, tier, bid, who: _Call((state["committed"], b"\x00" * 32, False, b"\x00" * 32, 0))
        if name in ("commitT1Aggregation", "commitT2Aggregation"):
            def _commit(*args):
                state["commits"].append((name, args))
                return MagicMock(name=f"{name}_tx")
            return _commit
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
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = contract
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = MagicMock()
    ctx.obj.get_current_gi_and_state.return_value = (GI, 0)
    ctx.obj.get_model_base_dir.return_value = model_base_dir
    return ctx


@pytest.fixture
def worker_stubs(tmp_path):
    """Stubs every IPFS/manifest/docker step between batch selection and the
    commit, so the aggregation path runs through to the commit tx."""
    output_dir = tmp_path / "out"
    with patch.object(aggregator, "get_cid_from_bytes32", return_value="QmGenesis"), \
         patch.object(aggregator, "get_manifest_key",
                      return_value={"path": "services/aggregator.py", "ipfs": "QmSvc"}), \
         patch.object(aggregator, "require_custom_manifest_service"), \
         patch.object(aggregator, "write_worker_job",
                      return_value=(tmp_path / "job.json", output_dir)), \
         patch.object(aggregator, "run_worker_container",
                      return_value=MagicMock(returncode=0, stdout="", stderr="")), \
         patch.object(aggregator, "read_worker_result",
                      return_value={"status": "ok", "result": "/din/model/avg.pth"}), \
         patch.object(aggregator, "upload_to_ipfs", return_value="QmAgg"), \
         patch.object(aggregator, "get_bytes32_from_cid", return_value=AGG_CID_BYTES32), \
         patch.object(aggregator.time, "sleep"):
        yield


def _read_cache(model_base_dir, tier, batch_id=0):
    with open(_agg_commit_store_path(model_base_dir, tier, GI, batch_id)) as f:
        return json.load(f)


@pytest.mark.parametrize("tier,command,commit_fn", [
    (TIER1, aggregate_t1, "commitT1Aggregation"),
    (TIER2, aggregate_t2, "commitT2Aggregation"),
])
def test_already_committed_batch_is_skipped_and_cache_untouched(tmp_path, tier, command, commit_fn):
    state = {"committed": True, "commits": []}
    contract = _make_contract(state)
    ctx = _make_ctx(contract, tmp_path)
    _save_agg_commit(tmp_path, tier, GI, 0, OLD_CID, OLD_SALT)
    before = _read_cache(tmp_path, tier)

    with patch.object(aggregator, "build_and_send_tx") as send, \
         patch.object(aggregator, "get_cid_from_bytes32", return_value="QmGenesis"), \
         patch.object(aggregator, "run_worker_container") as run_worker:
        command(ctx, 1, None, True, None, None, False)

    assert _read_cache(tmp_path, tier) == before
    send.assert_not_called()
    run_worker.assert_not_called()  # skipped before re-aggregating
    assert state["commits"] == []


@pytest.mark.parametrize("tier,command,commit_fn", [
    (TIER1, aggregate_t1, "commitT1Aggregation"),
    (TIER2, aggregate_t2, "commitT2Aggregation"),
])
def test_cache_written_before_send_and_matches_sent_commit(tmp_path, worker_stubs, tier, command, commit_fn):
    """build_and_send_tx returning None (revert, or receipt wait failed on a
    tx that may still mine) must still leave the preimage of the hash that
    was actually sent on disk."""
    state = {"committed": False, "commits": []}
    contract = _make_contract(state)
    ctx = _make_ctx(contract, tmp_path)
    cache_path = _agg_commit_store_path(tmp_path, tier, GI, 0)
    seen_at_send = {}

    def _send(ctx_, fn, *args, **kwargs):
        seen_at_send["cache_exists"] = cache_path.exists()
        return None

    with patch.object(aggregator, "build_and_send_tx", side_effect=_send):
        command(ctx, 1, None, True, None, None, False)

    assert seen_at_send == {"cache_exists": True}
    assert len(state["commits"]) == 1
    name, (gi, batch_id, sent_hash) = state["commits"][0]
    assert (name, gi, batch_id) == (commit_fn, GI, 0)

    cached = _read_cache(tmp_path, tier)
    cid = bytes.fromhex(cached["cid"])
    salt = bytes.fromhex(cached["salt"])
    assert cid == bytes.fromhex(AGG_CID_BYTES32[2:])
    assert _agg_commit_hash(cid, salt, ACCOUNT, GI, tier, 0) == sent_hash
