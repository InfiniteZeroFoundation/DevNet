"""Retry safety for `auditor lms-evaluation evaluate --submit` (issue #202 Part 1).

The auditor-side twin of the aggregator retry guard (PR No. 197 review,
finding No. 1; see tests/test_aggregator_commit_retry.py). The commit-then-
reveal flow caches the committed (score, vote, salt) per LM so the later
reveal can reproduce the commit hash. Two properties keep a retry from
stranding an honest auditor, whose reveal would otherwise revert
TA_RevealHashMismatch and get them S1-slashed (AUD_NO_VOTE):

- an LM already committed on-chain (hasCommittedLM) is skipped before
  re-evaluating, and its cached (score, vote, salt) is left untouched;
- for an uncommitted LM, the cache is written *before* the commit tx is sent,
  so a tx whose receipt wait fails but which still mines never loses its
  preimage (build_and_send_tx returns None in that case, same as on a revert).
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from dincli.cli import auditor
from dincli.cli.auditor import (_audit_commit_hash, _commit_store_path,
                                _save_commit, evaluate_lms)

GI = 1
BATCH = 0
ACCOUNT = "0x" + "11" * 20
OWNER = "0x" + "22" * 20
MODELS = [0, 1]
OLD_SALT = b"\xee" * 32


class _Call:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


def _make_auditor_contract(state):
    """state: 'committed' (set of model indexes), 'commits' (list of args)."""

    def getter(name):
        if name == "AuditorsBatchCount":
            return lambda gi: _Call(1)
        if name == "getAuditorsBatch":
            return lambda gi, b: _Call((BATCH, [ACCOUNT], MODELS, b"\x01" * 16))
        if name == "hasCommittedLM":
            return lambda gi, b, who, m: _Call(m in state["committed"])
        if name == "lmSubmissions":
            return lambda gi, m: _Call(("0x" + "33" * 20, b"\x00" * 32, 0, False, False, False, 0))
        if name == "encryptedTestDataKey":
            return lambda gi, b, who: _Call(b"\x02" * 16)
        if name == "commitAuditScore":
            def _commit(*args):
                state["commits"].append(args)
                return MagicMock(name="commitAuditScore_tx")
            return _commit
        raise AttributeError(name)

    class _Functions:
        def __getattr__(self, name):
            return getter(name)

    contract = MagicMock()
    contract.functions = _Functions()
    return contract


def _make_coordinator_contract():
    contract = MagicMock()
    contract.functions.genesisModelIpfsHash.return_value = _Call(b"\x00" * 32)
    contract.functions.owner.return_value = _Call(OWNER)
    return contract


def _make_ctx(auditor_contract, model_base_dir):
    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = _make_coordinator_contract()
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = auditor_contract
    ctx.obj.get_current_gi_and_state.return_value = (GI, 0)
    ctx.obj.get_model_base_dir.return_value = model_base_dir
    return ctx


def _manifest_key(network, key, model_id):
    if key == "requirements.txt":
        return {}
    if key == "owner_encryption_pubkey":
        return "00" * 32
    return {"path": f"services/{key}.py", "ipfs": "QmSvc"}


@pytest.fixture
def worker_stubs(tmp_path):
    """Stubs the manifest/decrypt/docker steps between LM selection and the
    commit, so the evaluation path runs through to the commit tx with
    score 80 / eligible True."""
    pt_path = tmp_path / "dataset" / "auditor" / "TestDatasets" / f"auditorDataset_{GI}_{BATCH}.pt"
    pt_path.parent.mkdir(parents=True)
    pt_path.write_bytes(b"test data")  # already decrypted: skips the IPFS fetch
    with patch.object(auditor, "get_cid_from_bytes32", return_value="QmCid"), \
         patch.object(auditor, "get_manifest_key", side_effect=_manifest_key), \
         patch.object(auditor, "require_custom_manifest_service"), \
         patch.object(auditor, "_load_auditor_x25519_key"), \
         patch.object(auditor, "PublicKey"), \
         patch.object(auditor, "Box"), \
         patch.object(auditor, "_decrypt_aes_gcm", return_value=b"\x03" * 32 + b"\x04" * 65), \
         patch.object(auditor.Account, "recover_message", return_value=OWNER), \
         patch.object(auditor, "write_worker_job",
                      return_value=(tmp_path / "job.json", tmp_path / "out")), \
         patch.object(auditor, "run_worker_container",
                      return_value=MagicMock(returncode=0, stdout="", stderr="")) as run_worker, \
         patch.object(auditor, "read_worker_result",
                      return_value={"status": "ok", "result": [80, True]}), \
         patch.object(auditor.time, "sleep"):
        yield run_worker


def _run(ctx):
    # evaluate_lms(ctx, model_id, lmi, batch, submit, gi, packages_dir, no_cache)
    evaluate_lms(ctx, 1, None, None, True, None, None, False)


def _read_cache(model_base_dir, model_index):
    with open(_commit_store_path(model_base_dir, GI, BATCH, model_index)) as f:
        return json.load(f)


def test_already_committed_lm_is_skipped_and_cache_untouched(tmp_path, worker_stubs):
    """LM 0 committed on an earlier run, LM 1's commit failed: the retry must
    leave LM 0's cache and on-chain commit alone and only commit LM 1."""
    state = {"committed": {0}, "commits": []}
    ctx = _make_ctx(_make_auditor_contract(state), tmp_path)
    _save_commit(tmp_path, GI, BATCH, 0, 55, False, OLD_SALT)
    before = _read_cache(tmp_path, 0)

    with patch.object(auditor, "build_and_send_tx") as send:
        _run(ctx)

    assert _read_cache(tmp_path, 0) == before
    assert send.call_count == 1
    assert [args[:3] for args in state["commits"]] == [(GI, BATCH, 1)]
    # Skipped before re-evaluating: the worker ran for LM 1 only.
    assert worker_stubs.call_count == 1
    assert "lm-1" in worker_stubs.call_args.kwargs["container_name"]


def test_all_committed_sends_nothing(tmp_path, worker_stubs):
    state = {"committed": set(MODELS), "commits": []}
    ctx = _make_ctx(_make_auditor_contract(state), tmp_path)

    with patch.object(auditor, "build_and_send_tx") as send:
        _run(ctx)

    send.assert_not_called()
    worker_stubs.assert_not_called()
    assert state["commits"] == []


def test_cache_written_before_send_and_matches_sent_commit(tmp_path, worker_stubs):
    """build_and_send_tx returning None (revert, or receipt wait failed on a
    tx that may still mine) must still leave the preimage of the hash that
    was actually sent on disk."""
    state = {"committed": set(), "commits": []}
    ctx = _make_ctx(_make_auditor_contract(state), tmp_path)
    seen_at_send = []

    def _send(ctx_, fn, *args, **kwargs):
        model_index = state["commits"][-1][2]
        seen_at_send.append(_commit_store_path(tmp_path, GI, BATCH, model_index).exists())
        return None

    with patch.object(auditor, "build_and_send_tx", side_effect=_send):
        _run(ctx)

    assert seen_at_send == [True, True]
    assert len(state["commits"]) == 2
    for gi, batch_id, model_index, sent_hash in state["commits"]:
        cached = _read_cache(tmp_path, model_index)
        assert (cached["score"], cached["vote"]) == (80, True)
        salt = bytes.fromhex(cached["salt"])
        assert _audit_commit_hash(80, True, salt, ACCOUNT, gi, batch_id, model_index) == sent_hash
