# Client Reward Mechanism Implementation Plan

## Implementation Strategy

Implement participant rewards in phases:

1. define reward policy in the manifest;
2. create a deterministic reward calculation module;
3. integrate contribution outputs from scoring;
4. generate simulation reports;
5. add compact contract accounting and claim flow.

The first delivery should work in simulation mode even before all on-chain reward settlement pieces are complete.

## Workstream 1: Manifest Reward Policy

### Goal

Make reward behavior explicit and task-specific.

### Files To Update

- `Documentation/technical/manifest.md`
- `cache_model_0/manifest.json`
- task registration or model-owner docs

### Changes

- add a `reward_policy` block;
- define `client_reward_pool`, `planned_global_iterations`, budget mode, split mode, and unspent budget behavior;
- document how `reward_policy` depends on `scoring_policy.contribution`;
- reject reward activation when required contribution outputs are unavailable.

## Workstream 2: Reward Calculation Module

### Goal

Create a reusable module that calculates deterministic per-client rewards from policy and scoring outputs.

### Recommended New Module

- `dincli/services/rewards.py`

### Responsibilities

- load and validate `reward_policy`;
- validate required scoring and contribution outputs;
- select rewardable clients;
- calculate global-iteration budget;
- apply contribution weighting;
- apply optional max-share caps;
- handle rollover and rounding dust;
- generate a reward calculation report.

### Suggested Result Shape

```python
{
    "task_id": task_id,
    "global_iteration": gi,
    "iteration_budget": iteration_budget,
    "rollover_in": rollover_in,
    "rollover_out": rollover_out,
    "total_rewarded": total_rewarded,
    "clients": [
        {
            "address": client_address,
            "eligible": True,
            "aggregated": True,
            "contribution_score_bps": 7100,
            "adjusted_contribution_bps": 7100,
            "weight_bps": 4200,
            "reward_amount": reward_amount,
        }
    ],
    "reward_report_cid": reward_report_cid,
}
```

## Workstream 3: Scoring Integration

### Goal

Consume only contribution-plane outputs for reward weighting while using admission-plane outputs as gates.

### Dependencies

From `scoring-mechanism/implementation.md`:

- `dincli/services/scoring.py`
- `dincli/services/contribution.py`
- normalized auditor results;
- `contributionReportCID`.

### Changes

- wire reward calculation after contribution report generation;
- require admitted and aggregated model indexes by default;
- reject missing or stale contribution reports;
- include scoring policy hash and contribution report CID in reward reports.

## Workstream 4: Model-Owner CLI Integration

### Goal

Let model owners simulate and finalize participant rewards for a global iteration.

### Candidate Commands

- `dincli modelowner rewards simulate`
- `dincli modelowner rewards calculate`
- `dincli modelowner rewards finalize`
- `dincli modelowner rewards status`

### CLI Responsibilities

- display client contribution scores and proposed rewards;
- warn when rewards are disabled or contribution mode is unavailable;
- upload reward reports to IPFS;
- submit compact reward summaries on chain when supported.

## Workstream 5: Contract Accounting

### Goal

Add compact reward-pool and claim accounting without placing raw contribution math on chain.

### Contracts To Update

- `foundry/src/DINTaskCoordinator.sol`
- potentially a new `foundry/src/DINTaskRewards.sol`
- mirrored Hardhat contracts if the repo keeps both contract sets

### Recommended Contract Direction

Add or introduce:

```solidity
struct TaskRewardPool {
    address token;
    uint256 clientRewardPool;
    uint256 totalPaid;
    uint256 totalRollover;
    uint256 plannedGlobalIterations;
    bool initialized;
}

struct IterationRewardSummary {
    uint256 iterationBudget;
    uint256 totalRewarded;
    uint256 rolloverOut;
    bytes32 rewardReportCID;
    bytes32 payoutRoot;
    bool finalized;
}
```

For DevNet, direct per-client finalized amounts are acceptable. For larger rounds, prefer a payout root and proof-based claims.

### Contract Functions

Candidate functions:

- `initializeClientRewardPool(taskId, token, amount, plannedGlobalIterations)`
- `finalizeIterationRewards(taskId, gi, iterationBudget, totalRewarded, rolloverOut, rewardReportCID, payoutRoot)`
- `claimClientReward(taskId, gi, amount, proof)`
- `getRewardPool(taskId)`
- `getIterationRewardSummary(taskId, gi)`

## Workstream 6: Simulation Harness

### Goal

Produce simulation results for WP 3.1 deliverables before relying on live claims.

### Recommended New Script Or Test Module

- `tests/rewards/`
- or `dincli/services/rewards.py` unit tests plus a `scripts/simulate_rewards.py`

### Simulation Inputs

- number of global iterations;
- client count per iteration;
- reward pool size;
- eligibility rate;
- contribution score distribution;
- anomaly rate;
- max-share cap;
- rollover policy.

### Simulation Outputs

- per-client payouts;
- per-iteration budget usage;
- unspent rollover;
- concentration metrics;
- proof that total paid never exceeds pool;
- examples for equal, skewed, zero, and adversarial contribution distributions.

## Workstream 7: Tests

### Python Tests

Add tests for:

- equal contribution split;
- weighted contribution split;
- ineligible clients receive zero;
- missing contribution outputs disable payout;
- zero contribution rolls budget forward;
- max-client-share cap;
- deterministic rounding behavior;
- total paid never exceeds client pool.

### Contract Tests

Add tests for:

- reward pool initialization;
- iteration reward finalization;
- duplicate finalization rejection;
- claim once only;
- over-claim rejection;
- total paid bound;
- CID and payout-root storage.

## Suggested Delivery Phases

### Phase A: Off-Chain Reward Calculator

- add manifest `reward_policy`;
- implement `dincli/services/rewards.py`;
- consume mocked contribution outputs;
- generate local reward reports.

### Phase B: Scoring-Connected Simulation

- consume real contribution reports from the scoring layer;
- produce simulation results for representative global iterations;
- document fairness outcomes.

### Phase C: Contract Reward Summaries

- add reward-pool and iteration-summary storage;
- finalize reward reports on chain;
- keep claims simple for DevNet.

### Phase D: Claim Flow And Payout Roots

- add claim flow;
- add proof-based payout root if participant counts require it;
- integrate CLI status and claim commands.

## Definition Of Done

Implementation is complete when:

- `reward_policy` is documented and parsed;
- reward calculation consumes contribution-plane scoring outputs;
- per-global-iteration budgets are deterministic;
- per-client rewards are contribution-weighted;
- ineligible clients receive zero;
- rollover and rounding are handled by policy;
- simulation results are generated;
- compact reward summaries can be finalized on chain or prepared for that path.
