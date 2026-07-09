# Validator Reward Mechanism Design

## Goals

The validator reward design gives DIN a deterministic way to compensate validators for successful aggregation and evaluation work.

The design goals are:

- separate validator rewards from client rewards;
- distinguish aggregator rewards from auditor rewards;
- distribute a bounded validator pool across global iterations;
- support fee-based validator incentives;
- withhold rewards for missed, invalid, late, or slashable work;
- keep detailed evidence off-chain and on-chain accounting compact.

## Non-Goals

This design does not define:

- participant reward distribution;
- validator selection mechanics;
- staking lifecycle mechanics;
- slashing rules;
- DIN issuance policy;
- exact long-term tokenomics.

Those mechanisms are dependencies or adjacent P3 workstreams.

## Validator Roles

DIN has two validator roles with different cost profiles.

### Aggregators

Aggregators combine accepted client updates and produce global model artifacts.

Expected work:

- download accepted local model artifacts;
- validate update availability;
- aggregate model weights or deltas;
- upload the global model artifact;
- submit or expose the aggregation result CID.

Cost profile:

- high bandwidth;
- higher RAM and disk risk;
- model-format and artifact-handling risk;
- batch-size sensitivity.

### Auditors

Auditors evaluate client submissions and produce scoring outputs.

Expected work:

- fetch assigned client model artifacts;
- load evaluation spec;
- run admission and utility checks;
- produce normalized audit results;
- upload metric bundles;
- submit score summaries.

Cost profile:

- evaluation compute;
- dataset-shard or evaluation-spec handling;
- scoring correctness risk;
- disagreement and dispute risk.

## Inputs

### Task inputs

- `task_id`
- planned global iteration count
- reward token
- validator reward pool
- fee revenue for the task or iteration

### Assignment inputs

- selected aggregators for global iteration;
- selected auditors for global iteration;
- assignment acceptance status;
- role and batch metadata;
- selection receipt CID.

### Completion inputs

Aggregator completion:

- aggregation artifact CID;
- artifact validity result;
- admitted client model indexes used;
- completion timestamp;
- optional replica agreement result.

Auditor completion:

- audit result summary;
- metric bundle CID;
- result accepted into final scoring;
- disagreement or outlier status;
- completion timestamp.

### Staking and lifecycle inputs

- active stake;
- exiting status;
- jailed status;
- blacklisted or tombstoned status;
- slashing state for the assignment.

## Pool Model

Each task owns a validator reward pool:

```text
validatorRewardPool_t
```

This pool is separate from:

- client reward pool;
- active validator stake;
- pending validator withdrawals;
- slashed funds;
- treasury reserves.

Separating the pools makes it possible to reason about validator expected return without draining participant rewards.

## Global Iteration Budgeting

The validator pool is split across planned global iterations.

### Equal budget

DevNet default:

```text
base_budget_g = validatorRewardPool / planned_global_iterations
```

### Equal budget with rollover

Recommended:

```text
iteration_budget_g = base_budget_g + rollover_g + fee_allocation_g
```

Rollover handles missed or invalid work without forcing undeserved payouts.

### Workload-aware budget

Later versions may adjust budget by workload:

```text
iteration_budget_g = base_budget_g * workload_factor_g
```

Possible factors:

- number of client updates;
- model size;
- number of audit batches;
- replicated aggregation count;
- evaluation dataset size.

This should be added only after DevNet has reliable workload measurements.

## Role Split

The validator iteration budget is split between aggregator and auditor reward pools.

Default:

```text
aggregator_pool_g = iteration_budget_g * 4000 / 10000
auditor_pool_g = iteration_budget_g * 6000 / 10000
```

The split is configurable because task types differ.

Examples:

- large model aggregation may increase aggregator share;
- heavy evaluation or multiple metrics may increase auditor share;
- no-label screening tasks may reduce auditor reward complexity but still pay for conformance checks.

## Aggregator Rewards

### Rewardable aggregator

An aggregator is rewardable when:

- selected for the global iteration;
- accepted the assignment if acceptance is enabled;
- submitted the expected aggregation artifact;
- artifact is valid and loadable;
- artifact is accepted by the coordinator or model owner flow;
- validator is active and not jailed, blacklisted, tombstoned, or slashed for the assignment.

### Default split

Use equal split among successful aggregators:

```text
aggregator_reward_v = aggregator_pool_g / successful_aggregators_g
```

### Optional weighted split

Later:

```text
aggregator_weight_v =
  completion_weight
  * batch_size_factor
  * timeliness_factor
  * replica_agreement_factor
```

Then:

```text
aggregator_reward_v =
  aggregator_pool_g * aggregator_weight_v / sum(aggregator_weight_j)
```

### Aggregator reward suppression

Aggregator reward should be zero when:

- artifact is missing;
- artifact CID is malformed;
- artifact fails conformance checks;
- submitted model omits admitted client updates without policy reason;
- submission is late beyond reward window;
- assignment is disputed and the aggregator is found faulty.

## Auditor Rewards

### Rewardable auditor

An auditor is rewardable when:

- selected for the global iteration or batch;
- accepted the assignment if acceptance is enabled;
- submitted audit results before the deadline;
- uploaded required metric bundle;
- result was accepted into robust aggregation;
- result is not suppressed by outlier or dispute policy;
- validator is active and not jailed, blacklisted, tombstoned, or slashed for the assignment.

### Default split

Use equal split among accepted auditors:

```text
auditor_reward_v = auditor_pool_g / accepted_auditors_g
```

### Optional weighted split

Later:

```text
auditor_weight_v =
  completion_weight
  * agreement_factor
  * timeliness_factor
  * metric_bundle_validity_factor
```

Then:

```text
auditor_reward_v =
  auditor_pool_g * auditor_weight_v / sum(auditor_weight_j)
```

### Agreement factor warning

Agreement-based auditor rewards should be conservative.

The mechanism should not overpay auditors simply for matching the majority, because that can create copycat incentives or punish honest auditors who detect real anomalies. A safer first version is:

- equal pay for accepted non-faulty audit results;
- suppress clear outliers only after robust aggregation or dispute logic;
- record disagreement metrics for later reputation rather than aggressive reward weighting.

## Fee Distribution

Fee distribution is the second source of validator incentives.

Potential fee sources:

- model registration fees;
- task creation fees;
- training participation fees;
- per-global-iteration service fees;
- treasury-funded reward top-ups.

Recommended DevNet model:

```text
validator_fee_allocation_g = task_fees_g * validator_fee_share_bps / 10000
treasury_fee_allocation_g = task_fees_g - validator_fee_allocation_g
```

Then:

```text
aggregator_fee_pool_g = validator_fee_allocation_g * aggregator_share_bps / 10000
auditor_fee_pool_g = validator_fee_allocation_g * auditor_share_bps / 10000
```

The fee pools can be added to the role reward pools before per-validator splitting.

## Unspent Budget

Unspent budget can occur when:

- no validators complete a role;
- role payout is capped;
- work is disputed;
- all validators are suppressed.

Recommended DevNet policy:

- roll forward during the task;
- after task completion, return final unspent reward-pool funds by manifest policy;
- route fee-derived unspent funds to treasury unless the manifest says to roll them forward.

Reward-pool funds and fee-derived funds should be tracked separately if their final destinations differ.

## Rounding

Use integer math.

Recommended rules:

- role splits use basis points;
- per-validator amounts are calculated in token base units;
- rounding dust stays in role remainder;
- role remainder rolls forward or moves to task remainder;
- never round up in a way that exceeds the available pool.

## On-Chain Accounting Model

Recommended state:

```text
ValidatorRewardPool
- token
- validatorRewardPool
- totalFeeAllocated
- totalPaid
- totalRollover
- plannedGlobalIterations

ValidatorIterationRewardSummary
- iterationBudget
- aggregatorPool
- auditorPool
- aggregatorRewarded
- auditorRewarded
- feeAllocated
- rolloverOut
- rewardReportCID
- payoutRoot
- finalized

ValidatorClaim
- claimedAmount
- claimed
```

For DevNet, direct per-validator mappings are acceptable. For larger validator sets, use a payout root.

## Reward Report

Every finalized global iteration should produce a validator reward report.

Recommended shape:

```json
{
  "spec_version": 1,
  "task_id": "0x...",
  "global_iteration": 6,
  "validator_reward_policy_hash": "0x...",
  "selection_receipt_cid": "bafy...",
  "iteration_budget": "50000000000000000000",
  "fee_allocation": "10000000000000000000",
  "roles": {
    "aggregators": {
      "role_pool": "24000000000000000000",
      "total_rewarded": "24000000000000000000",
      "validators": [
        {
          "validator": "0x...",
          "assignment_accepted": true,
          "completed": true,
          "artifact_valid": true,
          "weight_bps": 5000,
          "reward_amount": "12000000000000000000"
        }
      ]
    },
    "auditors": {
      "role_pool": "36000000000000000000",
      "total_rewarded": "35000000000000000000",
      "rollover_out": "1000000000000000000",
      "validators": [
        {
          "validator": "0x...",
          "assignment_accepted": true,
          "result_accepted": true,
          "metric_bundle_cid": "bafy...",
          "weight_bps": 2500,
          "reward_amount": "8750000000000000000"
        }
      ]
    }
  }
}
```

## Fairness Checks

The reward module should enforce or report:

- total validator rewards do not exceed available pool plus allocated fees;
- aggregator and auditor shares sum to the iteration budget;
- invalid or late work receives zero;
- jailed, blacklisted, tombstoned, or slashed validators receive zero for affected assignments;
- no validator exceeds configured max role share;
- fee allocation matches policy;
- reward output is deterministic for the same inputs.

## Recommended DevNet Policy

Use:

- equal per-global-iteration validator budget;
- fixed role split;
- equal split among successful aggregators;
- equal split among accepted auditors;
- fee top-up routed through same role split;
- rollover for unspent role budgets;
- no slash redistribution into rewards yet.

This policy is simple enough to implement in Week 6 and still captures the economic boundaries DIN needs before testnet hardening.
