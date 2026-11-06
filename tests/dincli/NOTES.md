# dincli Test Harness — SDK Candidate Notes

This file maps the test phases to their SDK extraction candidates for P4 WP 1.2
(September 2026 — CLI Integration Layer / shared SDK extraction).

The goal: `dincli/cli/` keeps Typer commands (UI/UX); `dincli/sdk/` holds pure
logic callable by `dind` without going through the CLI layer.

---

## Platform contracts (Phase 1 → `sdk/platform.py`)

Phase 1 deploys the seven platform contracts behind transparent proxies with
`forge script foundry/script/DeployPlatform.s.sol --broadcast` (the default
`PLATFORM_DEPLOY_TOOLCHAIN=foundry`; `hardhat` runs
`hardhat/scripts/deploy-platform.ts` instead), and dincli imports the
resulting `foundry/deployments/<network>.json` via `system import-deployments`.
The test checks each per-proxy `proxyAdmin*` key and its `proxy_admin_*`
din_info entry. Native web3.py proxy deploys in `dinrep deploy` remain the
recorded long-term decision
(`Documentation/technical/upgradable-contracts/proxy-deployment-architecture.md`;
backlog `Developer/issues/dincli-native-proxy-deployment.md`); once
implemented, Phase 1 returns to per-contract dincli deploy tests.

Task contracts (Phase 2 onward) are deployed from `foundry/out` too.
`dump-abi` tests write to the run's scratch dir (`--output`), never `--official`.

| Test | SDK function |
|------|-------------|
| `test_deploy_platform_via_script` | `deploy_platform(network) → addresses dict` (wraps the deploy script) |
| `test_import_deployments_into_din_info` | `import_deployments(network, file) → dict` (body of `system import-deployments`) |
| `test_dump_abi_*` | `dump_abi(artifact_path, output_dir)` |

---

## Task contracts + slashers (Phase 2 → `sdk/task_contracts.py`)

| Test | SDK function |
|------|-------------|
| `test_deploy_task_coordinator` | `deploy_task_coordinator(network, account, artifact_path, model_id=None) → address` (also sets DinToken) |
| `test_deploy_task_auditor` | `deploy_task_auditor(network, account, artifact_path, model_id=None) → address` (also sets DinToken) |
| `test_din_rep_authorizes_*` | `dinrep_add_slasher(network, account, task_coordinator=None, task_auditor=None)` |
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

One complete GI, with the GI state asserted after every phase (`_assert_state`).

| Test | SDK function | GI state after |
|------|-------------|----------------|
| `test_fund_gi_reward_pool` | `deposit_rewards(network, account, model_id, amount, gi=None)` | — |
| `test_gi_start` | `start_gi(network, account, model_id)` | `GIstarted` |
| `test_gi_aggregators_open/close` | `open/close_aggregator_registration(network, account, model_id)` | |
| `test_aggregator_register` | `register_aggregator(network, account, model_id)` | |
| `test_gi_auditors_open/close` | `open/close_auditor_registration(network, account, model_id)` | `DINauditorsRegistrationClosed` |
| `test_auditor_register` | `register_auditor(network, account, model_id)` | |
| `test_auditor_register_encryption_key` | `register_encryption_key(network, account)` | |
| `test_aggregator_cannot_register_as_auditor` | (negative: `register_auditor` raises) | |
| `test_lms_open/close` | `open_lms(network, account, model_id)` / `close_lms(...)` | `LMSstarted` / `LMSclosed` |
| `test_client_train_and_submit` | `train_lm(...)` + `submit_lm(network, account, model_id)` | |
| `test_auditor_lock_seed` | `lock_audit_seed(network, account, model_id)` | `AuditSeedLocked` |
| `test_create_auditor_batches` | `create_auditor_batches(network, account, model_id)` | `AuditorsBatchesCreated` |
| `test_create_testdataset_and_submit` | `assign_audit_test_data(network, account, model_id)` | `AuditTestDataAssigned` |
| `test_lms_evaluation_start` | `start_lms_evaluation(network, account, model_id)` | `LMSevaluationStarted` |
| `test_auditor_evaluate` | `evaluate_lms_batch(network, account, model_id)` (commit) | |
| `test_lms_evaluation_start_reveal` | `start_lms_evaluation_reveal(network, account, model_id)` | `LMSevaluationRevealStarted` |
| `test_auditor_reveal` | `reveal_audit_scores(network, account, model_id)` | |
| `test_lms_evaluation_close` | `close_lms_evaluation(network, account, model_id)` | `LMSevaluationClosed` |
| `test_aggregator_lock_seed` | `lock_agg_seed(network, account, model_id)` | `AggSeedLocked` |
| `test_create_t1nt2_batches` | `create_aggregation_batches(network, account, model_id)` | `T1nT2Bcreated` |
| `test_t1_aggregation_start` / `_start_reveal` / `_close` | `start/start_reveal/close_t1_aggregation(network, account, model_id)` | `T1AggregationStarted` / `…RevealStarted` / `T1AggregationDone` |
| `test_aggregator_aggregate_t1` / `test_aggregator_reveal_t1` | `aggregate_t1(...)` (commit) / `reveal_t1(...)` | |
| `test_t2_aggregation_start` / `_start_reveal` / `_close` | `start/start_reveal/close_t2_aggregation(network, account, model_id)` | `T2AggregationStarted` / `…RevealStarted` / `T2AggregationDone` |
| `test_aggregator_aggregate_t2` / `test_aggregator_reveal_t2` | `aggregate_t2(...)` (commit) / `reveal_t2(...)` | |
| `test_t2_set_score` | `set_tier2_score(network, account, model_id)` | |
| `test_slash_auditors` | `slash_auditors(network, account, model_id)` | `AuditorsSlashed` |
| `test_slash_aggregators` | `slash_aggregators(network, account, model_id)` | `AggregatorsSlashed` |
| `test_gi_end` / `test_gi_final_state_is_ended` | `end_gi(network, account, model_id)` | `GIended` (28) |
| `test_reward_claim_and_withdraw` | `claim_reward(network, account, model_id, gi)` + `withdraw_rewards(...)` | |
| `test_gi_release_slots` | `release_gi_slots(network, account, model_id, gi=None)` | |

------|-------------|
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
