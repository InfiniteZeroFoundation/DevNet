# Validator Reward Mechanism Simulation Plan

## Purpose

The WP 3.2 simulation should demonstrate that validator incentives are:

- bounded by the validator reward pool plus allocated fees;
- fair across global iterations;
- fair between aggregator and auditor roles;
- paid only for accepted completed work;
- robust to invalid, late, jailed, or disputed validators;
- deterministic under integer rounding.

## Simulation Scope

The simulation focuses on validator rewards only.

Out of scope:

- client rewards;
- slashing penalty amounts;
- emissions;
- dynamic token pricing;
- long-term validator reputation.

## Baseline Parameters

Recommended default scenario:

```text
validatorRewardPool = 500 DIN
plannedGlobalIterations = 10
baseIterationBudget = 50 DIN
aggregatorShare = 4000 bps
auditorShare = 6000 bps
aggregatorsPerGI = 2
auditorsPerGI = 6
validatorFeeShare = 7000 bps
treasuryFeeShare = 3000 bps
iterationBudgetMode = equal_with_rollover
roleSplitMode = fixed_bps
aggregatorSplitMode = successful_work_equal
auditorSplitMode = accepted_result_equal
```

## Simulation Cases

### Case 1: All Validators Successful

All assigned aggregators and auditors complete valid work on time.

Expected result:

- aggregator pool is split equally among aggregators;
- auditor pool is split equally among auditors;
- fee allocation follows policy;
- no rollover except rounding dust.

### Case 2: Aggregator Failure

One aggregator misses the deadline or submits an invalid artifact.

Expected result:

- failed aggregator receives zero;
- successful aggregators split the aggregator pool;
- failure reason is recorded;
- no auditor reward is affected unless task finalization policy requires successful aggregation.

### Case 3: Auditor Failure

Some auditors miss submission or omit metric bundles.

Expected result:

- failed auditors receive zero;
- accepted auditors split the auditor pool;
- missing metric bundle is visible in the report.

### Case 4: No Successful Aggregators

No aggregator completes valid work.

Expected result:

- aggregator role pool is not paid;
- aggregator pool rolls forward or follows unspent policy;
- auditor rewards can either be paid or withheld depending on finalization policy.

For DevNet, record this as a policy decision in the simulation output.

### Case 5: No Accepted Auditors

No auditor result is accepted.

Expected result:

- auditor role pool is not paid;
- auditor pool rolls forward;
- aggregation rewards are unaffected if aggregation completed successfully.

### Case 6: Jailed Or Slashed Validator

A validator completed work but is jailed or slashed for that assignment before reward finalization.

Expected result:

- validator receives zero for the affected assignment;
- share is redistributed or rolled forward according to policy;
- report shows lifecycle suppression reason.

### Case 7: Fee Revenue Spike

One global iteration collects unusually high fees.

Expected result:

- validator fee allocation increases that iteration's reward budget;
- treasury fee share remains correct;
- total fee-funded payout does not exceed allocated fees;
- role split remains policy-compliant.

### Case 8: Role Split Extremes

Run simulations with:

- aggregator share at `2000` bps;
- aggregator share at `7000` bps;
- auditor share as the complement.

Expected result:

- role payout moves as expected;
- total iteration payout remains bounded;
- no role receives more than its configured pool.

### Case 9: Max Share Cap

One role has only one successful validator and max role share is enabled.

Expected result:

- validator payout is capped;
- remainder rolls forward or follows unspent policy;
- cap invariant passes.

### Case 10: Rounding Stress

Use small budgets and many validators.

Expected result:

- integer rounding is deterministic;
- dust is tracked;
- no overpayment occurs.

## Metrics To Report

Each simulation run should output:

- validator reward pool;
- fee revenue;
- validator fee allocation;
- treasury fee allocation;
- total paid;
- total unspent;
- paid per global iteration;
- paid per role;
- per-validator reward table;
- zero-reward reasons;
- top-validator concentration;
- invariant pass/fail summary.

## Invariants

Every simulation must check:

```text
sum(validator_rewards) <= validatorRewardPool + allocated_validator_fees
aggregator_paid_g <= aggregator_pool_g
auditor_paid_g <= auditor_pool_g
aggregator_pool_g + auditor_pool_g <= iteration_budget_g
invalid_work_reward == 0
late_work_reward == 0
jailed_or_slashed_reward == 0
fee_to_validators + fee_to_treasury == fees_collected
```

If max-share cap is enabled:

```text
validator_reward_v_g_r <= role_pool_g_r * max_validator_role_share_bps / 10000
```

## Example Output Shape

```json
{
  "scenario": "fee_revenue_spike",
  "validator_reward_pool": "500000000000000000000",
  "allocated_validator_fees": "70000000000000000000",
  "treasury_fees": "30000000000000000000",
  "total_paid": "565000000000000000000",
  "total_unspent": "5000000000000000000",
  "global_iterations": [
    {
      "gi": 4,
      "iteration_budget": "120000000000000000000",
      "fee_allocation": "70000000000000000000",
      "aggregator_pool": "48000000000000000000",
      "auditor_pool": "72000000000000000000",
      "aggregator_paid": "48000000000000000000",
      "auditor_paid": "71000000000000000000",
      "rollover_out": "1000000000000000000",
      "successful_aggregators": 2,
      "accepted_auditors": 5,
      "suppressed_validators": 1
    }
  ],
  "invariants": {
    "pool_bound": true,
    "role_bounds": true,
    "invalid_zero": true,
    "fee_conservation": true,
    "deterministic_rounding": true
  }
}
```

## Acceptance Criteria

The simulation deliverable is acceptable when it includes:

- at least the ten cases listed above;
- deterministic output from fixed seeds;
- one human-readable summary table;
- one machine-readable JSON report;
- clear invariant checks;
- explicit zero-reward reasons;
- notes explaining unspent reward-pool and fee-derived balances.
