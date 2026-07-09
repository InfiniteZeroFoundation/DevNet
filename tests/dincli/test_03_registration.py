"""
Phase 3 — Genesis model creation and model registration.

Model owner creates genesis model, submits to IPFS, requests registration.
DIN-Representative approves the registration and manifest update requests.

GI state at end of phase: GenesisModelCreated (index 4) after registration,
transitioning through AwaitingGenesisModel → GenesisModelCreated.

SDK candidates:
  create_task_dir(network, account)
  cache_default_artifacts(network, account)
  create_genesis_model(network, account, model_id)
  submit_genesis_model(network, account, model_id)
  submit_registration_request(network, account)
  approve_registration_request(network, din_rep_account, request_id)
  approve_manifest_update(network, din_rep_account, request_id)

Confirmation-prompt map (input_text reference):
  create-genesis-model    : 6 × y  (4 pre-check + 2 post-service-load)
  submit-genesis-model    : 2 × y  (1 pre-check + 1 blockchain confirm)
  validate-update-manifest: 3 × y  (coordinator + auditor + genesis-CID via typer.confirm)
  register-request        : 3 × y  (validate-manifest check + read-manifest check + proceed)
  update-manifest-request : 1 × y  (proceed on-chain)
"""

import pytest
from tests.dincli.constants import TORCHENV_PYTHON

pytestmark = pytest.mark.integration

# Expected GI state after genesis model is registered
GI_STATE_GENESIS_MODEL_CREATED = "GenesisModelCreated"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_model_owner_create_task_dir(run):
    """Create the per-task working directory.

    SDK candidate: create_task_dir(network, model_owner_account)
    """
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "task", "create-task-dir"])
    assert result.returncode == 0


def test_model_owner_cache_default_artifacts(run):
    """Fetch and cache default service files from IPFS.

    SDK candidate: cache_default_artifacts(network, model_owner_account)
    """
    result = run(["model-owner", "task", "cache-default-artifacts"], timeout=300)
    assert result.returncode == 0


def test_model_owner_create_genesis_model(run):
    """Create the genesis model weights locally.

    create-genesis-model prompts 6 times:
      1. Have you created task directory?
      2. Have you cached all artifacts?
      3. Have you edited all the artifacts?
      4. Have you updated the manifest with the new artifact CIDs?
      5. Have you edited/modified the modelowner service?
      6. Have you edited/modified the modelarchitecture service?

    SDK candidate: create_genesis_model(network, account)
    """
    result = run(
        ["model-owner", "model", "create-genesis-model"],
        python=TORCHENV_PYTHON,
        input_text="y\ny\ny\ny\ny\ny\n",
        timeout=300,
    )
    assert result.returncode == 0


def test_model_owner_add_default_test_data(run):
    """Add default test dataset for auditor evaluation."""
    result = run(["model-owner", "model", "add-default-test-data", "--default-test-data"])
    assert result.returncode == 0


def test_model_owner_submit_genesis_model(run):
    """Upload genesis model to IPFS and submit on-chain.

    submit-genesis-model prompts 2 times:
      1. Have you generated the genesis model?
      2. Do you want to submit to the blockchain?

    SDK candidate: submit_genesis_model(network, account)
    """
    result = run(
        ["model-owner", "model", "submit-genesis-model"],
        python=TORCHENV_PYTHON,
        input_text="y\ny\ny\n",  # 1: genesis created? 2: test dataset placed? 3: submit on-chain?
        timeout=300,
    )
    assert result.returncode == 0


def test_model_owner_validate_update_manifest(run):
    """Validate and update local manifest with fresh contract addresses and genesis CID.

    validate-update-manifest uses typer.confirm (3 times) when addresses/CIDs in
    the manifest differ from what is in .env (they always differ on a fresh deploy):
      1. Update DINTaskCoordinator_Contract to match .env?
      2. Update DINTaskAuditor_Contract to match .env?
      3. Update Genesis_Model_CID to match .env?
    """
    result = run(
        ["model-owner", "model", "validate-update-manifest"],
        input_text="y\ny\ny\n",
    )
    assert result.returncode == 0


def test_model_owner_submit_registration_request(run):
    """Submit the model registration request to the registry.

    register-request prompts 3 times:
      1. Have you run validate-update-manifest?
      2. Have you thoroughly read/modified all manifest parameters?
      3. Proceed with submitting on-chain?

    SDK candidate: submit_registration_request(network, account)
    """
    result = run(
        ["task", "model-owner", "register-request"],
        input_text="y\ny\ny\n",
        timeout=180,
    )
    assert result.returncode == 0


def test_din_rep_lists_pending_requests(run):
    """DIN-Representative can see the pending registration request."""
    run(["system", "connect-wallet", "--account", "0"])
    result = run(["dindao", "registry", "list-pending-requests"])
    assert result.returncode == 0


def test_din_rep_explores_registration_request(run):
    """DIN-Representative inspects request 0 (model type)."""
    result = run(["dindao", "registry", "explore-request", "0", "-t", "model"])
    assert result.returncode == 0


def test_din_rep_approves_registration_request(run, state):
    """DIN-Representative approves model registration request 0.

    SDK candidate: approve_registration_request(network, account, request_id)
    """
    result = run(["dindao", "registry", "approve-registration-request", "0"])
    assert result.returncode == 0
    state["model_id"] = 0


def test_model_owner_checks_request_status(run):
    """Model owner confirms their request was approved."""
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["task", "model-owner", "my-requests", "--ip"])
    assert result.returncode == 0


def test_model_owner_shows_registration_request(run):
    result = run(["task", "model-owner", "show-registration-request", "0"])
    assert result.returncode == 0


def test_task_explore_model0(run):
    """Explore model 0 — confirms it is registered and visible."""
    result = run(["task", "explore", "0"])
    assert result.returncode == 0


def test_model_owner_update_manifest_request(run, din_tmp):
    """Model owner submits a manifest update request after registration.

    In a real flow the model owner would update service CIDs in the manifest
    before requesting an update.  Here we add a harness marker field so the
    manifest gets a new IPFS CID (otherwise the CLI correctly reports
    "no update needed" and exits 1).

    update-manifest-request prompts 1 time:
      1. Proceed with submitting the manifest update request on-chain?

    SDK candidate: submit_manifest_update_request(network, account, model_id)
    """
    import json as _json

    manifest_path = din_tmp / "cache" / "dincli" / "local" / "model_0" / "manifest.json"
    if manifest_path.exists():
        data = _json.loads(manifest_path.read_text())
        data["_harness_update_marker"] = "1"
        manifest_path.write_text(_json.dumps(data, indent=4))

    result = run(
        ["task", "model-owner", "update-manifest-request", "0"],
        input_text="y\n",
        timeout=180,
    )
    assert result.returncode == 0


def test_din_rep_lists_manifest_requests(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["dindao", "registry", "list-pending-requests"])
    assert result.returncode == 0


def test_din_rep_explores_manifest_request(run):
    run(["system", "connect-wallet", "--account", "0"])
    result = run(["dindao", "registry", "explore-request", "0", "-t", "manifest"])
    assert result.returncode == 0


def test_din_rep_approves_manifest_update(run):
    """DIN-Representative approves manifest update request 0.

    SDK candidate: approve_manifest_update(network, account, request_id)
    """
    result = run(["dindao", "registry", "approve-manifest-update", "0"])
    assert result.returncode == 0
