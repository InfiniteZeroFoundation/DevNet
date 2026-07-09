# Client Reward Mechanism Simulation Plan

## Purpose

The WP 3.1 simulation should demonstrate that participant rewards are:

- bounded by the task-level client reward pool;
- fair across global iterations;
- weighted by contribution inside each iteration;
- robust to zero, missing, or anomalous contribution outputs;
- deterministic under integer rounding.

## Simulation Scope

The simulation should focus on client rewards only.

Out of scope:

- validator rewards;
- slashing;
- emissions;
- dynamic token pricing;
- treasury policy.

## Baseline Parameters

Recommended default scenario:

```text
clientRewardPool = 1000 DIN
plannedGlobalIterations = 10
baseIterationBudget = 100 DIN
clientCountPerGI = 10
contributionScale = 0..10000 bps
iterationBudgetMode = equal_with_rollover
clientSplitMode = contribution_weighted
fairnessTransform = linear
```

## Simulation Cases

### Case 1: Equal Contributions

All rewardable clients have the same contribution score.

Expected result:

- every eligible client receives the same reward;
- no budget is lost except deterministic rounding dust;
- total paid is bounded by the pool.

### Case 2: Skewed Contributions

One or two clients produce much higher contribution scores.

Expected result:

- higher contributors receive higher rewards;
- reward concentration is measurable;
- optional max-share cap limits dominance when enabled.

### Case 3: Ineligible Clients

Some clients have high contribution-like metrics but failed admission.

Expected result:

- ineligible clients receive zero;
- eligible clients split the iteration budget;
- reward logic does not override admission gates.

### Case 4: Zero Contributions

All clients have zero or below-threshold contribution.

Expected result:

- no clients are paid;
- the iteration budget rolls forward;
- future iterations can consume rollover if rewardable contribution appears.

### Case 5: Missing Contribution Report

Admission scores exist, but contribution-plane outputs are missing.

Expected result:

- rewards are disabled or withheld for the iteration;
- no equal fallback is silently applied unless explicitly configured;
- the report explains the missing dependency.

### Case 6: Anomalous Client

A client has a high contribution score and an anomaly score above policy bounds.

Expected result:

- anomalous client receives zero or is suppressed according to policy;
- remaining clients are weighted normally;
- suppression is visible in the report.

### Case 7: Rollover Across Iterations

Early iterations have no rewardable clients and later iterations do.

Expected result:

- early budgets roll forward;
- later iteration budgets include rollover;
- total paid remains below or equal to the original pool.

### Case 8: Rounding Stress

Use small reward pools and many clients.

Expected result:

- integer rounding is deterministic;
- dust is tracked as rollover or task remainder;
- no overpayment occurs.

## Metrics To Report

Each simulation run should output:

- total pool;
- total paid;
- total unspent;
- paid per global iteration;
- rollover per global iteration;
- per-client reward table;
- reward concentration by top 1 and top 3 clients;
- number of rewardable clients;
- number of suppressed clients;
- invariant pass/fail summary.

## Invariants

Every simulation must check:

```text
sum(all_client_rewards) <= clientRewardPool
sum(iteration_rewards_g) <= iteration_budget_g
ineligible_client_reward == 0
below_threshold_client_reward == 0
claimed_or_finalized_amounts_are_deterministic
```

If max-share cap is enabled:

```text
client_reward_i_g <= iteration_budget_g * max_client_share_bps / 10000
```

## Example Output Shape

```json
{
  "scenario": "skewed_contributions",
  "client_reward_pool": "1000000000000000000000",
  "total_paid": "998700000000000000000",
  "total_unspent": "1300000000000000000",
  "global_iterations": [
    {
      "gi": 1,
      "iteration_budget": "100000000000000000000",
      "total_rewarded": "100000000000000000000",
      "rollover_out": "0",
      "rewardable_clients": 8,
      "suppressed_clients": 2,
      "top_1_share_bps": 4100,
      "top_3_share_bps": 7600
    }
  ],
  "invariants": {
    "pool_bound": true,
    "iteration_bound": true,
    "ineligible_zero": true,
    "deterministic_rounding": true
  }
}
```

## Acceptance Criteria

The simulation deliverable is acceptable when it includes:

- at least the eight cases listed above;
- deterministic output from fixed seeds;
- one human-readable summary table;
- one machine-readable JSON report;
- clear invariant checks;
- notes explaining any retained unspent budget.
