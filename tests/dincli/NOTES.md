# dincli Test Harness — SDK Candidate Notes

This file maps the test phases to their SDK extraction candidates for P4 WP 1.2
(September 2026 — CLI Integration Layer / shared SDK extraction).

The goal: `dincli/cli/` keeps Typer commands (UI/UX); `dincli/sdk/` holds pure
logic callable by `dind` without going through the CLI layer.

---

## Platform contracts (Phase 1 → `sdk/platform.py`)

| Test | SDK function |
|------|-------------|
| `test_deploy_din_coordinator` | `deploy_din_coordinator(network, account, artifact_path) → address` |
| `test_deploy_din_validator_stake` | `deploy_din_validator_stake(network, account, artifact_path) → address` |
| `test_deploy_din_model_registry` | `deploy_din_model_registry(network, account, artifact_path) → address` |
| `test_dump_abi_*` | `dump_abi(artifact_path, official=True)` |

---

## Task contracts + slashers (Phase 2 → `sdk/task_contracts.py`)

| Test | SDK function |
|------|-------------|
| `test_deploy_task_coordinator` | `deploy_task_coordinator(network, account, artifact_path) → address` |
| `test_deploy_task_auditor` | `deploy_task_auditor(network, account, artifact_path) → address` |
| `test_din_rep_authorizes_*` | `dindao_add_slasher(network, account, task_coordinator=None, task_auditor=None)` |
| `test_model_owner_registers_*` | `model_owner_add_slasher(network, account, task_coordinator=None, task_auditor=None)` |

---

## Registration (Phase 3 → `sdk/registration.py`)

| Test | SDK function |
|------|-------------|
| `test_model_owner_create_task_dir` | `create_task_dir(network, account)` |
| `test_model_owner_cache_default_artifacts` | `cache_default_artifacts(network, account)` |
| `test_model_owner_create_genesis_model` | `create_genesis_model(network, account)` |
| `test_model_owner_submit_genesis_model` | `submit_genesis_model(network, account)` |
| `test_model_owner_submit_registration_request` | `submit_registration_request(network, account)` |
| `test_din_rep_approves_registration_request` | `approve_registration_request(network, account, request_id)` |
| `test_model_owner_update_manifest_request` | `submit_manifest_update_request(network, account, model_id)` |
| `test_din_rep_approves_manifest_update` | `approve_manifest_update(network, account, request_id)` |

---

## GI lifecycle (Phase 4 → `sdk/gi.py`)

| Test | SDK function |
|------|-------------|
| `test_gi_start` | `start_gi(network, account, model_id)` |
| `test_gi_aggregators_open/close` | `open/close_aggregator_registration(network, account, model_id)` |
| `test_aggregator_register` | `register_aggregator(network, account, model_id)` |
| `test_gi_auditors_open/close` | `open/close_auditor_registration(network, account, model_id)` |
| `test_auditor_register` | `register_auditor(network, account, model_id)` |
| `test_lms_open/close` | `open_lms(network, account, model_id)` / `close_lms(...)` |
| `test_client_train_and_submit` | `train_and_submit_lm(network, account, model_id)` |
| `test_create_auditor_batches` | `create_auditor_batches(network, account, model_id)` |
| `test_lms_evaluation_start/close` | `start/close_lms_evaluation(network, account, model_id)` |
| `test_auditor_evaluate` | `evaluate_lms_batch(network, account, model_id)` |
| `test_create_t1nt2_batches` | `create_aggregation_batches(network, account, model_id)` |
| `test_t1_aggregation_start/close` | `start/close_t1_aggregation(network, account, model_id)` |
| `test_aggregator_aggregate_t1` | `aggregate_t1(network, account, model_id)` |
| `test_t2_aggregation_start/close` | `start/close_t2_aggregation(network, account, model_id)` |
| `test_aggregator_aggregate_t2` | `aggregate_t2(network, account, model_id)` |
| `test_slash_auditors` | `slash_auditors(network, account, model_id)` |
| `test_slash_aggregators` | `slash_aggregators(network, account, model_id)` |
| `test_gi_end` | `end_gi(network, account, model_id)` |

---

## CLI vs SDK separation boundary

The CLI layer (Typer) is responsible for:
- Argument parsing and `--option` flags
- Rich console output (colours, tables, progress bars)
- `typer.Exit(1)` error handling
- `ctx.obj` (DinContext) lifecycle

The SDK layer should be responsible for:
- All Web3 / contract calls
- IPFS upload/retrieve
- Wallet loading and transaction signing
- State transitions and return values (addresses, CIDs, tx receipts)
- Raising Python exceptions (not `typer.Exit`)

The split is already partially implied by `DinContext` and `utils.py`. The SDK
extraction will mainly involve pulling the body of each CLI command into a pure
function in `sdk/`, with the CLI command becoming a thin wrapper that calls
the SDK function and formats the result for the terminal.
