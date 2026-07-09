# Validator Reward Mechanism Implementation Plan

## Implementation Strategy

Implement validator incentives in phases:

1. define validator reward and fee policy in the manifest;
2. create a deterministic validator incentive module;
3. integrate aggregation and audit completion outputs;
4. add fee distribution accounting;
5. generate simulation reports;
6. add compact contract accounting and claim flow.

The first version should be able to run in simulation mode before production claim flows are complete.

## Workstream 1: Manifest Validator Reward Policy

### Goal

Make validator reward behavior explicit and task-specific.

### Files To Update

- `Documentation/technical/manifest.md`
- `cache_model_0/manifest.json`
- validator/operator docs
- model-owner docs

### Changes

- add a `validator_reward_policy` block;
- define validator reward pool, planned global iterations, role split, fee routing, and unspent behavior;
- define rewardable completion criteria for aggregators and auditors;
- document how the policy interacts with staking, validator selection, and scoring.

## Workstream 2: Validator Incentive Module

### Goal

Create a reusable module that calculates deterministic validator rewards.

### Recommended New Module

- `dincli/services/validator_rewards.py`

### Responsibilities

- load and validate `validator_reward_policy`;
- calculate per-global-iteration validator budget;
- allocate fee revenue to validator incentives;
- split rewards between aggregators and auditors;
- select rewardable validators for each role;
- apply role-specific weights;
- apply optional max-share caps;
- track rollover and rounding dust;
- generate validator reward reports.

### Suggested Result Shape

```python
{
    "task_id": task_id,
    "global_iteration": gi,
    "iteration_budget": iteration_budget,
    "fee_allocation": fee_allocation,
    "rollover_in": rollover_in,
    "rollover_out": rollover_out,
    "roles": {
        "aggregators": {
            "role_pool": aggregator_pool,
            "total_rewarded": aggregator_total,
            "validators": [...]
        },
        "auditors": {
            "role_pool": auditor_pool,
            "total_rewarded": auditor_total,
            "validators": [...]
        }
    },
    "reward_report_cid": reward_report_cid,
}
```

## Workstream 3: Aggregation Reward Integration

### Goal

Reward aggregators for accepted aggregation work.

### Inputs

- assignment receipt;
- accepted assignment state;
- aggregation artifact CID;
- artifact validity result;
- admitted client update set;
- completion timestamp;
- validator lifecycle status.

### Changes

- record aggregation completion metadata in model-owner or coordinator tooling;
- verify artifact existence and basic validity before reward calculation;
- exclude late or invalid aggregation submissions;
- include aggregation report reference in the validator reward report.

### DevNet Split

Use equal split among successful aggregators first.

Later add:

- batch-size weighting;
- model-size weighting;
- timeliness bonus;
- replicated aggregation agreement weighting.

## Workstream 4: Evaluation Reward Integration

### Goal

Reward auditors for accepted evaluation work.

### Inputs

- auditor assignment receipt;
- audit result summary;
- metric bundle CID;
- accepted result status;
- disagreement or outlier status;
- completion timestamp;
- validator lifecycle status.

### Changes

- consume scoring finalization outputs from `DINTaskAuditor` and off-chain scoring reports;
- exclude missing, late, invalid, or suppressed audit results;
- include metric bundle references in the validator reward report;
- avoid aggressive agreement weighting in the first version.

### DevNet Split

Use equal split among accepted auditors first.

Later add:

- agreement factor;
- timeliness factor;
- workload factor by number of evaluated client models;
- dispute outcome factor.

## Workstream 5: Fee Distribution Logic

### Goal

Route task or protocol fees into validator incentives by explicit policy.

### Inputs

- fees collected for task or global iteration;
- `validator_fee_share_bps`;
- treasury share;
- role fee split mode.

### Changes

- add fee allocation calculation to `validator_rewards.py`;
- track fee-derived rewards separately from reward-pool-derived rewards when final destinations differ;
- generate fee distribution report entries;
- expose fee allocation in CLI status output.

### Recommended DevNet Rule

```text
validator_fee_allocation = fees_collected * validator_fee_share_bps / 10000
treasury_fee_allocation = fees_collected - validator_fee_allocation
```

Then split validator fee allocation by the same aggregator/auditor role split.

## Workstream 6: Model-Owner And Validator CLI Integration

### Goal

Let operators simulate, calculate, finalize, and claim validator rewards.

### Candidate Model-Owner Commands

- `dincli modelowner validator-rewards simulate`
- `dincli modelowner validator-rewards calculate`
- `dincli modelowner validator-rewards finalize`
- `dincli modelowner validator-rewards status`

### Candidate Validator Commands

- `dincli validator rewards status`
- `dincli validator rewards claim`

### CLI Responsibilities

- show role split and fee allocation;
- show eligible, suppressed, and rewarded validators;
- upload validator reward reports to IPFS;
- submit compact reward summaries when contracts support it;
- explain why a validator received zero.

## Workstream 7: Contract Accounting

### Goal

Add compact validator reward and fee accounting.

### Contracts To Update

- `foundry/src/DINTaskCoordinator.sol`
- `foundry/src/DINTaskAuditor.sol`
- potentially a new `foundry/src/DINTaskRewards.sol`
- mirrored Hardhat contracts if both stacks remain active

### Recommended Contract Direction

Add or introduce:

```solidity
struct ValidatorRewardPool {
    address token;
    uint256 validatorRewardPool;
    uint256 totalFeeAllocated;
    uint256 totalPaid;
    uint256 totalRollover;
    uint256 plannedGlobalIterations;
    bool initialized;
}

struct ValidatorIterationRewardSummary {
    uint256 iterationBudget;
    uint256 aggregatorPool;
    uint256 auditorPool;
    uint256 aggregatorRewarded;
    uint256 auditorRewarded;
    uint256 feeAllocated;
    uint256 rolloverOut;
    bytes32 rewardReportCID;
    bytes32 payoutRoot;
    bool finalized;
}
```

### Candidate Functions

- `initializeValidatorRewardPool(taskId, token, amount, plannedGlobalIterations)`
- `finalizeValidatorIterationRewards(taskId, gi, summary, rewardReportCID, payoutRoot)`
- `claimValidatorReward(taskId, gi, amount, proof)`
- `getValidatorRewardPool(taskId)`
- `getValidatorIterationRewardSummary(taskId, gi)`

For DevNet, direct per-validator reward mappings may be acceptable. For larger validator sets, use a payout root.

## Workstream 8: Simulation Harness

### Goal

Produce simulation results for WP 3.2 deliverables.

### Recommended Location

- `tests/rewards/`
- or `dincli/services/validator_rewards.py` unit tests plus `scripts/simulate_validator_rewards.py`

### Simulation Inputs

- validator reward pool;
- planned global iterations;
- aggregator count per iteration;
- auditor count per iteration;
- completion rates;
- late submission rates;
- invalid artifact rates;
- audit disagreement rates;
- fee revenue per iteration;
- role split;
- max-share caps.

### Simulation Outputs

- per-role payout table;
- per-validator payouts;
- fee allocation summary;
- unspent and rollover summary;
- zero-reward reasons;
- concentration metrics;
- invariant pass/fail summary.

## Workstream 9: Tests

### Python Tests

Add tests for:

- equal aggregator split;
- equal auditor split;
- role split basis points;
- fee allocation math;
- no reward for invalid aggregation artifact;
- no reward for missing metric bundle;
- no reward for late work;
- no reward for jailed or slashed validator;
- rollover when a role has no successful validators;
- deterministic rounding;
- total paid never exceeds pool plus allocated fees.

### Contract Tests

Add tests for:

- validator reward pool initialization;
- iteration reward finalization;
- duplicate finalization rejection;
- claim once only;
- over-claim rejection;
- fee allocation storage;
- payout root or direct mapping correctness;
- total paid bound.

## Suggested Delivery Phases

### Phase A: Off-Chain Incentive Calculator

- add `validator_reward_policy`;
- implement `dincli/services/validator_rewards.py`;
- calculate aggregator and auditor rewards from mocked completion data;
- generate reward reports.

### Phase B: Aggregation And Evaluation Integration

- consume real aggregation completion outputs;
- consume accepted auditor result outputs;
- produce global-iteration validator reward reports.

### Phase C: Fee Distribution

- add fee allocation logic;
- report treasury and validator fee splits;
- include fee top-ups in role pools.

### Phase D: Contract Summaries And Claims

- add validator reward pool and iteration summary storage;
- finalize reward summaries on chain;
- add DevNet claim flow.

## Definition Of Done

Implementation is complete when:

- `validator_reward_policy` is documented and parsed;
- aggregation rewards are calculated for successful aggregators;
- evaluation rewards are calculated for accepted auditors;
- fee distribution logic is deterministic and reported;
- invalid, late, jailed, blacklisted, or slashed validators receive zero for affected work;
- global iteration and role budgets are bounded;
- simulation results are generated;
- compact validator reward summaries can be finalized on chain or prepared for that path.
