"""`aggregator aggregate-t2` names its work after the T2 batch (issue #202 Part 2).

aggregate_t2 reads the T2 batch id from getTier2Batch, then loops over every
T1 batch to collect their final CIDs. That loop used to unpack into `bid`
too, so after it `bid` held the *last T1 batch's* id, and the T2 models path,
worker job and container were named after an unrelated T1 batch. The on-chain
commit used the loop index and was unaffected.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dincli.cli import aggregator
from dincli.cli.aggregator import aggregate_t2

GI = 1
ACCOUNT = "0x" + "11" * 20
T1_BATCH_COUNT = 3  # T1 ids 0..2; the last one (2) is what leaked before the fix


class _Call:
    def __init__(self, value):
        self._value = value

    def call(self):
        return self._value


def _make_contract():
    def getter(name):
        if name == "genesisModelIpfsHash":
            return lambda: _Call(b"\x00" * 32)
        if name == "getTier2Batch":
            return lambda gi, i: _Call((0, [ACCOUNT], False, b"\x00" * 32))
        if name == "getAggregatorSubmission":
            return lambda gi, tier, bid, who: _Call((False, b"\x00" * 32, False, b"\x00" * 32, 0))
        if name == "tier1BatchCount":
            return lambda gi: _Call(T1_BATCH_COUNT)
        if name == "getTier1Batch":
            return lambda gi, j: _Call((j, ["0x" + "44" * 20], [j], True, bytes([j + 1]) * 32))
        raise AttributeError(name)

    class _Functions:
        def __getattr__(self, name):
            return getter(name)

    contract = MagicMock()
    contract.functions = _Functions()
    return contract


@pytest.fixture
def ctx(tmp_path):
    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = _make_contract()
    ctx.obj.get_current_gi_and_state.return_value = (GI, 0)
    ctx.obj.get_model_base_dir.return_value = tmp_path
    return ctx


@pytest.fixture
def stubs(tmp_path):
    with patch.object(aggregator, "get_cid_from_bytes32", side_effect=lambda h: f"Qm{h[-4:]}"), \
         patch.object(aggregator, "get_manifest_key",
                      return_value={"path": "services/aggregator.py", "ipfs": "QmSvc"}), \
         patch.object(aggregator, "require_custom_manifest_service"), \
         patch.object(aggregator, "write_worker_job",
                      return_value=(tmp_path / "job.json", tmp_path / "out")) as write_job, \
         patch.object(aggregator, "run_worker_container",
                      return_value=MagicMock(returncode=0, stdout="", stderr="")) as run_worker, \
         patch.object(aggregator, "read_worker_result",
                      return_value={"status": "ok", "result": "/din/model/avg.pth"}), \
         patch.object(aggregator, "upload_to_ipfs", return_value="QmAgg"), \
         patch.object(aggregator.time, "sleep"):
        yield write_job, run_worker


@pytest.mark.parametrize("batch_id", [None, 0])
def test_t2_work_is_named_after_the_t2_batch_not_the_last_t1_batch(ctx, stubs, tmp_path, batch_id):
    write_job, run_worker = stubs

    # aggregate_t2(ctx, model_id, gi, submit, batch_id, packages_dir, no_cache)
    aggregate_t2(ctx, 1, None, False, batch_id, None, False)

    write_job.assert_called_once()
    assert write_job.call_args.args[1] == f"aggregator_t2_gi_{GI}_batch_0"
    job_args = write_job.call_args.args[2]["args"]
    assert job_args[4] == 0  # bid passed to get_aggregated_cid_t2
    assert len(job_args[2]) == T1_BATCH_COUNT  # every T1 final CID collected

    run_worker.assert_called_once()
    assert run_worker.call_args.kwargs["container_name"].endswith(f"-gi-{GI}-batch-0")
    models_path = Path(run_worker.call_args.kwargs["writable_subdirs"][0])
    assert models_path == tmp_path / "aggregator" / ACCOUNT / str(GI) / "T2" / "0" / "models"


def test_batch_out_of_range_still_rejected(ctx, stubs):
    import typer

    with pytest.raises(typer.Exit):
        aggregate_t2(ctx, 1, None, False, 1, None, False)
