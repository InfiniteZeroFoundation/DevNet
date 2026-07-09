# Validator Reward Mechanism

## Summary

This issue defines the validator incentive mechanism for DIN P3 Task 3: Reward Distribution, specifically WP 3.2: Validator Incentive Mechanism.

DIN has two rewardable validator roles:

- **aggregators**, who combine accepted client updates into global model artifacts;
- **auditors**, who evaluate submitted client models or updates and submit scoring results.

The validator reward mechanism decides how the validator reward pool and fee revenue are split across global iterations, across validator roles, and then across individual validators inside each role.

The key design rule is:

- staking and selection decide who can be assigned;
- accepted completion decides who is rewardable;
- role-specific service quality weights determine reward share;
- fee distribution must be explicit and bounded.

This keeps validator incentives separate from client rewards while still aligning validator compensation with useful protocol work.

## Work Package

**Task:** P3 Task 3: Reward Distribution  
**Work package:** WP 3.2: Validator Incentive Mechanism  
**Duration:** June 08, 2026 to June 12, 2026 (Week 6)

### Activities

- Implement aggregation rewards
- Implement evaluation rewards
- Design fee-based incentives

### Deliverables

- Validator incentive module
- Fee distribution logic

## Problem Restated

DIN validators currently take on work and slash risk, but the reward side is incomplete.

Without a clear validator incentive mechanism:

- aggregators are not paid for heavier compute and memory work;
- auditors are not paid for evaluation work or timely score submission;
- protocol fees are not clearly routed into validator incentives;
- one role can be overpaid relative to its operational cost;
- global iterations with different validator counts can pay inconsistently;
- honest validators may face penalties without a positive expected return.

The protocol therefore needs a reward layer that is explicit about:

- the total validator reward pool for a task;
- the portion reserved for aggregators and auditors;
- how fee revenue is routed;
- how rewards are unlocked per global iteration;
- how rewards are split within each validator role;
- when rewards are withheld for missed, invalid, late, or disputed work.

## Related Mechanisms

This issue depends on several adjacent P3 docs.

- [Staking Infrastructure](staking-mechanism.md): defines validator eligibility, active stake, unbonding, jailing, blacklisting, and slashability.
- [Validator Selection](validator_selection.md): defines capability-aware assignment and the distinction between auditor and aggregator requirements.
- [Scoring Mechanism](scoring-mechanism.md): defines auditor result quality, agreement, and scoring artifacts used to judge evaluation work.
- [Client Reward Mechanism](client-reward-mechanism.md): handles participant rewards separately from validator rewards.
- [Tokenomics](tokenomics.md): defines broader issuance, fee, treasury, and reward-source policy.

## Core Design Direction

Validator incentives should be organized into four layers.

### 1. Task-level validator reward pool

Each task should have a bounded `validatorRewardPool`.

This pool is separate from:

- `clientRewardPool`;
- validator stake;
- slashed stake;
- treasury reserves;
- model-owner refundable balances.

### 2. Global-iteration validator budget

The task-level validator pool is unlocked across global iterations.

This prevents early rounds from consuming all validator rewards and gives validator operators predictable economics.

### 3. Role split

Each global iteration budget is split between:

- aggregator rewards;
- auditor rewards.

The split can be fixed, policy-driven, or workload-driven.

For DevNet, use a fixed split first:

```text
aggregator_pool_g = validator_iteration_budget_g * aggregator_share_bps / 10000
auditor_pool_g = validator_iteration_budget_g * auditor_share_bps / 10000
```

### 4. Per-role validator split

Within each role, validators split the role pool according to completed accepted work and service-quality weights.

Examples:

- aggregators: accepted aggregation artifact, assigned batch size, timeliness, successful finalization;
- auditors: accepted audit result, agreement with robust aggregate, timeliness, valid metric bundle.

## Fairness Principles

### 1. Bounded pool fairness

Total validator payouts must never exceed the task's `validatorRewardPool` plus explicitly allocated fee revenue.

The reward module must track:

- scheduled validator rewards;
- fee-funded rewards;
- total paid;
- unspent rollover;
- final remainder destination.

### 2. Global-iteration fairness

Validators should be paid against the work available in the global iteration where they were assigned.

The default budget is:

```text
validator_iteration_budget_g = base_budget_g + rollover_g + fee_allocation_g
```

Global iterations with no valid completed validator work should roll forward or route the budget according to policy.

### 3. Role fairness

Aggregator and auditor work should not compete in one undifferentiated pool.

Aggregation is usually heavier on memory, bandwidth, and model-artifact handling. Auditing is usually heavier on evaluation, scoring reliability, and timely submissions. The reward policy must account for the different costs and risks.

Recommended DevNet default:

- aggregator share: `4000` bps;
- auditor share: `6000` bps;
- allow task policy to override once real workload measurements exist.

### 4. Completion fairness

Only validators that completed assigned work successfully should be rewardable.

A validator receives zero reward for a global iteration if:

- assignment was not accepted when acceptance is required;
- work was missing;
- work was late beyond the reward window;
- submitted artifact was invalid;
- validator was jailed, blacklisted, tombstoned, or below active stake before finalization;
- validator was slashed for that assignment.

### 5. Quality fairness

Validators should be paid for valid work, not only attempted work.

Aggregator quality signals:

- aggregation artifact exists and is loadable;
- artifact CID matches expected format;
- aggregation used admitted client updates;
- final global model passes basic conformance checks;
- redundant aggregators agree within tolerance if the task uses replicated aggregation.

Auditor quality signals:

- audit result is eligible for final scoring;
- metric bundle exists;
- score submission is within deadline;
- result is not an outlier beyond disagreement policy;
- auditor is not found faulty by re-evaluation or dispute.

### 6. Anti-dominance fairness

One validator should not capture an excessive share when work was assigned to multiple validators.

Optional controls:

- per-validator max share per role;
- equal base fee plus quality bonus;
- stake-weighted cap, not stake-weighted default payout;
- minimum quorum before rewards are finalized.

### 7. Fee fairness

Fee-based incentives must be predictable and auditable.

If model-owner fees fund validator rewards, the routing must state:

- which fees are eligible;
- how much goes to validators;
- how much goes to treasury;
- whether fees are split by role;
- whether fees are paid immediately or pooled per global iteration.

## Recommended DevNet Default

For the first DevNet validator reward implementation:

- `validatorRewardPool`: fixed per task;
- global iteration schedule: equal split across planned global iterations;
- role split: `40%` aggregators, `60%` auditors;
- fee routing: optional additional top-up to validator iteration budget;
- aggregator split: equal among successful aggregators, with optional batch-size weight;
- auditor split: equal among accepted auditors, with optional agreement weight;
- unspent rewards: roll forward during task;
- final unspent rewards: return to model owner or task treasury policy;
- validators under active slashing or jail are not rewardable for affected assignments.

This keeps the first implementation deterministic while allowing later workload-aware tuning.

## Reward Formula

For task `t`, global iteration `g`, role `r`, and validator `v`:

```text
validator_pool_t = validatorRewardPool
iteration_budget_g = scheduled_budget_g + rollover_g + fee_allocation_g

aggregator_pool_g = iteration_budget_g * aggregator_share_bps / 10000
auditor_pool_g = iteration_budget_g * auditor_share_bps / 10000

role_pool_g_r = aggregator_pool_g or auditor_pool_g
eligible_validators_g_r = validators with accepted completed work for role r
quality_weight_v_g_r = role-specific completion and quality weight
reward_v_g_r = role_pool_g_r * quality_weight_v_g_r / sum(quality_weight_j_g_r)
```

If no validator is rewardable for a role:

```text
reward_v_g_r = 0
role_pool_g_r rolls forward or follows unspent policy
```

## Role-Specific Weighting

### Aggregator reward weight

Recommended DevNet default:

```text
aggregator_weight = 1
```

for each successful aggregator.

Optional later weighting:

```text
aggregator_weight =
  base_completion_weight
  * batch_size_factor
  * timeliness_factor
  * artifact_validity_factor
```

### Auditor reward weight

Recommended DevNet default:

```text
auditor_weight = 1
```

for each accepted auditor result.

Optional later weighting:

```text
auditor_weight =
  base_completion_weight
  * agreement_factor
  * timeliness_factor
  * metric_bundle_validity_factor
```

Agreement weighting should be conservative. It should reward consistency with robust consensus without incentivizing auditors to copy majority behavior blindly.

## Fee Distribution Policy

Validator incentives can be funded by:

- a task-level validator reward pool;
- model-owner task fees;
- protocol usage fees;
- treasury emissions;
- later, explicitly routed slash proceeds if tokenomics permits.

For WP 3.2, fee routing should be designed but kept simple.

Recommended DevNet policy:

```text
fee_allocation_g = fees_collected_for_task_g * validator_fee_share_bps / 10000
treasury_fee_g = fees_collected_for_task_g - fee_allocation_g
```

Then split `fee_allocation_g` by the same role split as the validator iteration budget, unless the manifest declares separate role fee shares.

Slashed validator stake should not be routed into validator rewards in WP 3.2 unless the tokenomics workstream explicitly approves that settlement path.

## Manifest Policy

The validator incentive policy should be declared in the task manifest.

Example:

```json
"validator_reward_policy": {
  "spec_version": 1,
  "validator_reward_pool": "500000000000000000000",
  "pool_token": "DIN",
  "planned_global_iterations": 10,
  "iteration_budget_mode": "equal_with_rollover",
  "role_split": {
    "aggregator_share_bps": 4000,
    "auditor_share_bps": 6000
  },
  "fee_distribution": {
    "enabled": true,
    "validator_fee_share_bps": 7000,
    "treasury_fee_share_bps": 3000,
    "role_fee_split_mode": "same_as_reward_pool"
  },
  "aggregator_rewards": {
    "split_mode": "successful_work_equal",
    "require_assignment_acceptance": true,
    "require_valid_artifact": true,
    "max_lateness_seconds": 3600
  },
  "auditor_rewards": {
    "split_mode": "accepted_result_equal",
    "require_assignment_acceptance": true,
    "require_metric_bundle": true,
    "max_disagreement_bps": 800,
    "max_lateness_seconds": 3600
  },
  "fairness": {
    "max_validator_role_share_bps": 5000,
    "min_rewardable_aggregators": 1,
    "min_rewardable_auditors": 1
  },
  "unspent_budget": {
    "during_task": "roll_forward",
    "after_task": "return_to_model_owner"
  }
}
```

## On-Chain And Off-Chain Split

### Off-chain artifacts

- validator assignment receipt;
- aggregation completion report;
- auditor result and metric bundle references;
- validator reward calculation report;
- fee distribution report;
- simulation report.

### On-chain summaries

- task-level validator reward pool;
- role split policy hash or compact values;
- per-iteration validator budget;
- per-role total rewarded;
- reward report CID;
- payout root or direct per-validator rewards;
- claim state;
- fee allocation totals.

Contracts should settle compact reward summaries. They should not recompute model aggregation, audit metrics, or complex agreement analysis on chain.

## Proposed Deliverables In This Folder

- [Design](validator-reward-mechanism/design.md): validator reward pool, global iteration budgeting, role splits, fee routing, and fairness rules
- [Implementation Plan](validator-reward-mechanism/implementation.md): module, CLI, contract, tests, and integration workstreams
- [Simulation Plan](validator-reward-mechanism/simulation.md): simulation cases for aggregator and auditor payouts, fee routing, and pool bounds

## Definition Of Done

This issue is complete when DIN can:

- define a task-level validator reward pool;
- split validator rewards across global iterations by explicit policy;
- split each iteration budget between aggregators and auditors;
- reward only validators with accepted completed work;
- route task fees into validator incentives by explicit policy;
- withhold rewards from late, invalid, jailed, blacklisted, or slashed validators;
- generate validator reward and fee distribution reports;
- prove through simulation that payouts are bounded and fair across roles and global iterations.

## Out Of Scope For Initial Delivery

The first WP 3.2 delivery does not need:

- dynamic emissions;
- slash redistribution into validator rewards;
- production Merkle-claim UX;
- fully automated dispute resolution;
- stake-weighted reward markets;
- real-time workload price discovery.

The immediate goal is a deterministic validator incentive module that supports aggregation rewards, evaluation rewards, and simple fee-based incentives for DevNet tasks.
