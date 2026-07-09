"""
Phase 4 — Complete Global Iteration (GI).

Drives a full GI lifecycle for model 0:
  GI start → aggregator registration → auditor registration →
  LMS open → client training + submission → LMS close →
  auditor batches → LMS evaluation → aggregation T1+T2 →
  slash → GI end

Expected final state: GIended (index 22).

Account map:
  0    = DIN-Representative
  1    = model owner
  2–10 = clients (9 accounts; account 3 is skipped — matches task description)
  11–22 = aggregators (12 accounts)
  50–58 = auditors (9 accounts)

Confirmation-prompt map (input_text reference):
  model-owner gi start        : 1 × y  (test dataset for GM evaluation)
  client train-lms            : 3 × y  (dataset placed? confirm containerised training × 2)
  model-owner slash auditors  : 1 × y  (only if tier2_score == 0; pass extra y to be safe)
  model-owner slash aggregators: 1 × y (same guard)

SDK candidates:
  start_gi(network, account, model_id)
  register_aggregator(network, account, model_id)
  register_auditor(network, account, model_id)
  open_lms / close_lms(network, account, model_id)
  train_and_submit_lm(network, account, model_id)
  create_auditor_batches(network, account, model_id)
  start_lms_evaluation / close_lms_evaluation(network, account, model_id)
  evaluate_lms(network, account, model_id)
  start_t1_aggregation / close_t1_aggregation(network, account, model_id)
  aggregate_t1(network, account, model_id)
  start_t2_aggregation / close_t2_aggregation(network, account, model_id)
  aggregate_t2(network, account, model_id)
  slash_auditors / slash_aggregators(network, account, model_id)
  end_gi(network, account, model_id)
"""

import pytest
from tests.dincli.constants import TORCHENV_PYTHON

pytestmark = pytest.mark.integration

MODEL_ID = "0"

AGGREGATOR_ACCOUNTS = list(range(11, 23))   # 11..22 inclusive
AUDITOR_ACCOUNTS    = list(range(50, 59))   # 50..58 inclusive
CLIENT_ACCOUNTS     = list(range(2, 11))  # 2, 4..10 (account 3 is skipped per task)


def _gi_state(run) -> str:
    result = run(["task", "gi", "show-state", MODEL_ID], check=False)
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and not line.startswith("["):
            return line
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# GI setup
# ---------------------------------------------------------------------------


def test_show_initial_gi_state(run):
    """Confirm model 0 GI state before starting."""
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["task", "gi", "show-state", MODEL_ID])
    assert result.returncode == 0


def test_add_default_test_data_for_gi(run):
    """Add default test data tied to model 0 for auditor evaluation."""
    result = run([
        "model-owner", "model", "add-default-test-data",
        "--default-test-data", "--model-id", MODEL_ID,
    ])
    assert result.returncode == 0


def test_gi_start(run):
    """Model owner starts GI for model 0.

    gi start prompts 1 time when pass-scoring is enabled:
      1. Have you placed the test dataset for GM evaluation?

    SDK candidate: start_gi(network, account, model_id)
    """
    result = run(
        ["model-owner", "gi", "start", MODEL_ID],
        python=TORCHENV_PYTHON,
        input_text="y\n",
    )
    assert result.returncode == 0


def test_gi_aggregators_open(run):
    """Open aggregator registration window.

    SDK candidate: open_aggregator_registration(network, account, model_id)
    """
    result = run(["model-owner", "gi", "reg", "aggregators-open", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Aggregator registration (accounts 11–22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_register(run, acc):
    """Each aggregator buys tokens, stakes, and registers for model 0.

    SDK candidate: register_aggregator(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["aggregator", "dintoken", "buy", "0.00001"])
    run(["aggregator", "dintoken", "stake", "10"])
    run(["aggregator", "dintoken", "read-stake"])
    result = run(["aggregator", "register", MODEL_ID])
    assert result.returncode == 0


def test_show_registered_aggregators(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "gi", "show-registered-aggregators", MODEL_ID])
    assert result.returncode == 0


def test_gi_aggregators_close(run):
    """Close aggregator registration.

    SDK candidate: close_aggregator_registration(network, account, model_id)
    """
    result = run(["model-owner", "gi", "reg", "aggregators-close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Auditor registration (accounts 50–58)
# ---------------------------------------------------------------------------


def test_gi_auditors_open(run):
    result = run(["model-owner", "gi", "reg", "auditors-open", MODEL_ID])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AUDITOR_ACCOUNTS)
def test_auditor_register(run, acc):
    """Each auditor buys tokens, stakes, and registers for model 0.

    SDK candidate: register_auditor(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["auditor", "dintoken", "buy", "0.00001"])
    run(["auditor", "dintoken", "stake", "10"])
    run(["auditor", "dintoken", "read-stake"])
    result = run(["auditor", "register", MODEL_ID])
    assert result.returncode == 0


def test_show_registered_auditors(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "gi", "show-registered-auditors", MODEL_ID])
    assert result.returncode == 0


def test_gi_auditors_close(run):
    result = run(["model-owner", "gi", "reg", "auditors-close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# LMS — Local Model Submission
# ---------------------------------------------------------------------------


def test_lms_open(run):
    """Open LMS window.

    SDK candidate: open_lms(network, account, model_id)
    """
    result = run(["model-owner", "lms", "open", MODEL_ID])
    assert result.returncode == 0


def test_distribute_mnist(run):
    """Distribute MNIST dataset shards to 9 clients."""
    result = run([
        "system", "dataset", "distribute-mnist",
        "--seed", "42",
        "--clients", "--test-train",
        "--num-clients", "9",
        "--model-id", MODEL_ID,
    ], python=TORCHENV_PYTHON, input_text="y\n", timeout=300)
    assert result.returncode == 0


@pytest.mark.parametrize("acc", CLIENT_ACCOUNTS)
def test_client_train_and_submit(run, acc):
    """Each client trains on their local shard and submits.

    train-lms prompts 3 times:
      1. Have you placed your client dataset?
      2. Are you sure the dataset is updated? (only reached if dataset exists)
      3. Starting training using containerised service. Do you want to continue?

    SDK candidate: train_and_submit_lm(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["client", "create-client-dataset-dir", MODEL_ID])
    run(
        ["client", "train-lms", MODEL_ID, "--packages-dir", "/home/azureuser/my_venvs/torchenv/lib/python3.12/site-packages", "--no-cache"],
        python=TORCHENV_PYTHON,
        input_text="y\ny\ny\n",
        timeout=300,
    )
    result = run(
        ["client", "submit-lm", MODEL_ID],
        python=TORCHENV_PYTHON,
        timeout=180,
    )
    assert result.returncode == 0


def test_lms_close(run):
    """Close LMS window.

    SDK candidate: close_lms(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "lms", "close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Auditor batches + LMS evaluation
# ---------------------------------------------------------------------------


def test_create_auditor_batches(run):
    """Assign submitted LMs to auditor batches.

    SDK candidate: create_auditor_batches(network, account, model_id)
    """
    result = run(["model-owner", "auditor-batches", "create", MODEL_ID])
    assert result.returncode == 0


def test_show_auditor_batches(run):
    result = run(["model-owner", "auditor-batches", "show", MODEL_ID])
    assert result.returncode == 0


def test_create_testdataset_and_submit(run):
    """Upload the test dataset for auditor scoring."""
    result = run([
        "model-owner", "auditor-batches", "create-testdataset", MODEL_ID, "--submit",
    ], python=TORCHENV_PYTHON, timeout=300)
    assert result.returncode == 0


def test_lms_evaluation_start(run):
    """Open LMS evaluation window.

    SDK candidate: start_lms_evaluation(network, account, model_id)
    """
    result = run(["model-owner", "lms-evaluation", "start", MODEL_ID])
    assert result.returncode == 0


def test_show_lms_evaluation(run):
    result = run(["model-owner", "lms-evaluation", "show", MODEL_ID])
    assert result.returncode == 0


def test_show_lms_evaluation_auditors_and_models(run):
    result = run(["model-owner", "lms-evaluation", "show", MODEL_ID, "--auditors", "--models"])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AUDITOR_ACCOUNTS)
def test_auditor_evaluate(run, acc):
    """Each auditor evaluates their batch and submits scores.

    SDK candidate: evaluate_lms_batch(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["auditor", "lms-evaluation", "show-batch", MODEL_ID])
    result = run(
        [
            "auditor", "lms-evaluation", "evaluate", MODEL_ID, "--submit",
            "--packages-dir", "/home/azureuser/my_venvs/torchenv/lib/python3.12/site-packages", "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0


def test_show_lms_evaluation_models_after(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "lms-evaluation", "show", MODEL_ID, "--models"])
    assert result.returncode == 0


def test_lms_evaluation_close(run):
    """Close LMS evaluation window.

    SDK candidate: close_lms_evaluation(network, account, model_id)
    """
    result = run(["model-owner", "lms-evaluation", "close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T1 aggregation
# ---------------------------------------------------------------------------


def test_create_t1nt2_batches(run):
    """Create T1 and T2 aggregation batches.

    SDK candidate: create_aggregation_batches(network, account, model_id)
    """
    result = run(["model-owner", "aggregation", "create-t1nt2-batches", MODEL_ID])
    assert result.returncode == 0


def test_show_t1_batches_before_agg(run):
    result = run(["model-owner", "aggregation", "show-t1-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_show_t2_batches_before_agg(run):
    result = run(["model-owner", "aggregation", "show-t2-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_t1_aggregation_start(run):
    """Open T1 aggregation window.

    SDK candidate: start_t1_aggregation(network, account, model_id)
    """
    result = run(["model-owner", "aggregation", "T1", "start", MODEL_ID])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_aggregate_t1(run, acc):
    """Each aggregator processes their T1 batch and submits.

    SDK candidate: aggregate_t1(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["aggregator", "show-t1-batches", MODEL_ID, "--detailed"])
    result = run(
        [
            "aggregator", "aggregate-t1", MODEL_ID, "--submit",
            "--packages-dir", "/home/azureuser/my_venvs/torchenv/lib/python3.12/site-packages", "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0


def test_show_t1_batches_after_agg(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "aggregation", "show-t1-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_t1_aggregation_close(run):
    """Close T1 aggregation.

    SDK candidate: close_t1_aggregation(network, account, model_id)
    """
    result = run(["model-owner", "aggregation", "T1", "close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# T2 aggregation
# ---------------------------------------------------------------------------


def test_t2_aggregation_start(run):
    result = run(["model-owner", "aggregation", "T2", "start", MODEL_ID])
    assert result.returncode == 0


def test_show_gi_state_t2(run):
    result = run(["task", "gi", "show-state", MODEL_ID])
    assert result.returncode == 0


def test_show_t2_batches(run):
    result = run(["model-owner", "aggregation", "show-t2-batches", MODEL_ID])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_aggregate_t2(run, acc):
    """Each aggregator processes their T2 batch and submits.

    SDK candidate: aggregate_t2(network, account, model_id)
    """
    run(["system", "connect-wallet", "--account", str(acc)])
    run(["aggregator", "show-t2-batches", MODEL_ID, "--detailed"])
    result = run(
        [
            "aggregator", "aggregate-t2", MODEL_ID, "--submit",
            "--packages-dir", "/home/azureuser/my_venvs/torchenv/lib/python3.12/site-packages", "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0


def test_show_t2_batches_after_agg(run):
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["model-owner", "aggregation", "show-t2-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_t2_aggregation_close(run):
    """Close T2 aggregation.

    SDK candidate: close_t2_aggregation(network, account, model_id)
    """
    result = run(["model-owner", "aggregation", "T2", "close", MODEL_ID])
    assert result.returncode == 0


# ---------------------------------------------------------------------------
# Slashing + GI end
# ---------------------------------------------------------------------------


def test_slash_auditors(run):
    """Slash under-performing auditors.

    slash auditors may prompt 1 time if tier2_score == 0:
      1. Tier 2 score reads as 0. Are you sure you want to continue?

    SDK candidate: slash_auditors(network, account, model_id)
    """
    result = run(
        ["model-owner", "slash", "auditors", MODEL_ID],
        input_text="y\n",
    )
    assert result.returncode == 0


def test_slash_aggregators(run):
    """Slash under-performing aggregators.

    SDK candidate: slash_aggregators(network, account, model_id)
    """
    result = run(
        ["model-owner", "slash", "aggregators", MODEL_ID],
        input_text="y\n",
    )
    assert result.returncode == 0


def test_gi_end(run):
    """End GI for model 0.

    SDK candidate: end_gi(network, account, model_id)
    """
    result = run(["model-owner", "gi", "end", MODEL_ID])
    assert result.returncode == 0


def test_gi_final_state_is_ended(run):
    """Assert final GI state is GIended (index 22) — the key regression gate."""
    run(["system", "connect-wallet", "--account", "1"])
    result = run(["task", "gi", "show-state", MODEL_ID])
    assert result.returncode == 0
    assert "GIended" in result.stdout or "22" in result.stdout, (
        f"Expected GIended state, got:\n{result.stdout}"
    )
