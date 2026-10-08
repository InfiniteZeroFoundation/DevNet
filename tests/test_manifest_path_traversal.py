"""Tests for issue #227 (manifest path traversal).

Every dincli command that fetches a model-owner-supplied service file or
artifact built its destination path by joining a trusted local base
directory with a raw `path` string taken directly from the model's
manifest JSON, with no containment check -- an absolute `path` discarded
the base directory entirely, and `..` segments walked out of it. The
manifest is fetched from IPFS by a CID the model owner controls, so its
`path` fields are attacker-influenced: any client/auditor/aggregator who
interacts with a malicious model owner's model could have an arbitrary
file on their own machine overwritten.

`resolve_manifest_path` (dincli/cli/utils.py) is the fix: every call site
that used to do `<base> / Path(manifest[...]["path"])` now goes through
it, and it raises rather than silently re-anchoring. `ensure_file_exists`
and `load_custom_fn` (dincli/cli/context.py) also take a required
`base_dir` and check containment as a backstop, so a future call site that
forgets the helper still can't write outside its workflow root:
`get_model_base_dir(model_id)` for participants (and the model owner once
the model is registered), `get_task_dir(coordinator)` for the model owner
while preparing the task.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# dincli/cli/aggregator.py and dincli/cli/auditor.py import dincli.cli.dintoken,
# which uses a 3.12+ nested-quote f-string that fails to parse on Python
# 3.10 (a pre-existing, unrelated issue -- see tests/test_dintoken.py). Import
# those two modules lazily, inside the tests that need them, so a 3.10
# collection environment can still run every other test in this file.
from dincli.cli import client
from dincli.cli.context import DinContext
from dincli.cli.modelownerd import auditor_batches
from dincli.cli.utils import ManifestPathEscapesBaseError, resolve_manifest_path

ACCOUNT = "0x" + "11" * 20


# ─── resolve_manifest_path (the helper itself) ──────────────────────────────

def test_resolve_manifest_path_normal_relative_path_resolves_inside_base(tmp_path):
    resolved = resolve_manifest_path(tmp_path, "services/client.py")
    assert resolved == (tmp_path / "services" / "client.py").resolve()
    assert resolved.is_relative_to(tmp_path.resolve())


def test_resolve_manifest_path_rejects_absolute_path(tmp_path):
    with pytest.raises(ManifestPathEscapesBaseError):
        resolve_manifest_path(tmp_path, "/etc/passwd")


def test_resolve_manifest_path_rejects_absolute_path_even_inside_looking(tmp_path):
    # An absolute path that happens to render as a subpath of tmp_path as a
    # *string* must still be rejected on the is_absolute() check alone --
    # confirms the rejection isn't accidentally keyed off string prefixes.
    fake_absolute = "/" + str(tmp_path).lstrip("/")
    with pytest.raises(ManifestPathEscapesBaseError):
        resolve_manifest_path(tmp_path, fake_absolute)


def test_resolve_manifest_path_rejects_dotdot_traversal(tmp_path):
    base = tmp_path / "model_base"
    base.mkdir()
    with pytest.raises(ManifestPathEscapesBaseError):
        resolve_manifest_path(base, "../../../../etc/passwd")


def test_resolve_manifest_path_rejects_symlink_escape(tmp_path):
    base = tmp_path / "model_base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")

    # A symlink *inside* the base pointing *outside* it must still be
    # rejected -- resolve() follows it, and the check runs after resolve().
    escape_link = base / "escape"
    escape_link.symlink_to(outside)

    with pytest.raises(ManifestPathEscapesBaseError):
        resolve_manifest_path(base, "escape/secret.txt")


def test_resolve_manifest_path_allows_a_path_equal_to_base_itself(tmp_path):
    # Edge case: manifest_path = "." should resolve to base_dir itself, not
    # raise -- is_relative_to(x, x) is True.
    resolved = resolve_manifest_path(tmp_path, ".")
    assert resolved == tmp_path.resolve()


# ─── ensure_file_exists backstop ────────────────────────────────────────────

def _make_dincontext():
    ctx = DinContext.__new__(DinContext)  # bypass __init__ (no config/log I/O needed)
    ctx.console = MagicMock()
    ctx._resolved_network = "local"
    return ctx


def test_ensure_file_exists_backstop_rejects_outside_path_with_explicit_base(tmp_path):
    ctx = _make_dincontext()
    base = tmp_path / "model_base"
    base.mkdir()
    outside_path = tmp_path / "outside" / "evil.py"

    with patch("dincli.cli.context.retrieve_from_ipfs") as mock_retrieve:
        with pytest.raises(ManifestPathEscapesBaseError):
            ctx.ensure_file_exists(outside_path, "cidABC", "evil file", base_dir=base)
        mock_retrieve.assert_not_called()


def test_ensure_file_exists_and_load_custom_fn_require_base_dir(tmp_path):
    # There is no CACHE_DIR fallback: a caller that forgets base_dir fails
    # loudly instead of being checked against a boundary that's either too
    # wide (other models' dirs) or wrong (the model owner's cwd task dir).
    ctx = _make_dincontext()
    path = tmp_path / "services" / "client.py"

    with patch("dincli.cli.context.retrieve_from_ipfs") as mock_retrieve:
        with pytest.raises(TypeError):
            ctx.ensure_file_exists(path, "cidABC", "client service")
        with pytest.raises(TypeError):
            ctx.load_custom_fn(path, "fn")
        mock_retrieve.assert_not_called()


def test_ensure_file_exists_participant_cannot_write_into_another_model_dir(tmp_path, monkeypatch):
    # A participant's root is its own model dir, not the whole cache: a path
    # under a sibling model's dir is rejected even though it's inside CACHE_DIR.
    monkeypatch.setattr("dincli.cli.context.CACHE_DIR", tmp_path / "cache")
    ctx = _make_dincontext()
    other_model_path = ctx.get_model_base_dir(2) / "services" / "client.py"

    with patch("dincli.cli.context.retrieve_from_ipfs") as mock_retrieve:
        with pytest.raises(ManifestPathEscapesBaseError):
            ctx.ensure_file_exists(other_model_path, "cidABC", "client service", base_dir=ctx.get_model_base_dir(1))
        mock_retrieve.assert_not_called()


def test_load_custom_fn_model_owner_task_dir_outside_cache_dir(tmp_path, monkeypatch):
    # Regression for create-genesis-model / submit-genesis-model /
    # distribute-mnist (task flow): the model owner's services live under
    # cwd/tasks/<network>/<coordinator>, outside CACHE_DIR, and must load.
    monkeypatch.setattr("dincli.cli.context.CACHE_DIR", tmp_path / "cache")
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    ctx = _make_dincontext()

    task_dir = ctx.get_task_dir("0xabc")
    assert task_dir == project / "tasks" / "local" / "0xabc"
    service_path = resolve_manifest_path(task_dir, "services/modelowner.py")
    service_path.parent.mkdir(parents=True)
    service_path.write_text("def getGenesisModelIpfs(task_dir):\n    return 'ok'\n")

    fn = ctx.load_custom_fn(service_path, "getGenesisModelIpfs", base_dir=task_dir)
    assert fn(task_dir) == "ok"

    # The same file is outside a participant's model dir.
    with pytest.raises(ManifestPathEscapesBaseError):
        ctx.load_custom_fn(service_path, "getGenesisModelIpfs", base_dir=ctx.get_model_base_dir(1))


def test_ensure_file_exists_accepts_a_path_inside_the_given_base(tmp_path):
    ctx = _make_dincontext()
    base = tmp_path / "model_base"
    base.mkdir()
    inside_path = base / "services" / "client.py"

    def _fake_retrieve(cid, dest):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("ok")

    with patch("dincli.cli.context.retrieve_from_ipfs", side_effect=_fake_retrieve) as mock_retrieve:
        ctx.ensure_file_exists(inside_path, "cidABC", "client service", base_dir=base)
        mock_retrieve.assert_called_once()
    assert inside_path.read_text() == "ok"


# ─── Per-role call sites: a malicious manifest raises before any I/O ────────
#
# Each of these calls the real CLI command function with a heavily mocked
# `ctx`/contract surface (ctx.obj is a MagicMock -- only resolve_manifest_path
# itself is real code), a manifest whose "path" field escapes the model's
# base directory, and asserts the command raises before ctx.obj.ensure_file_exists
# (the actual download/write step) is ever reached.

@patch("dincli.cli.client.get_cid_from_bytes32", return_value="cidGenesis")
def test_train_lms_rejects_manifest_path_escape(mock_get_cid):
    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())

    coordinator = MagicMock()
    coordinator.functions.genesisModelIpfsHash.return_value.call.return_value = b"\x00" * 32
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = coordinator
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = MagicMock()
    ctx.obj.get_current_gi_and_state.return_value = (1, "LMSubmissionsStarted")  # current_GI == 1: skips getTier2Batch
    ctx.obj.validate_gi_ET_curr_GI.return_value = None
    ctx.obj.get_model_base_dir.return_value = Path("/tmp/dincli-test-client-model")

    runtime = MagicMock()

    def require_manifest_key(key):
        if key == "train_client_model":
            return {"path": "../../../../etc/passwd", "ipfs": "cidABC"}
        if key == "ModelArchitecture":
            return {"path": "model.py", "ipfs": "cidDEF"}
        raise KeyError(key)

    runtime.require_manifest_key.side_effect = require_manifest_key
    ctx.obj.build_service_runtime.return_value = runtime

    with pytest.raises(ManifestPathEscapesBaseError):
        client.train_lms(ctx, model_id=1, gi=None, packages_dir=None, no_cache=False)

    ctx.obj.ensure_file_exists.assert_not_called()


@patch("dincli.cli.aggregator.get_manifest_key")
@patch("dincli.cli.aggregator.get_cid_from_bytes32", return_value="cidGenesis")
def test_aggregate_t1_rejects_manifest_path_escape(mock_get_cid, mock_get_manifest_key):
    from dincli.cli import aggregator

    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())

    coordinator = MagicMock()
    coordinator.functions.tier1BatchCount.return_value.call.return_value = 1
    coordinator.functions.genesisModelIpfsHash.return_value.call.return_value = b"\x00" * 32
    # (bid, aggregators_in_batch, model_indexes, finalized, cid)
    coordinator.functions.getTier1Batch.return_value.call.return_value = (0, [ACCOUNT], [], False, b"\x00" * 32)
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = coordinator
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = MagicMock()
    ctx.obj.get_current_gi_and_state.return_value = (1, "T1AggregationStarted")
    ctx.obj.validate_gi_ET_curr_GI.return_value = 1
    ctx.obj.validate_GIstate_ET_given_GIstate.return_value = None
    ctx.obj.get_model_base_dir.return_value = Path("/tmp/dincli-test-agg-model")

    def manifest_side_effect(network, key, model_id):
        if key == "get_aggregated_cid_t1":
            return {"path": "/etc/passwd", "ipfs": "cidABC"}
        if key == "ModelArchitecture":
            return {"path": "model.py", "ipfs": "cidDEF"}
        raise KeyError(key)

    mock_get_manifest_key.side_effect = manifest_side_effect

    with pytest.raises(ManifestPathEscapesBaseError):
        aggregator.aggregate_t1(ctx, model_id=1, gi=None, submit=False, batch_id=None, packages_dir=None, no_cache=False)

    ctx.obj.ensure_file_exists.assert_not_called()


@patch("dincli.cli.auditor.get_manifest_key")
@patch("dincli.cli.auditor.get_cid_from_bytes32", return_value="cidLM")
def test_evaluate_lms_rejects_manifest_path_escape(mock_get_cid, mock_get_manifest_key):
    from dincli.cli import auditor

    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())

    coordinator = MagicMock()
    coordinator.functions.genesisModelIpfsHash.return_value.call.return_value = b"\x00" * 32
    task_auditor = MagicMock()
    task_auditor.functions.AuditorsBatchCount.return_value.call.return_value = 1
    # (batchId, auditors_in_batch, model_indexes, encrypted_cid_blob)
    task_auditor.functions.getAuditorsBatch.return_value.call.return_value = (0, [ACCOUNT], [0], b"\x00" * 16)
    task_auditor.functions.lmSubmissions.return_value.call.return_value = (ACCOUNT, b"\x00" * 32, 0, True, False, False, 0)
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = coordinator
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = task_auditor
    ctx.obj.get_current_gi_and_state.return_value = (1, "LMSevaluationStarted")
    ctx.obj.validate_gi_ET_curr_GI.return_value = 1
    ctx.obj.validate_GIstate_ET_given_GIstate.return_value = None
    ctx.obj.get_model_base_dir.return_value = Path("/tmp/dincli-test-auditor-model")

    def manifest_side_effect(network, key, model_id):
        if key == "requirements.txt":
            return {}
        if key == "Score_model_by_auditor":
            return {"path": "../../../../etc/passwd", "ipfs": "cidABC"}
        if key == "ModelArchitecture":
            return {"path": "model.py", "ipfs": "cidDEF"}
        raise KeyError(key)

    mock_get_manifest_key.side_effect = manifest_side_effect

    with pytest.raises(ManifestPathEscapesBaseError):
        auditor.evaluate_lms(ctx, model_id=1, lmi=None, batch=None, submit=False, gi=None, packages_dir=None, no_cache=False)

    # evaluate_lms legitimately calls ensure_file_exists once up front, to
    # refresh the (non-manifest-path-driven, hardcoded-subpath) genesis
    # model file -- that call is unrelated to this fix and must still
    # happen. What must NOT happen is a second call for the malicious
    # auditor/model/scoring service path, which would only be reached after
    # the resolve_manifest_path call this test is actually checking.
    ctx.obj.ensure_file_exists.assert_called_once()
    genesis_call_path = ctx.obj.ensure_file_exists.call_args[0][0]
    assert genesis_call_path == Path("/tmp/dincli-test-auditor-model") / "models" / "genesis_model.pth"


@patch("dincli.cli.modelownerd.auditor_batches.get_manifest_key")
def test_create_testdataset_rejects_manifest_path_escape(mock_get_manifest_key):
    ctx = MagicMock()
    account = MagicMock()
    account.address = ACCOUNT
    ctx.obj.get_en_w3_account_console.return_value = ("local", MagicMock(), account, MagicMock())

    coordinator = MagicMock()
    task_auditor = MagicMock()
    task_auditor.functions.AuditorsBatchCount.return_value.call.return_value = 1
    ctx.obj.get_deployed_din_task_coordinator_contract.return_value = coordinator
    ctx.obj.get_deployed_din_task_auditor_contract.return_value = task_auditor
    ctx.obj.get_current_gi_and_state.return_value = (1, "AuditorsBatchesCreated")
    ctx.obj.validate_gi_ET_curr_GI.return_value = 1
    ctx.obj.validate_GIstate_ET_given_GIstate.return_value = None
    ctx.obj.get_model_base_dir.return_value = Path("/tmp/dincli-test-modelowner-model")

    mock_get_manifest_key.return_value = {"path": "/etc/passwd", "ipfs": "cidABC"}

    with pytest.raises(ManifestPathEscapesBaseError):
        auditor_batches.create_testdataset(ctx, model_id=1, gi=None, submit=False, test_data_path=None)

    ctx.obj.ensure_file_exists.assert_not_called()


# ─── Task-contract artifact path (context.py) ───────────────────────────────

def test_resolve_task_contract_artifact_path_falls_back_on_escape(monkeypatch, tmp_path):
    ctx = _make_dincontext()
    ctx._resolved_network = "local"

    model_id = 1
    model_base_path = tmp_path / "local" / f"model_{model_id}"
    model_base_path.mkdir(parents=True)

    malicious_manifest = {
        "task_contracts": {
            "DINTaskCoordinator_Contract": {
                "artifact": {"path": "../../../../etc/passwd", "ipfs": "cidABC"},
            },
        },
    }

    monkeypatch.setattr("dincli.cli.context.get_manifest", lambda network, model_id=None: malicious_manifest)
    monkeypatch.setattr("dincli.cli.context.CACHE_DIR", tmp_path)

    with patch.object(ctx, "ensure_file_exists") as mock_ensure, \
         patch("dincli.cli.context.retrieve_from_ipfs") as mock_retrieve:
        result = ctx._resolve_task_contract_artifact_path(
            "DINTaskCoordinator_Contract",
            "DINTaskCoordinator.json",
            model_id,
            None,
        )
        # Falls back to the bundled default ABI rather than raising or
        # writing anywhere -- same graceful-degradation shape this function
        # already uses for every other malformed-manifest case.
        assert result.name == "DINTaskCoordinator.json"
        mock_ensure.assert_not_called()
        mock_retrieve.assert_not_called()
