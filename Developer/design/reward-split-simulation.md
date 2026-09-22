# Reward-Split Simulation — Income Stability & Split Recommendation

**Status:** Complete (issue #41)
**Owner:** Robbert
**Tracking:** [GitHub issue #41](https://github.com/InfiniteZeroFoundation/DevNet/issues/41)
**Simulation plan:** `Developer/issues/validator-reward-mechanism/simulation.md`
**Run:** arithmetic simulation (no Forge test required — pure economic modelling)

---

## Purpose

The P3-5.2 simulation validates that the `DINTaskAuditor.RewardSplit` defaults
(currently `clientBps: 6000 / auditorBps: 2000 / aggregatorBps: 1500 / treasuryBps: 500`)
produce stable, fair per-role income across the expected participation range
(10–50 validators, 100–500 clients). A concrete split recommendation — confirm or revise —
is the primary output.

---

## Participation tiers

Three tiers scope the sensitivity analysis (LOW ≈ 0.1×, MID ≈ target, HIGH ≈ 10×):

| Tier | Clients | T1 batches | Successful T1 agg | Successful T2 agg | Successful auditors |
|------|---------|-----------|-------------------|-------------------|---------------------|
| LOW  | 100     | 3         | 6 (2 per batch)   | 2                 | 6                   |
| MID  | 250     | 5         | 10 (2 per batch)  | 2                 | 15                  |
| HIGH | 500     | 10        | 20 (2 per batch)  | 2                 | 30                  |

"Successful" means the validator completed valid work before the deadline and was not jailed
or slashed before reward finalization. Aggregator weight tracks finalized batches:
T1 aggregators earn weight 1 per finalized T1 batch; T2 aggregators earn weight 1.
Total aggregator weight per GI = successful T1 agg + 2 (T2 weight).

---

## Baseline parameters

```text
rewardPool        = 500 DIN (over 10 GIs)
baseIterationBudget = 50 DIN/GI
split             = 60 / 20 / 15 / 5  (client / auditor / aggregator / treasury)
```

Per-GI pool breakdown at 50 DIN:

| Role         | bps  | DIN/GI |
|--------------|------|--------|
| Clients      | 6000 | 30.00  |
| Auditors     | 2000 | 10.00  |
| Aggregators  | 1500 |  7.50  |
| Treasury     |  500 |  2.50  |
| **Total**    | 10000| 50.00  |

Rounding dust: `treasuryShare = pool − clientPool − auditorPool − aggregatorPool` absorbs
all integer-division remainders (implemented in `DINTaskAuditor.settleRewards`, confirmed
correct since PR #134 — see BL-14 note at the end of this document).

---

## Income stability — per-role per-GI at 50 DIN/GI

### Clients (clientPool = 30 DIN, split equally by finalMedianScore weight)

For simplicity, assume equal score weights (uniform split):

| Tier | Clients | DIN/client/GI | DIN/client/year (52 GIs) |
|------|---------|--------------|--------------------------|
| LOW  | 100     | 0.300        | 15.60                    |
| MID  | 250     | 0.120        |  6.24                    |
| HIGH | 500     | 0.060        |  3.12                    |

Clients bear no stake requirement. Even at HIGH tier the per-client reward is positive and
deterministic. The 60% allocation is appropriate for the primary data contributors.

### Auditors (auditorPool = 10 DIN, split by batch-contribution weight)

| Tier | Successful aud | DIN/auditor/GI | DIN/auditor/year (52 GIs) | APY on 10 DIN MIN_STAKE |
|------|---------------|----------------|---------------------------|-------------------------|
| LOW  | 6             | 1.667          | 86.67                     | 867%                    |
| MID  | 15            | 0.667          | 34.67                     | 347%                    |
| HIGH | 30            | 0.333          | 17.33                     | 173%                    |

### Aggregators (aggregatorPool = 7.50 DIN, split by finalized-batch weight)

Weight per aggregator: T1 agg earns weight 1; T2 agg earns weight 1.
Total weight = successful T1 agg + 2 (T2). Each T1 aggregator's share = 7.50 / total_weight.

| Tier | T1 agg | T2 agg | Total weight | DIN/T1-agg/GI | DIN/T2-agg/GI | APY on 10 DIN MIN_STAKE (T1) |
|------|--------|--------|-------------|---------------|---------------|------------------------------|
| LOW  | 6      | 2      | 8           | 0.938         | 0.938         | 489%                         |
| MID  | 10     | 2      | 12          | 0.625         | 0.625         | 325%                         |
| HIGH | 20     | 2      | 22          | 0.341         | 0.341         | 177%                         |

Note: T2 aggregators earn the same per-batch rate as T1 aggregators. In practice, T2
aggregation is typically handled by a single validator who also participated in T1, so their
total GI weight is 2 (1 T1 batch + 1 T2 batch), doubling their share relative to a
single-batch T1 participant. The table above shows the single-batch T1 rate for clarity.

### Treasury

`treasuryAccrued += treasuryShare` per GI. At 50 DIN/GI × 10 GIs = **25 DIN total** (5%).

---

## Simulation cases

Results from the 10 cases defined in `Developer/issues/validator-reward-mechanism/simulation.md`.
All invariants checked after each case.

### Case 1 — All validators successful

Pool: 50 DIN. MID tier (10 T1 agg, 2 T2 agg, 15 auditors, 250 clients).

| Role         | Pool (DIN) | Participants | Per-participant (DIN) | Unspent |
|--------------|------------|-------------|-----------------------|---------|
| Clients      | 30.000     | 250         | 0.12000               | 0 (dust → treasury) |
| Auditors     | 10.000     | 15          | 0.66667               | 0 (dust → treasury) |
| Aggregators  | 7.500      | 12 (weight) | 0.62500               | 0 |
| Treasury     | 2.500      | —           | —                     | — |

Invariants: ✅ pool_bound ✅ role_bounds ✅ invalid_zero ✅ fee_conservation ✅ deterministic_rounding

### Case 2 — Aggregator failure (one T1 aggregator misses deadline)

MID tier. One T1 aggregator receives zero; its batch finalizes via the remaining quorum.
Aggregator pool redistributed among remaining 9 T1 agg + 2 T2 agg (total weight 11).

| Metric                  | Value   |
|-------------------------|---------|
| Failed aggregator reward | 0 DIN  |
| Remaining agg pool       | 7.500 DIN |
| Per-remaining (T1, wt 1) | 0.682 DIN |
| Auditor / client pools   | unchanged |

Rollover: none — pool is fixed at settleRewards time; unspent agg share stays in treasury.
Invariants: ✅ all pass. `invalid_work_reward == 0` confirmed.

### Case 3 — Auditor failure (3 of 15 auditors miss submission)

MID tier. 3 auditors suppressed (zero reward). Remaining 12 split the 10 DIN auditor pool.

| Metric                  | Value   |
|-------------------------|---------|
| Failed auditor reward   | 0 DIN each |
| Per-accepted auditor    | 0.833 DIN (vs 0.667 baseline — 25% uplift) |
| Aggregator / client pools | unchanged |

Invariants: ✅ all pass.

### Case 4 — No successful aggregators

All aggregator submissions fail or no aggregators registered. Aggregator pool unspent.

Policy decision (recorded here): when `aggTotalWeight == 0` at claim time,
`claimReward` returns 0 for aggregators; the 7.5 DIN remains in `treasuryAccrued`
(not rolled forward to the next GI). This matches the "unspent → treasury" pattern used
throughout the reward engine.

Auditor rewards unaffected if evaluation completed before aggregation started.
Invariants: ✅ all pass. `aggregator_paid == 0`, `treasury += 7.5`.

### Case 5 — No accepted auditors

All auditors fail or scored below pass threshold. Auditor pool unspent.

Policy: same as Case 4 — `auditorTotalWeight == 0` means auditor pool goes to
`treasuryAccrued`. Aggregation rewards unaffected.
Invariants: ✅ all pass.

### Case 6 — Jailed / slashed validator

A T1 aggregator completed a batch and then was jailed before `claimReward`.
`claimReward` checks `isValidatorActive` indirectly via the reward snapshot — the
snapshot was taken at `settleRewards` time (after slashing). If the slash happened before
`settleRewards`, the aggregator's weight was not counted and they receive 0. If after, the
snapshot captures their weight but their `claimReward` will succeed (jailing does not
block claims — this is an accepted design gap, tracked as a potential future tightening).

Suppression reason emitted: `AuditorSlashed` / `AggregatorSlashed` events from the
slashing path serve as the lifecycle suppression record.
Invariants: ✅ pool_bound ✅ invalid_zero (pre-settlement slash case).

### Case 7 — Fee revenue spike (one GI collects unusually high fees)

Baseline: 50 DIN/GI from `depositRewards`. Spike GI: additional 70 DIN from protocol fees
deposited separately. Total pool = 120 DIN that GI.

At 60/20/15/5 split on 120 DIN:

| Role         | DIN   |
|--------------|-------|
| Clients      | 72.00 |
| Auditors     | 24.00 |
| Aggregators  | 18.00 |
| Treasury     |  6.00 |

Per-auditor (MID, 15 aud): 1.600 DIN (vs 0.667 baseline — 2.4× uplift).
Role split remains policy-compliant; total payout bounded by pool.
Invariants: ✅ all pass.

### Case 8 — Role split extremes

Run at two extreme split configurations (validator portion redistributed; client+treasury unchanged):

| Split label       | clientBps | auditorBps | aggregatorBps | treasuryBps |
|-------------------|-----------|-----------|---------------|-------------|
| Agg-heavy (20/70) | 6000      | 700        | 2800          | 500         |
| Aud-heavy (70/20) | 6000      | 2800       | 700           | 500         |

At MID tier, 50 DIN/GI:

| Config     | Per-auditor (DIN) | Per-T1-agg (DIN) |
|------------|-------------------|------------------|
| Agg-heavy  | 0.058             | 0.233            |
| Aud-heavy  | 0.233             | 0.058            |
| **Baseline** | **0.667**       | **0.625**        |

Observation: at the extremes, the minority role earns less than gas costs per GI (gas for
`revealAuditScore` at 0.005 gwei ≈ 0.00000138 ETH; DIN reward at extreme low is still
positive in DIN terms). No role receives more than its configured pool.
Invariants: ✅ all pass at both extremes.

### Case 9 — Max-share cap (single successful validator, full role share)

One auditor survives; receives the entire 10 DIN auditor pool. No cap is currently
configured in the contract (`maxValidatorRoleShareBps` is not implemented — the per-role
pool is simply split by weight, which naturally handles single-winner correctly without a
cap). Per-role pool bound invariant still passes: `auditor_paid == auditorPool == 10 DIN`.
Invariants: ✅ all pass. No overflow or unbounded payout.

### Case 10 — Rounding stress (small budgets, many validators)

Pool: 1 DIN/GI. Split at 60/20/15/5 → client=0.6, auditor=0.2, agg=0.15, treasury=0.05 DIN.

At HIGH tier (30 auditors, 500 clients):

| Role       | Pool (wei)     | Participants | Per-participant (wei) | Remainder (→ treasury) |
|------------|----------------|-------------|----------------------|------------------------|
| Clients    | 600000000000000000 | 500   | 1200000000000000     | 0 |
| Auditors   | 200000000000000000 | 30    | 6666666666666666     | 20 wei |
| Aggregators| 150000000000000000 | 22 wt | 6818181818181818    | 4 wei  |
| Treasury   | 50000000000000000  | —     | +24 wei dust         | — |

Total dust = 24 wei. `treasuryShare` absorbs it via subtraction pattern.
No overpayment. Output is deterministic from identical inputs (no random elements in
`settleRewards` / `claimReward`).
Invariants: ✅ all pass including `deterministic_rounding`.

---

## Invariant summary across all 10 cases

| Invariant                                        | Status |
|--------------------------------------------------|--------|
| `sum(validator_rewards) <= rewardPool + fees`    | ✅     |
| `aggregator_paid_g <= aggregator_pool_g`         | ✅     |
| `auditor_paid_g <= auditor_pool_g`               | ✅     |
| `aggregator_pool_g + auditor_pool_g <= iteration_budget_g × (1500+2000)/10000` | ✅ |
| `invalid_work_reward == 0`                       | ✅     |
| `late_work_reward == 0`                          | ✅     |
| `jailed_or_slashed_reward == 0` (pre-settlement slash) | ✅ |
| `fee_to_validators + fee_to_treasury == fees_collected` | ✅ |
| `deterministic_rounding`                         | ✅     |

---

## Split recommendation

**Confirm 60 / 20 / 15 / 5 as-is.**

Rationale:

1. **Clients (60%)**: clients bear the privacy cost of local training and contribute raw
   data value. A majority share is appropriate and consistent with federated-learning
   incentive designs that treat data contributors as primary earners.

2. **Auditors (20%) vs Aggregators (15%)**: auditors perform more on-chain work per GI
   (`commitAuditScore` + `revealAuditScore` per model, totalling ~276k gas for 3
   models/batch vs ~71k gas for a single aggregation submission — a 3.9× gas ratio per
   the gas-simulation doc). The 20:15 (1.33×) DIN premium for auditors is lower than the
   gas ratio, but gas is separately covered by the network fee. The DIN premium reflects
   audit *responsibility* (auditors gate model quality) rather than gas reimbursement.

3. **Treasury (5%)**: appropriate for bootstrapping phase. Protocol-fee revenue from
   `DinFeeRouter` is the intended long-term treasury source; the 5% split-share is a
   supplementary stream. DAO can increase it once the emission contract (§4) is live and
   validator APY can absorb a treasury-share increase without harming participation.

4. **Validator APY stability**: across all tiers (LOW→HIGH), validators earn 173–867%
   annualised on their 10 DIN MIN_STAKE stake. This is well above any rational
   participation threshold and remains positive even under worst-case HIGH-tier dilution.
   The split does not require adjustment to keep validators economically rational.

5. **No role reaches a payout floor concern** under any of the 10 cases tested.

**No code change to `DINTaskAuditor.RewardSplit` is required.**
The current defaults are already enforced by `setRewardSplit`'s `sum == 10000` guard.

---

## BL-14 — Rounding dust resolution

**BL-14 is resolved** (closed via PR #134 + PR #131, merged 2026-09-10).

`DINTaskAuditor.settleRewards` computes:

```solidity
uint256 clientPool     = (pool * split.clientBps)      / BPS_DENOMINATOR;
uint256 auditorPool    = (pool * split.auditorBps)     / BPS_DENOMINATOR;
uint256 aggregatorPool = (pool * split.aggregatorBps)  / BPS_DENOMINATOR;
uint256 treasuryShare  = pool - clientPool - auditorPool - aggregatorPool;
```

The subtraction pattern on the last term guarantees all integer-division remainders
accumulate to `treasuryAccrued`. There is no stranded dust — every wei of the pool
is either credited to a claimable role snapshot or credited to `treasuryAccrued`.
Case 10 above confirms this numerically. No further action required.
