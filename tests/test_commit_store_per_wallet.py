"""The auditor and aggregator commit stores are per wallet.

Several auditors share an audit batch, and several aggregators share a T1/T2
batch. When they run from one machine (one dincli cache dir; e.g. `--demokey`
in the tests/dincli harness), a shared commit file let the last committer
overwrite the others' salts, so their reveals failed the commit hash. Each
wallet now gets commits/<address>/..., and the loaders still read the old
shared path so a commit made before upgrading can be revealed.
"""
import json

from dincli.cli.aggregator import TIER1, TIER2, _agg_commit_store_path, _load_agg_commit, _save_agg_commit
from dincli.cli.auditor import _commit_store_path, _load_commit, _save_commit

A = "0x" + "aa" * 20
B = "0x" + "bb" * 20
GI, BATCH, LMI = 1, 0, 3


def test_two_auditors_same_batch_keep_their_own_salts(tmp_path):
    _save_commit(tmp_path, GI, BATCH, LMI, 70, True, b"\x01" * 32, A)
    _save_commit(tmp_path, GI, BATCH, LMI, 40, False, b"\x02" * 32, B)

    a, b = _load_commit(tmp_path, GI, BATCH, LMI, A), _load_commit(tmp_path, GI, BATCH, LMI, B)
    assert (a["score"], a["vote"], a["salt"]) == (70, True, b"\x01" * 32)
    assert (b["score"], b["vote"], b["salt"]) == (40, False, b"\x02" * 32)
    assert _commit_store_path(tmp_path, GI, BATCH, LMI, A).parent.name == A


def test_auditor_reads_legacy_shared_commit(tmp_path):
    legacy = _commit_store_path(tmp_path, GI, BATCH, LMI, None)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"score": 9, "vote": True, "salt": ("03" * 32)}))

    assert _load_commit(tmp_path, GI, BATCH, LMI, A)["score"] == 9
    assert _load_commit(tmp_path, GI + 1, BATCH, LMI, A) is None


def test_two_aggregators_same_batch_keep_their_own_salts(tmp_path):
    for tier in (TIER1, TIER2):
        _save_agg_commit(tmp_path, tier, GI, BATCH, b"\xaa" * 32, b"\x01" * 32, A)
        _save_agg_commit(tmp_path, tier, GI, BATCH, b"\xaa" * 32, b"\x02" * 32, B)
        assert _load_agg_commit(tmp_path, tier, GI, BATCH, A)["salt"] == b"\x01" * 32
        assert _load_agg_commit(tmp_path, tier, GI, BATCH, B)["salt"] == b"\x02" * 32


def test_aggregator_reads_legacy_shared_commit(tmp_path):
    legacy = _agg_commit_store_path(tmp_path, TIER1, GI, BATCH, None)
    legacy.parent.mkdir(parents=True)
    legacy.write_text(json.dumps({"cid": "ab" * 32, "salt": "04" * 32}))

    assert _load_agg_commit(tmp_path, TIER1, GI, BATCH, A)["salt"] == b"\x04" * 32
    assert _load_agg_commit(tmp_path, TIER2, GI, BATCH, A) is None
