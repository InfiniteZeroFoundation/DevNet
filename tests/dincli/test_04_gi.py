"""
Phase 4 — one complete Global Iteration (GI) on the foundry task contracts.

Walks GI 1 of model 0 end to end (task_061026_21 Part D, Decision 3) and
asserts the GI state by name after every phase:

  1. fund GI 1 (rewards deposit)          → gi start              GIstarted
  2. aggregator / auditor registration (+ auditor encryption keys;
     an aggregator registering as an auditor is refused)
  3. LMS → auditor lock-seed               AuditSeedLocked
         → auditor-batches create          AuditorsBatchesCreated
         → create-testdataset --submit     AuditTestDataAssigned
  4. lms-evaluation start → evaluate --submit → start-reveal → reveal → close
  5. aggregator lock-seed                  AggSeedLocked
         → create-t1nt2-batches            T1nT2Bcreated
  6. T1 start → aggregate-t1 --submit → start-reveal → reveal-t1 → close;
     the same for T2; then T2 set-score
  7. slash auditors → slash aggregators → gi end                GIended
  8. rewards claim + withdraw for one client, one auditor and one
     aggregator (DIN balance rises) → gi release-slots

Account map (anvil, 70 accounts):
  0    = DIN-Representative
  1    = model owner
  2–10 = clients (9 accounts)
  11–22 = aggregators (12 accounts)
  50–58 = auditors (9 accounts)

Confirmation-prompt map (input_text reference):
  model-owner gi start         : 1 × y  (test dataset for GM evaluation)
  client train-lms             : 3 × y  (dataset placed? confirm containerised training × 2)
  model-owner slash auditors   : 1 × y  (only if tier2_score == 0; pass extra y to be safe)
  model-owner slash aggregators: 1 × y  (same guard)
"""

import json
import re

import pytest
from eth_account import Account
from web3 import Web3

from tests.dincli.constants import (
    DEVNET_ROOT,
    DIN_INFO_PATH,
    HARDHAT_RPC,
    TORCHENV_PYTHON,
    TORCHENV_SITE_PACKAGES,
)
from tests.dincli.demo import DEMO_MNEMONIC

MODEL_ID = "0"
GI = "1"

AGGREGATOR_ACCOUNTS = list(range(11, 23))   # 11..22 inclusive
AUDITOR_ACCOUNTS    = list(range(50, 59))   # 50..58 inclusive
CLIENT_ACCOUNTS     = list(range(2, 11))    # 2..10 inclusive

REWARD_DEPOSIT_DIN = "50"
MODEL_OWNER_DIN_BUY_ETH = "0.001"

_BALANCE_OF_ABI = [{
    "inputs": [{"name": "account", "type": "address"}],
    "name": "balanceOf",
    "outputs": [{"name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function",
}]


def _gi_state(run) -> str:
    """The GI state name printed by `task gi show-state` ("Global iteration state: <name>")."""
    result = run(["task", "gi", "show-state", MODEL_ID])
    match = re.search(r"Global iteration state:\s*(\w+)", result.stdout)
    assert match, f"No GI state in show-state output:\n{result.stdout}"
    return match.group(1)


def _assert_state(run, expected: str) -> None:
    actual = _gi_state(run)
    assert actual == expected, f"Expected GI state {expected}, got {actual}"


def _address(acc: int) -> str:
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(DEMO_MNEMONIC, account_path=f"m/44'/60'/0'/0/{acc}").address


def _task_coordinator(state):
    """The model's DINTaskCoordinator (deployed in test_02) and a web3 handle."""
    address = state.get("task_coordinator_address")
    assert address, "task_coordinator_address not set; run the suite from test_01"
    abi = json.loads((DEVNET_ROOT / "dincli" / "abis" / "DINTaskCoordinator.json").read_text(encoding="utf-8"))["abi"]
    w3 = Web3(Web3.HTTPProvider(HARDHAT_RPC))
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi), w3


def _revealers(contract, w3, event_name: str) -> set:
    """{(batchId, aggregator)} from T{1,2}AggregationSubmitted (emitted on reveal) for GI.

    Raw eth_getLogs filter: web3 6 and 7 name the get_logs keywords differently.
    """
    event = getattr(contract.events, event_name)()
    signature = f"{event_name}({','.join(i['type'] for i in event.abi['inputs'])})"
    # HexBytes.hex() has a 0x prefix on web3 6 and none on web3 7.
    event_topic = "0x" + Web3.keccak(text=signature).hex().removeprefix("0x")
    gi_topic = "0x" + int(GI).to_bytes(32, "big").hex()
    raw = w3.eth.get_logs({
        "address": contract.address,
        "fromBlock": 0,
        "toBlock": "latest",
        "topics": [event_topic, gi_topic],
    })
    return {(log.args.batchId, log.args.aggregator) for log in map(event.process_log, raw)}


def _din_balance(acc: int) -> int:
    token = json.loads(DIN_INFO_PATH.read_text(encoding="utf-8"))["local"]["token"]
    w3 = Web3(Web3.HTTPProvider(HARDHAT_RPC))
    contract = w3.eth.contract(address=Web3.to_checksum_address(token), abi=_BALANCE_OF_ABI)
    return contract.functions.balanceOf(_address(acc)).call()


# ---------------------------------------------------------------------------
# GI setup
# ---------------------------------------------------------------------------


def test_show_initial_gi_state(run):
    """Confirm model 0 GI state before starting."""
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["task", "gi", "show-state", MODEL_ID])
    assert result.returncode == 0


def test_add_default_test_data_for_gi(run):
    """Add default test data tied to model 0 for auditor evaluation."""
    result = run([
        "model-owner", "model", "add-default-test-data",
        "--default-test-data", "--model-id", MODEL_ID,
    ])
    assert result.returncode == 0


def _assert_no_failures(result):
    """A command that skips its work (✗ lines, failed txs) can still exit 0."""
    assert "✗" not in result.stdout, result.stdout
    assert "failed" not in result.stdout.lower(), result.stdout


def test_fund_gi_reward_pool(run):
    """Step 1: the model owner buys DIN and deposits it into GI 1's reward pool.

    `gi start` refuses an unfunded GI. The deposit needs `setDinToken` on
    DINTaskAuditor, which `model-owner deploy task-auditor` sends.
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    run(["dintoken", "buy", MODEL_OWNER_DIN_BUY_ETH])
    result = run(["model-owner", "rewards", "deposit", MODEL_ID, "--amount", REWARD_DEPOSIT_DIN])
    assert result.returncode == 0
    assert f"GI {GI} reward pool" in result.stdout


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
    _assert_state(run, "GIstarted")


def test_gi_aggregators_open(run):
    """Open aggregator registration window.

    SDK candidate: open_aggregator_registration(network, account, model_id)
    """
    result = run(["model-owner", "gi", "reg", "aggregators-open", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "DINaggregatorsRegistrationStarted")


# ---------------------------------------------------------------------------
# Aggregator registration (accounts 11–22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_register(run, acc):
    """Each aggregator buys tokens, stakes, and registers for model 0.

    SDK candidate: register_aggregator(network, account, model_id)
    """
    # --demokey <idx> (demo-mode-only global flag) signs each command with the
    # dev key directly — no per-account register/connect round-trip.
    run(["--demokey", str(acc), "aggregator", "dintoken", "buy", "0.00001"])
    run(["--demokey", str(acc), "aggregator", "dintoken", "stake", "10"])
    run(["--demokey", str(acc), "aggregator", "dintoken", "read-stake"])
    result = run(["--demokey", str(acc), "aggregator", "register", MODEL_ID])
    assert result.returncode == 0


def test_show_registered_aggregators(run):
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "gi", "show-registered-aggregators", MODEL_ID])
    assert result.returncode == 0


def test_gi_aggregators_close(run):
    """Close aggregator registration.

    SDK candidate: close_aggregator_registration(network, account, model_id)
    """
    result = run(["model-owner", "gi", "reg", "aggregators-close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "DINaggregatorsRegistrationClosed")


# ---------------------------------------------------------------------------
# Auditor registration (accounts 50–58)
# ---------------------------------------------------------------------------


def test_gi_auditors_open(run):
    result = run(["model-owner", "gi", "reg", "auditors-open", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "DINauditorsRegistrationStarted")


@pytest.mark.parametrize("acc", AUDITOR_ACCOUNTS)
def test_auditor_register(run, acc):
    """Each auditor buys tokens, stakes, and registers for model 0.

    SDK candidate: register_auditor(network, account, model_id)
    """
    run(["--demokey", str(acc), "auditor", "dintoken", "buy", "0.00001"])
    run(["--demokey", str(acc), "auditor", "dintoken", "stake", "10"])
    run(["--demokey", str(acc), "auditor", "dintoken", "read-stake"])
    result = run(["--demokey", str(acc), "auditor", "register", MODEL_ID])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AUDITOR_ACCOUNTS)
def test_auditor_register_encryption_key(run, acc):
    """Each auditor registers an X25519 key. create-testdataset --submit refuses keyless auditors."""
    result = run(["--demokey", str(acc), "auditor", "register-encryption-key"])
    assert result.returncode == 0


def test_aggregator_cannot_register_as_auditor(run):
    """task_061026_20 Part B (#180): an aggregator of this GI can't also be an auditor."""
    result = run(
        ["--demokey", str(AGGREGATOR_ACCOUNTS[0]), "auditor", "register", MODEL_ID],
        check=False,
    )
    assert result.returncode != 0, f"Dual-role registration was not refused:\n{result.stdout}"


def test_show_registered_auditors(run):
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "gi", "show-registered-auditors", MODEL_ID])
    assert result.returncode == 0


def test_gi_auditors_close(run):
    result = run(["model-owner", "gi", "reg", "auditors-close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "DINauditorsRegistrationClosed")


# ---------------------------------------------------------------------------
# LMS — Local Model Submission
# ---------------------------------------------------------------------------


def test_lms_open(run):
    """Open LMS window.

    SDK candidate: open_lms(network, account, model_id)
    """
    result = run(["model-owner", "lms", "open", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "LMSstarted")


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
    run(["--demokey", str(acc), "client", "create-client-dataset-dir", MODEL_ID])
    run(
        ["--demokey", str(acc), "client", "train-lms", MODEL_ID, "--packages-dir", TORCHENV_SITE_PACKAGES, "--no-cache"],
        python=TORCHENV_PYTHON,
        input_text="y\ny\ny\n",
        timeout=300,
    )
    result = run(
        ["--demokey", str(acc), "client", "submit-lm", MODEL_ID],
        python=TORCHENV_PYTHON,
        timeout=180,
    )
    assert result.returncode == 0


def test_lms_close(run):
    """Close LMS window.

    SDK candidate: close_lms(network, account, model_id)
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "lms", "close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "LMSclosed")


# ---------------------------------------------------------------------------
# Auditor batches + LMS evaluation
# ---------------------------------------------------------------------------


def test_auditor_lock_seed(run):
    """An auditor (permissionless) locks the auditor batch-assignment seed once its block is mined."""
    result = run(["--demokey", str(AUDITOR_ACCOUNTS[0]), "auditor", "lock-seed", MODEL_ID], timeout=180)
    assert result.returncode == 0
    run(["system", "connect-demo-wallet", "modelowner"])
    _assert_state(run, "AuditSeedLocked")


def test_create_auditor_batches(run):
    """Assign submitted LMs to auditor batches.

    SDK candidate: create_auditor_batches(network, account, model_id)
    """
    result = run(["model-owner", "auditor-batches", "create", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "AuditorsBatchesCreated")


def test_show_auditor_batches(run):
    result = run(["model-owner", "auditor-batches", "show", MODEL_ID])
    assert result.returncode == 0


def test_create_testdataset_and_submit(run):
    """Upload the test dataset for auditor scoring."""
    result = run([
        "model-owner", "auditor-batches", "create-testdataset", MODEL_ID, "--submit",
    ], python=TORCHENV_PYTHON, timeout=300)
    assert result.returncode == 0
    _assert_state(run, "AuditTestDataAssigned")


def test_lms_evaluation_start(run):
    """Open LMS evaluation window.

    SDK candidate: start_lms_evaluation(network, account, model_id)
    """
    result = run(["model-owner", "lms-evaluation", "start", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "LMSevaluationStarted")


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
    run(["--demokey", str(acc), "auditor", "lms-evaluation", "show-batch", MODEL_ID])
    result = run(
        [
            "--demokey", str(acc), "auditor", "lms-evaluation", "evaluate", MODEL_ID, "--submit",
            "--packages-dir", TORCHENV_SITE_PACKAGES, "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0
    _assert_no_failures(result)


def test_show_lms_evaluation_models_after(run):
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "lms-evaluation", "show", MODEL_ID, "--models"])
    assert result.returncode == 0


def test_lms_evaluation_start_reveal(run):
    """Close the commit window and open the reveal window."""
    result = run(["model-owner", "lms-evaluation", "start-reveal", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "LMSevaluationRevealStarted")


@pytest.mark.parametrize("acc", AUDITOR_ACCOUNTS)
def test_auditor_reveal(run, acc):
    """Each auditor reveals the scores it committed (from its own per-wallet commit cache)."""
    result = run(["--demokey", str(acc), "auditor", "lms-evaluation", "reveal", MODEL_ID])
    assert result.returncode == 0
    _assert_no_failures(result)
    # Every LM in this auditor's batch must have a commit to reveal.
    assert "No local commit found for LM" not in result.stdout, result.stdout


def test_lms_evaluation_close(run):
    """Close LMS evaluation window.

    SDK candidate: close_lms_evaluation(network, account, model_id)
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "lms-evaluation", "close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "LMSevaluationClosed")


# ---------------------------------------------------------------------------
# T1 aggregation
# ---------------------------------------------------------------------------


def test_aggregator_lock_seed(run):
    """An aggregator (permissionless) locks the T1/T2 batch-assignment seed once its block is mined."""
    result = run(["--demokey", str(AGGREGATOR_ACCOUNTS[0]), "aggregator", "lock-seed", MODEL_ID], timeout=180)
    assert result.returncode == 0
    run(["system", "connect-demo-wallet", "modelowner"])
    _assert_state(run, "AggSeedLocked")


def test_create_t1nt2_batches(run):
    """Create T1 and T2 aggregation batches.

    SDK candidate: create_aggregation_batches(network, account, model_id)
    """
    result = run(["model-owner", "aggregation", "create-t1nt2-batches", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T1nT2Bcreated")


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
    _assert_state(run, "T1AggregationStarted")


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_aggregate_t1(run, acc):
    """Each aggregator processes their T1 batch and submits.

    SDK candidate: aggregate_t1(network, account, model_id)
    """
    run(["--demokey", str(acc), "aggregator", "show-t1-batches", MODEL_ID, "--detailed"])
    result = run(
        [
            "--demokey", str(acc), "aggregator", "aggregate-t1", MODEL_ID, "--submit",
            "--packages-dir", TORCHENV_SITE_PACKAGES, "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0
    _assert_no_failures(result)


def test_show_t1_batches_after_agg(run):
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "aggregation", "show-t1-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_t1_aggregation_start_reveal(run):
    result = run(["model-owner", "aggregation", "T1", "start-reveal", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T1AggregationRevealStarted")


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_reveal_t1(run, acc):
    """Each aggregator reveals its T1 commits (a no-op for one outside every T1 batch)."""
    result = run(["--demokey", str(acc), "aggregator", "reveal-t1", MODEL_ID])
    assert result.returncode == 0
    _assert_no_failures(result)
    # reveal-t1 checks the seat before the cache: a seated aggregator with no
    # local commit prints this and sends nothing.
    assert "No local commit found for T1 batch" not in result.stdout, result.stdout


def test_every_seated_t1_aggregator_revealed(state):
    """Every aggregator seated in a T1 batch revealed on-chain.

    A T1 batch can finalize on 2 of 3 reveals, so reaching GIended alone
    doesn't catch a missed reveal.
    """
    contract, w3 = _task_coordinator(state)
    revealed = _revealers(contract, w3, "T1AggregationSubmitted")
    count = contract.functions.tier1BatchCount(int(GI)).call()
    assert count > 0, "No T1 batches were created"
    for bid in range(count):
        _, validators, _, _, _ = contract.functions.getTier1Batch(int(GI), bid).call()
        missing = [v for v in validators if (bid, v) not in revealed]
        assert not missing, f"T1 batch {bid}: seated aggregators never revealed: {missing}"


def test_t1_aggregation_close(run):
    """Close T1 aggregation.

    SDK candidate: close_t1_aggregation(network, account, model_id)
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "aggregation", "T1", "close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T1AggregationDone")


# ---------------------------------------------------------------------------
# T2 aggregation
# ---------------------------------------------------------------------------


def test_t2_aggregation_start(run):
    result = run(["model-owner", "aggregation", "T2", "start", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T2AggregationStarted")


def test_show_t2_batches(run):
    result = run(["model-owner", "aggregation", "show-t2-batches", MODEL_ID])
    assert result.returncode == 0


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_aggregate_t2(run, acc):
    """Each aggregator processes their T2 batch and submits.

    SDK candidate: aggregate_t2(network, account, model_id)
    """
    run(["--demokey", str(acc), "aggregator", "show-t2-batches", MODEL_ID, "--detailed"])
    result = run(
        [
            "--demokey", str(acc), "aggregator", "aggregate-t2", MODEL_ID, "--submit",
            "--packages-dir", TORCHENV_SITE_PACKAGES, "--no-cache",
        ],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0
    _assert_no_failures(result)


def test_show_t2_batches_after_agg(run):
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "aggregation", "show-t2-batches", MODEL_ID, "--detailed"])
    assert result.returncode == 0


def test_t2_aggregation_start_reveal(run):
    result = run(["model-owner", "aggregation", "T2", "start-reveal", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T2AggregationRevealStarted")


@pytest.mark.parametrize("acc", AGGREGATOR_ACCOUNTS)
def test_aggregator_reveal_t2(run, acc):
    """Each aggregator reveals its T2 commit (a no-op for one outside the T2 batch)."""
    result = run(["--demokey", str(acc), "aggregator", "reveal-t2", MODEL_ID])
    assert result.returncode == 0
    _assert_no_failures(result)
    assert "No local commit found for T2 batch" not in result.stdout, result.stdout


def test_every_seated_t2_aggregator_revealed(state):
    """Every aggregator seated in the T2 batch revealed on-chain."""
    contract, w3 = _task_coordinator(state)
    revealed = _revealers(contract, w3, "T2AggregationSubmitted")
    _, aggregators, _, _ = contract.functions.getTier2Batch(int(GI), 0).call()
    missing = [a for a in aggregators if (0, a) not in revealed]
    assert not missing, f"T2 batch: seated aggregators never revealed: {missing}"


def test_t2_aggregation_close(run):
    """Close T2 aggregation.

    SDK candidate: close_t2_aggregation(network, account, model_id)
    """
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "aggregation", "T2", "close", MODEL_ID])
    assert result.returncode == 0
    _assert_state(run, "T2AggregationDone")


def test_t2_set_score(run):
    """Score the final GM on the owner's test data and record it on-chain."""
    result = run(
        ["model-owner", "aggregation", "T2", "set-score", MODEL_ID],
        python=TORCHENV_PYTHON,
        timeout=300,
    )
    assert result.returncode == 0
    assert "Tier 2 score set" in result.stdout


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
    _assert_state(run, "AuditorsSlashed")


def test_slash_aggregators(run):
    """Slash under-performing aggregators.

    SDK candidate: slash_aggregators(network, account, model_id)
    """
    result = run(
        ["model-owner", "slash", "aggregators", MODEL_ID],
        input_text="y\n",
    )
    assert result.returncode == 0
    _assert_state(run, "AggregatorsSlashed")


def test_gi_end(run):
    """End GI for model 0.

    SDK candidate: end_gi(network, account, model_id)
    """
    result = run(["model-owner", "gi", "end", MODEL_ID])
    assert result.returncode == 0


def test_gi_final_state_is_ended(run):
    """The GI ends in GIended (ordinal 28) — the key regression gate."""
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["task", "gi", "show-state", MODEL_ID])
    assert "Global iteration state: GIended" in result.stdout, result.stdout
    assert "Global iteration numerical state: 28" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# Rewards + release slots
# ---------------------------------------------------------------------------


def _claim_and_withdraw(run, acc) -> bool:
    """Claim and withdraw GI 1's reward for `acc`; True if its DIN balance rose."""
    before = _din_balance(acc)
    claim = run(["--demokey", str(acc), "rewards", "claim", MODEL_ID, "--gi", GI], check=False)
    if claim.returncode != 0:
        return False
    withdraw = run(["--demokey", str(acc), "rewards", "withdraw", MODEL_ID], check=False)
    return withdraw.returncode == 0 and _din_balance(acc) > before


@pytest.mark.parametrize("role,accounts", [
    ("client", CLIENT_ACCOUNTS),
    ("auditor", AUDITOR_ACCOUNTS),
    ("aggregator", AGGREGATOR_ACCOUNTS),
])
def test_reward_claim_and_withdraw(run, role, accounts):
    """One participant of each role claims and withdraws GI 1's reward, and its DIN balance rises.

    Tries the role's accounts in order: a participant whose work was rejected
    or slashed, or that sat outside every batch, has no share.
    """
    for acc in accounts:
        if _claim_and_withdraw(run, acc):
            return
    pytest.fail(f"No {role} in {accounts} could claim and withdraw a GI {GI} reward")


def test_gi_release_slots(run):
    """Release the ended GI's validator registration slots (once per GI)."""
    run(["system", "connect-demo-wallet", "modelowner"])
    result = run(["model-owner", "gi", "release-slots", MODEL_ID, "--gi", GI])
    assert result.returncode == 0
