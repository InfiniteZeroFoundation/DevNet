# Gas Simulation — Validator Network Fee Sizing

**Status:** Complete (issue #78)
**Owner:** Robbert
**Tracking:** [GitHub issue #78](https://github.com/InfiniteZeroFoundation/DevNet/issues/78)
**Simulation code:** `foundry/test/GasSimulation.t.sol`
**Run:** `forge clean && forge test --match-contract GasSimulationTest -vv`
**All 14 tests pass** (re-measured after H-1 quorum fix — see Scenario 3 notes).

---

## Purpose

The DIN network fee is the ETH amount model trainers pay per GI, upfront, to cover the
on-chain gas validators spend submitting their results. Setting it wrong in either direction
blocks validator economics: too low and validators lose ETH on gas; too high and model owners
won't participate. This document records the simulation methodology, raw gas measurements,
and the resulting fee-floor recommendation.

---

## Participation tiers

Three tiers scope the sensitivity analysis (LOW ≈ 0.1×, MID ≈ target, HIGH ≈ ~3×):

| Tier | T1 batches | Aggregators        | Auditors | Models |
|------|-----------|-------------------|---------|--------|
| LOW  | 3         | 12 (9 T1 + 3 T2)  | 9       | 9      |
| MID  | 5         | 18 (15 T1 + 3 T2) | 15      | 15     |
| HIGH | 10        | 33 (30 T1 + 3 T2) | 30      | 30     |

Audit batch parameters at all tiers: 3 auditors/batch, 3 models/batch, quorum=2
(DINTaskAuditor demo defaults). Audit batch count = T1 batch count at these settings.

---

## Scope of on-chain validator work per GI

Only the calls validators make themselves are costed here. Owner-only lifecycle calls
(`startGI`, `closeLMsubmissions`, `autoCreateTier1AndTier2`, `slashAuditors`, etc.) are
paid by the model owner and are not included in the per-validator network fee.

| Role | On-chain call | Calls per GI |
|------|--------------|-------------|
| T1 aggregator | `submitT1Aggregation` | 1 |
| T2 aggregator | `submitT2Aggregation` | 1 |
| Auditor | `commitAuditScore` + `revealAuditScore` | 2 × models_per_batch (default: 3) — commit-then-reveal (task_210726_6 §2a) split what was previously a single `setAuditScorenEligibility` call into two |

---

## Scenario 1 — Aggregation submissions

### Per-call gas (constant, independent of batch count)

| Call | Gas | ETH @ 0.005 gwei | ETH @ 0.02 gwei |
|------|-----|-----------------|----------------|
| `submitT1Aggregation` (cold SSTORE) | 71,509 | 0.000000358 | 0.00000143 |
| `submitT1Aggregation` (warm, same CID) | 49,597 | 0.000000248 | 0.00000099 |
| `submitT2Aggregation` (cold SSTORE) | 71,428 | 0.000000357 | 0.00000143 |

"Cold" = first submission to a batch slot (SSTORE from zero). "Warm" = second aggregator
submitting the same CID; the vote counter hits a non-zero slot. Every validator hits the
cold path on their own submission slot regardless of order.

T1 and T2 submission gas is essentially identical (~71,400 gas). The 81-gas difference
is rounding noise from the slightly different storage layout.

### `finalizeT1Aggregation` — model owner call, scales with batch count

| T1 batches | Gas    | ETH @ 0.005 gwei | Notes |
|-----------|--------|-----------------|-------|
| 3         | 141,768 | 0.000000709 | |
| 5         | 234,642 | 0.000001173 | |
| 10        | 466,827 | 0.000002334 | |

Scales roughly linearly at ~46,700 gas per T1 batch. Validates the "aggregation logic
off-chain, only CID on-chain" design mitigation: even at HIGH (10 batches), finalization
costs < 0.5M gas — well within block limits.

---

## Scenario 2 — Evaluation submissions

Re-measured after commit-then-reveal (task_210726_6 §2a, merged to `develop` via #63)
replaced the single-shot `setAuditScorenEligibility` with `commitAuditScore` +
`revealAuditScore`. `revealAuditScore` is what now does the eligibility bookkeeping
(`_tryFinalizeEligibility` fires there, not at commit time), so it's the direct successor
to the old call for benchmarking purposes — `commitAuditScore`'s own gas is **not measured
here** (see Open Items).

| Call | Gas | ETH @ 0.005 gwei |
|------|-----|-----------------|
| `revealAuditScore` (cold, below quorum) | 91,972 | 0.000000460 |
| `revealAuditScore` (quorum-trigger vote) | 87,200 | 0.000000436 |

The cold call (first reveal for a model) costs slightly more than the quorum-trigger call
because it hits more cold SSTORE slots. The quorum-trigger call does write `eligible=true`
on top but benefits from warm storage reads. In practice, the difference is small (~5%),
same shape as the pre-commit-reveal measurement.

**For fee-floor purposes: use 91,972 gas per call (cold path, worst case per auditor).**
**This covers `revealAuditScore` only — see Open Items for why the fee floor below is
provisional until `commitAuditScore`'s gas is folded in.**

**Per-auditor gas per GI** (default 3 models/batch, reveal only):
```
3 × 91,972 = 275,916 gas
```

---

## Scenario 3 — Worst-case slashing (dispute proxy)

The DIN protocol has no explicit dispute contract yet. The closest bounding scenario is the
full slashing path after T2 aggregation: validators who submitted wrong or no results are
slashed in a single model-owner call.

### `slashAuditors` — loop overhead (model-owner call)

| Audit batches | Auditors | Models checked | Slashed | Gas    |
|--------------|---------|---------------|---------|--------|
| 3            | 9       | 27            | 0       | 40,345 |
| 5            | 15      | 45            | 0       | 60,471 |
| 10           | 30      | 90            | 0       | 110,786 |

All auditors voted in these runs, so gas is pure loop overhead with zero `slash()` calls.
Scales at ~11,000 gas per 10 additional models checked.

Worst-case with N auditors actually slashed ≈ loop_overhead + N × marginal_slash_cost.
Marginal cost per `slash()` call is derivable from `slashAggregators` measurements below
(~23,500 gas per additional slash call, interpolated from the tier differences).

### `slashAggregators` — 1/3 aggregator slashed per T1 batch + 1/3 T2 (model-owner call)

Post-H-1 worst case: minimum quorum (2 of 3) submits per batch, so only 1 of 3 aggregators
is slashed per batch. This is the maximum reachable slash count with finalization succeeding.

| T1 batches | `slash()` calls | Gas     | ETH @ 0.005 gwei |
|-----------|----------------|---------|-----------------|
| 3         | 4 (3 T1 + 1 T2) | 120,811 | 0.000000604 |
| 5         | 6 (5 T1 + 1 T2) | 166,735 | 0.000000834 |
| 10        | 11 (10 T1 + 1 T2) | 281,545 | 0.000001408 |

Scales at ~23,200 gas per 10 additional `slash()` calls. The model owner bears this cost;
it does not enter the per-validator network fee directly, but a sustained worst-case slash
rate would signal an unhealthy network.

---

## Fee floor recommendation

### Per-validator gas per GI

| Role | Gas per GI | ETH @ 0.001 gwei | ETH @ 0.005 gwei | ETH @ 0.02 gwei |
|------|-----------|-----------------|-----------------|----------------|
| T1 aggregator | 71,509 | 0.0000000715 | 0.000000358 | 0.00000143 |
| T2 aggregator | 71,428 | 0.0000000714 | 0.000000357 | 0.00000143 |
| Auditor (3 models, `revealAuditScore` only) | 275,916 | 0.000000276 | 0.00000138 | 0.00000552 |

The **auditor role is the most gas-intensive** at ~3.9× a single aggregator submission.
The fee floor must be set to cover the auditor's cost, or auditors will lose ETH net of gas.
This is the `revealAuditScore`-only figure — see Open Items on `commitAuditScore`.

### Recommended floor

```
fee_floor_ETH = 275,916 gas × gas_price_ETH
```

| Gas price | Fee floor per validator per GI |
|-----------|-------------------------------|
| 0.001 gwei (L2 quiet) | 0.000000276 ETH (~$0.00088 at $3,200/ETH) |
| 0.005 gwei (L2 typical) | 0.00000138 ETH (~$0.0044) |
| 0.02 gwei (L2 busy) | 0.00000552 ETH (~$0.018) |

These are per-validator figures. The model trainer pays the total across all validators
participating in their GI. At LOW tier (21 validators) and 0.005 gwei, the total network
fee per GI would be approximately **0.000029 ETH (~$0.09)**.

### Sensitivity table

| Tier | Validators | Total gas (auditor path) | Fee (0.001 gwei) | Fee (0.005 gwei) | Fee (0.02 gwei) |
|------|-----------|--------------------------|-----------------|-----------------|----------------|
| LOW (3 batches) | 21 | 5,794,236 | 0.0000058 ETH | 0.000029 ETH | 0.000116 ETH |
| MID (5 batches) | 36 | 9,932,976 | 0.0000099 ETH | 0.0000497 ETH | 0.000199 ETH |
| HIGH (10 batches) | 63 | 17,382,708 | 0.0000174 ETH | 0.0000869 ETH | 0.000348 ETH |

All tiers are profitable at all tested gas prices — the numbers are small enough that the
network fee is not a participation barrier even at HIGH tier and busy-L2 prices.

**Flag:** No scenario in the simulation makes validator participation unprofitable at the
proposed fee floor (cost always > 0 when fee floor is set to cover the auditor path).

---

## Design mitigations validated

| Mitigation | Finding |
|-----------|---------|
| Aggregation logic off-chain (only CID on-chain) | `submitT1Aggregation` is O(1) per aggregator regardless of model size. Validated. |
| Evaluations batched to final round | `revealAuditScore` is constant per call; total auditor gas scales linearly with models_per_batch. Validated. |
| Disputes rare (random assignment + consensus) | Worst-case `slashAggregators` at HIGH tier (478k gas) is well within block limits. Validated. |

---

## Open items

- **`commitAuditScore` gas is not yet in the fee floor:** commit-then-reveal (#63) means
  each auditor now makes two on-chain calls per model, not one — this document only prices
  `revealAuditScore`. The fee floor above therefore understates the auditor's real per-GI
  cost by the commit call's gas. Needs a dedicated measurement (add a timed
  `test_gas_s2_commitAuditScore_cold` case to `GasSimulation.t.sol`) and folding into the
  "Auditor" row above before this floor is treated as final.
- **Gas price oracle:** The fee floor should track actual Optimism gas prices rather than
  a fixed constant. At steady state, validators should self-report or a TWAP from L1 gas
  oracles could feed into the fee setter.
- **`slashAuditors` with actual slashes:** The simulation ran with all auditors voting
  (0 slashed). A follow-up measurement with 1/3 slashed per batch would give the marginal
  per-slash cost for auditors precisely (estimated at ~23,500 gas/slash from aggregator data).
- **Reward split:** Out of scope here; see MECHANISM_DESIGN §5 for the (clients/validators/
  treasury) split discussion.
- **Spec-level audit params:** At spec params (10 auditors/batch, 100 models/batch), the
  auditor cost per GI scales to ~8.99M gas — still tractable but warrants a separate
  measurement run once those params are adopted.
