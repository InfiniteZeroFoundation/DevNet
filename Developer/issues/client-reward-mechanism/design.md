# Client Reward Mechanism Design

## Goals

The participant reward design gives DIN a deterministic way to distribute a bounded client reward pool according to measured contribution.

The design goals are:

- keep reward logic separate from admission scoring;
- distribute rewards fairly across global iterations;
- distribute each iteration budget fairly across clients;
- consume contribution outputs from the scoring mechanism;
- keep detailed contribution and reward evidence off-chain;
- keep on-chain accounting compact and claimable.

## Non-Goals

This design does not define:

- validator reward distribution;
- token issuance or treasury policy;
- slash redistribution;
- complete production dispute resolution;
- exact Shapley valuation for every deep-learning round.

Those are adjacent P3 topics, but WP 3.1 is specifically about participant reward logic.

## Inputs

The reward calculator consumes task, scoring, and runtime inputs.

### Task inputs

- `task_id`
- `clientRewardPool`
- reward token
- planned global iteration count
- active global iteration
- aggregation roster for the iteration

### Scoring inputs

From the scoring mechanism:

- admission result per client;
- contribution score per client;
- contribution mode;
- contribution report CID;
- anomaly or disagreement fields if available.

### Policy inputs

From `reward_policy`:

- iteration budget mode;
- client split mode;
- minimum contribution threshold;
- max client share cap;
- unspent budget behavior;
- final remainder behavior.

## Reward Pool Model

Each task owns a client reward pool:

```text
clientRewardPool_t
```

This pool is funded before or during task registration. The reward pool should be escrowed or otherwise reserved so clients can trust that rewards are actually available.

The pool is not the same as:

- validator rewards;
- staking collateral;
- slashing balances;
- protocol fee reserves;
- model-owner refunds.

Keeping these buckets separate makes accounting understandable and prevents client payouts from silently depending on unrelated economics.

## Global Iteration Budgeting

The task-level pool is split across global iterations.

### Equal budget

Recommended DevNet default:

```text
base_budget_g = clientRewardPool / planned_global_iterations
```

Any integer remainder is assigned by deterministic policy, such as adding it to the final iteration.

### Equal budget with rollover

Recommended for DevNet:

```text
iteration_budget_g = base_budget_g + unspent_rollover_g
```

If no clients are rewardable, the budget rolls forward instead of being paid equally to weak or ineligible updates.

### Performance-unlocked budget

Later versions may unlock an iteration budget only when the global model improves.

Example:

```text
iteration_budget_g = base_budget_g * unlock_factor(global_delta_g)
```

This is useful, but it depends on stable global utility measurement and should not be the first DevNet default.

## Per-Iteration Client Split

For each global iteration, calculate rewards only among rewardable clients.

A client is rewardable when:

- the submitted update is eligible;
- the update was accepted into aggregation;
- contribution output exists;
- adjusted contribution is positive;
- anomaly or disagreement checks do not suppress rewards.

### Linear contribution weighting

Default:

```text
adjusted_i = max(contribution_score_i - min_contribution_score, 0)
weight_i = adjusted_i / sum(adjusted_j)
reward_i = iteration_budget * weight_i
```

This is transparent and easy to simulate.

### Capped contribution weighting

Optional:

```text
reward_i <= iteration_budget * max_client_share_bps / 10000
```

Any cap remainder should be redistributed to other rewardable clients or rolled forward, depending on policy.

### Transformed contribution weighting

Optional transforms can reduce dominance:

- `sqrt`: softens large differences;
- `log`: strongly compresses large contributors;
- `rank`: pays by contribution rank instead of magnitude.

For DevNet, use `linear` first because it is easiest to audit.

## Handling Edge Cases

### No rewardable clients

Default:

- pay no one;
- roll the iteration budget forward.

### One rewardable client

Default:

- pay that client the full iteration budget unless `max_client_share_bps` is configured.

If a cap is configured, roll or redistribute the remainder according to policy.

### Negative contribution

Negative contribution should not create negative rewards in WP 3.1.

Default:

```text
adjusted_i = 0
```

Slashing or penalties belong to the slashing workstream, not the client reward module.

### Ties

Equal adjusted contribution scores receive equal rewards.

### Rounding

Use integer math and deterministic remainder handling.

Recommended:

- calculate proportional rewards using fixed-point basis points or token wei units;
- assign rounding dust to task remainder;
- roll dust forward or settle it at finalization.

## Contribution Modes

The reward calculator should support multiple contribution backends, but it should consume them through one normalized interface.

### `marginal_global_delta`

Measures how much the client update improves the global model or aggregation result.

Best near-term fit for DevNet if aggregation artifacts are available.

### `leave_one_out`

Estimates contribution by comparing aggregation with and without each client.

Useful and intuitive, but can be expensive as client count grows.

### `tknn_shapley` (Rejected)

Rejected due to FL privacy constraints. The validator/auditor does not have access to client training features/labels ($x_{train}, y_{train}$), which are required to compute distances. See [Rejected Ideas: TKNN-Shapley](../../rejected-ideas/tknn-shapley.md) for details.

### `dp_tknn_shapley` (Rejected)

Rejected for the same reasons as `tknn_shapley`.

## Reward Report

Every finalized global iteration should produce a reward calculation report.

Recommended shape:

```json
{
  "spec_version": 1,
  "task_id": "0x...",
  "global_iteration": 4,
  "reward_policy_hash": "0x...",
  "contribution_report_cid": "bafy...",
  "iteration_budget": "100000000000000000000",
  "rollover_in": "0",
  "rollover_out": "1200000000000000000",
  "clients": [
    {
      "client": "0x...",
      "eligible": true,
      "aggregated": true,
      "contribution_score_bps": 7100,
      "adjusted_contribution_bps": 7100,
      "weight_bps": 4200,
      "reward_amount": "42000000000000000000"
    }
  ]
}
```

The report should be uploaded off-chain and referenced by CID.

## On-Chain Accounting Model

The contract should store enough information to prove and claim rewards without storing every raw score.

Recommended state:

```text
TaskRewardPool
- token
- clientRewardPool
- totalScheduled
- totalPaid
- totalRollover
- finalizedIterations

IterationRewardSummary
- iterationBudget
- rewardReportCID
- payoutRoot or payoutCID
- totalRewarded
- rolloverOut
- finalized

ClientClaim
- claimedAmount
- claimed
```

For DevNet, a direct per-client mapping is acceptable if participant counts are small. For larger rounds, use a Merkle root or payout root and keep individual proofs off-chain.

## Fairness Checks

The reward module should enforce or report:

- `sum(client_rewards) <= iteration_budget`;
- `sum(iteration_paid) <= clientRewardPool`;
- ineligible clients receive zero;
- clients below contribution threshold receive zero;
- no client exceeds configured max share;
- unspent budget is routed by policy;
- reward output is deterministic for the same inputs.

## Recommended DevNet Policy

Use the following initial policy:

- equal per-global-iteration budget;
- rollover unspent budget during the task;
- linear contribution weights;
- require admitted and aggregated updates;
- no negative rewards;
- cap disabled in the first implementation, but implemented in simulation;
- final unspent budget returned according to model-owner or treasury policy.

This gives DIN a simple, auditable path first, while still leaving room for stronger economics later.
