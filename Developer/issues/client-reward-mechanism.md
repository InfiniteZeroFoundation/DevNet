# Client Reward Mechanism

## Summary

This issue defines the participant reward mechanism for DIN P3 Task 3: Reward Distribution, specifically WP 3.1: Participant Reward Logic.

The reward mechanism depends on the scoring redesign in [scoring-mechanism.md](scoring-mechanism.md). Scoring decides which client updates are eligible and how much contribution each accepted client made. The reward mechanism decides how the client reward pool is split across global iterations and then distributed across clients inside each iteration.

The key design rule is:

- admission scoring gates participation in aggregation;
- contribution scoring weights rewards;
- reward accounting settles claims from a bounded client reward pool.

This keeps rewards fair without mixing model approval, contribution valuation, and token payout logic into one scalar.

## Work Package

**Task:** P3 Task 3: Reward Distribution  
**Work package:** WP 3.1: Participant Reward Logic  
**Duration:** June 01, 2026 to June 05, 2026 (Week 5)

### Activities

- Design contribution-weighted rewards
- Implement reward split logic
- Integrate scoring outputs

### Deliverables

- Reward calculation module
- Simulation results

## Problem Restated

DIN needs to reward clients for useful training contributions, but a naive equal split creates several failures:

- free riders can receive the same reward as useful contributors;
- low-quality or ineligible updates can dilute honest participants;
- one unusually large round can drain the reward pool;
- early global iterations can overpay before the task's total contribution profile is known;
- scoring outputs can be misused if admission utility is treated as a reward score.

The protocol therefore needs a reward layer that is explicit about:

- the total client reward pool for a task;
- how much of that pool is unlocked per global iteration;
- which clients are eligible for rewards in each iteration;
- how contribution scores are normalized into payout weights;
- what happens to unearned or withheld rewards.

## Dependency On Scoring Mechanism

This design assumes the scoring mechanism provides separate outputs for admission and contribution.

Required scoring outputs:

- `eligible`: whether the client model/update passed admission checks;
- `utility_score_bps`: normalized utility score used for model admission;
- `contribution_score_bps`: normalized reward contribution score;
- `contribution_mode`: for example `leave_one_out` or `marginal_global_delta` (note: `tknn_shapley` and `dp_tknn_shapley` are rejected - see [Rejected Ideas: TKNN-Shapley](rejected-ideas/tknn-shapley.md));
- `contributionReportCID`: off-chain report containing detailed contribution evidence;
- optional `anomaly_score_bps` or disagreement fields for reward suppression.

Reward logic must not use `utility_score_bps` directly as the only reward weight unless the manifest explicitly declares that policy. The safer default is to pay only eligible clients and weight them by contribution-plane output.

## Core Design Direction

Client rewards should be organized into three layers.

### 1. Task-level client reward pool

The model owner, treasury, or emissions policy funds a bounded `clientRewardPool` for a task.

This pool is the maximum amount payable to clients across all global iterations. It should be separated from validator rewards, protocol fees, slashing proceeds, and treasury reserves.

### 2. Global-iteration reward budget

Each global iteration receives a budget from the task-level pool.

This prevents the first iteration with many eligible clients from consuming the full pool and gives the protocol a predictable payout schedule.

### 3. Per-iteration client split

Within a global iteration, eligible clients split that iteration's client reward budget according to normalized contribution weights.

Clients that are ineligible, rejected, anomalous, or below the minimum contribution threshold receive no reward for that iteration.

## Fairness Principles

The reward mechanism should satisfy the following properties.

### 1. Bounded pool fairness

The total amount paid to clients must never exceed the task's `clientRewardPool`.

Every global iteration receives a budget from this pool according to an explicit schedule. Unspent rewards should either roll forward, return to the task owner, or move to treasury based on manifest policy.

### 2. Iteration fairness

Clients should be compared against other clients in the same global iteration because they trained against the same global model state and task conditions.

The default split is:

```text
client_reward_i_g = iteration_budget_g * normalized_weight_i_g
```

where `g` is the global iteration and `i` is the client.

### 3. Contribution fairness

Reward weights should reflect measured contribution, not raw participation.

Recommended default:

```text
positive_contribution_i_g = max(contribution_score_i_g - min_contribution_score, 0)
weight_i_g = positive_contribution_i_g / sum(positive_contribution_j_g)
```

If the sum is zero, the protocol should either withhold the iteration budget or use a conservative fallback declared in the manifest.

### 4. Eligibility fairness

Only admitted clients should be rewardable by default.

A client should receive zero reward for a global iteration if:

- `eligible == false`;
- admission utility is below the declared threshold;
- the update is excluded from aggregation;
- anomaly score exceeds the reward-suppression bound;
- contribution report is missing or invalid.

### 5. Anti-dominance fairness

The protocol should avoid one client capturing the entire iteration budget unless the policy explicitly permits it.

Optional controls:

- per-client max share per iteration;
- square-root or log contribution transform;
- floor/cap policy;
- minimum number of eligible contributors before payout;
- withheld remainder routed according to policy.

### 6. Temporal fairness

Reward distribution across global iterations should not overpay early rounds or starve later rounds.

Supported schedules:

- equal budget per global iteration;
- performance-unlocked budget based on global model improvement;
- decaying schedule that rewards early bootstrapping more heavily;
- milestone schedule tied to task-level evaluation targets.

For DevNet, the recommended default is equal budget per planned global iteration with roll-forward of unused budget.

## Recommended DevNet Default

For the current DevNet path, use:

- `clientRewardPool`: fixed per task;
- global iteration schedule: equal split across planned global iterations;
- eligibility gate: admitted and aggregated client updates only;
- contribution backend: `marginal_global_delta` or `leave_one_out` once available;
- normalization: basis points;
- min contribution score: `0`;
- max client share: optional, default disabled for first simulation;
- unspent budget: roll forward to the next global iteration;
- final unspent budget: return to model owner or task treasury policy.

If only admission scoring exists initially, reward distribution should remain disabled or run in simulation mode until contribution-plane outputs are available.

## Reward Formula

For task `t`, global iteration `g`, and client `i`:

```text
task_pool_t = clientRewardPool
iteration_budget_g = scheduled_budget_g + rolled_unspent_budget_g
eligible_set_g = clients accepted into aggregation for g

raw_contribution_i_g = contribution_score_bps_i_g
adjusted_contribution_i_g = max(raw_contribution_i_g - min_contribution_bps, 0)
weight_i_g = adjusted_contribution_i_g / sum(adjusted_contribution_j_g)
reward_i_g = iteration_budget_g * weight_i_g
```

If `sum(adjusted_contribution_j_g) == 0`, the default DevNet behavior should be:

```text
reward_i_g = 0
rolled_unspent_budget_g+1 += iteration_budget_g
```

## Manifest Policy

The reward policy should be declared alongside the scoring policy in the task manifest.

Example:

```json
"reward_policy": {
  "spec_version": 1,
  "client_reward_pool": "1000000000000000000000",
  "pool_token": "DIN",
  "planned_global_iterations": 10,
  "iteration_budget_mode": "equal_with_rollover",
  "client_split_mode": "contribution_weighted",
  "required_contribution_mode": "marginal_global_delta",
  "normalization": {
    "score_scale": "basis_points",
    "max_score": 10000
  },
  "eligibility": {
    "require_admitted": true,
    "require_aggregated": true,
    "min_contribution_bps": 0,
    "max_anomaly_score_bps": 2000
  },
  "fairness": {
    "max_client_share_bps": 5000,
    "min_rewardable_clients": 1,
    "transform": "linear"
  },
  "unspent_budget": {
    "during_task": "roll_forward",
    "after_task": "return_to_model_owner"
  }
}
```

## On-Chain And Off-Chain Split

Reward calculation should follow the same compact-on-chain pattern as scoring.

### Off-chain artifacts

- contribution report per global iteration;
- reward calculation report per global iteration;
- simulation report;
- detailed client score breakdown;
- calculation inputs and policy snapshot.

### On-chain summaries

- task-level client reward pool;
- per-iteration budget;
- reward root or payout summary CID;
- claimed amount per client;
- total paid and remaining pool;
- optional dispute or finalization status.

The contract should not parse every contribution metric. It should settle compact normalized reward amounts produced by an auditable reward calculation module.

## Proposed Deliverables In This Folder

- [Design](client-reward-mechanism/design.md): pool fairness, global iteration budget, per-client reward split, policy schema, and accounting model
- [Implementation Plan](client-reward-mechanism/implementation.md): module, CLI, contract, tests, and integration workstreams
- [Simulation Plan](client-reward-mechanism/simulation.md): simulation cases and expected outputs for validating fairness and manipulation resistance

## Definition Of Done

This issue is complete when DIN can:

- define a task-level client reward pool;
- split the pool across global iterations by explicit policy;
- consume contribution-plane outputs from the scoring mechanism;
- calculate per-client iteration rewards deterministically;
- withhold rewards from ineligible or anomalous updates;
- generate a reward calculation report and simulation results;
- expose compact on-chain reward accounting and claim state;
- prove through simulation that payouts are bounded, contribution-weighted, and fair across global iterations.

## Out Of Scope For Initial Delivery

The first WP 3.1 delivery does not need:

- full validator reward distribution;
- slash redistribution;
- dynamic emissions policy;
- cross-task reputation rewards;
- cryptographic verification of every off-chain contribution calculation;
- production Merkle-claim UX.

The immediate goal is a deterministic participant reward module that correctly consumes scoring outputs and simulates fair client reward distribution for DevNet tasks.
