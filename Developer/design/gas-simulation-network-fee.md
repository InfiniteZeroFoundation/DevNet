# Gas Simulation — Validator Network Fee Sizing

**Status:** Complete (issue #78, updated task_100926_12)
**Owner:** Robbert
**Tracking:** [GitHub issue #78](https://github.com/InfiniteZeroFoundation/DevNet/issues/78)
**Simulation code:** `foundry/test/GasSimulation.t.sol`
**Run:** `forge clean && forge test --match-contract GasSimulationTest -vv`
**All 19 tests pass** (re-measured at task_100926_12 baseline; `commitAuditScore` added).

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
(`_tryFinalizeEligibility` fires there, not at commit time). `commitAuditScore` is now
also measured here (task_100926_12 #78), closing the Open Item below.

### `commitAuditScore` (cold, first commit for a batch/model slot)

Gas is per-call constant regardless of participation scale (confirmed at LOW/MID/HIGH):

| Call | Gas | ETH @ 0.005 gwei |
|------|-----|-----------------|
| `commitAuditScore` (cold SSTORE) | 56,474 | 0.000000282 |

### `revealAuditScore`

Re-measured at task_100926_12 baseline (post-#65, #63, #124-134 merges):

| Call | Gas | ETH @ 0.005 gwei |
|------|-----|-----------------|
| `revealAuditScore` (cold, below quorum) | 137,272 | 0.000000686 |
| `revealAuditScore` (quorum-trigger vote) | 110,600 | 0.000000553 |

The cold call (first reveal for a model) costs slightly more than the quorum-trigger call.
The absolute numbers are higher than the initial post-#63 measurement due to additional
storage writes from subsequent merges (#65 stake tracking, #124-134 slashing/treasury wires).

**For fee-floor purposes: use 56,474 (commit) + 137,272 (reveal) = 193,746 gas per model.**

**Per-auditor gas per GI** (default 3 models/batch, commit + reveal both counted):
```
3 × (56,474 + 137,272) = 3 × 193,746 = 581,238 gas
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
| Auditor (3 models, commit + reveal) | 581,238 | 0.000000581 | 0.00000291 | 0.0000116 |

The **auditor role is the most gas-intensive** at ~8.1× a single aggregator submission
(up from the prior 3.9× estimate, which only counted `revealAuditScore`).  The fee floor
must be set to cover the auditor's cost, or auditors will lose ETH net of gas.

### Recommended floor

```
fee_floor_ETH = 581,238 gas × gas_price_ETH
```

(Replaces the previous 275,916-gas provisional floor; prior floor excluded `commitAuditScore`.)

The on-chain parameter `DINTaskCoordinator.networkFeeFloor` (added task_100926_12 #78,
setter `setNetworkFeeFloor`) carries this value in gas units for DAO governance.
Enforcement point (where the deposited reward pool is checked against
`networkFeeFloor × nValidators`) to be confirmed with Umer before the next release.

| Gas price | Fee floor per validator per GI |
|-----------|-------------------------------|
| 0.001 gwei (L2 quiet) | 0.000000581 ETH (~$0.00186 at $3,200/ETH) |
| 0.005 gwei (L2 typical) | 0.00000291 ETH (~$0.0093) |
| 0.02 gwei (L2 busy) | 0.0000116 ETH (~$0.037) |

These are per-validator figures. The model trainer pays the total across all validators
participating in their GI. At LOW tier (21 validators) and 0.005 gwei, the total network
fee per GI would be approximately **0.000061 ETH (~$0.20)**.

### Sensitivity table

| Tier | Validators | Total gas (auditor path) | Fee (0.001 gwei) | Fee (0.005 gwei) | Fee (0.02 gwei) |
|------|-----------|--------------------------|-----------------|-----------------|----------------|
| LOW (3 batches) | 21 | 12,205,998 | 0.0000122 ETH | 0.000061 ETH | 0.000244 ETH |
| MID (5 batches) | 36 | 20,924,568 | 0.0000209 ETH | 0.0001046 ETH | 0.000419 ETH |
| HIGH (10 batches) | 63 | 36,617,994 | 0.0000366 ETH | 0.0001831 ETH | 0.000732 ETH |

All tiers remain economically tractable at all tested gas prices — even at HIGH tier and
busy-L2 prices the total fee is well under $1 per GI.

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

- ~~**`commitAuditScore` gas is not yet in the fee floor**~~ — **Resolved (task_100926_12 #78).**
  `commitAuditScore` measured at 56,474 gas (cold); folded into the fee floor above.
  `DINTaskCoordinator.setNetworkFeeFloor` carries the result for DAO governance.
- **Enforcement point for `networkFeeFloor`:** `depositRewards` / `startGI` should reject
  a reward pool that can't cover `networkFeeFloor × nExpectedValidators`.  Enforcement
  point to confirm with Umer before the next release.
- **Gas price oracle:** The fee floor should track actual Optimism gas prices rather than
  a fixed constant. At steady state, validators should self-report or a TWAP from L1 gas
  oracles could feed into the fee setter.
- **`slashAuditors` with actual slashes:** The simulation ran with all auditors voting
  (0 slashed). A follow-up measurement with 1/3 slashed per batch would give the marginal
  per-slash cost for auditors precisely (estimated at ~23,500 gas/slash from aggregator data).
- **Reward split:** Out of scope here; see MECHANISM_DESIGN §5 for the (clients/validators/
  treasury) split discussion.
- **Spec-level audit params:** At spec params (10 auditors/batch, 100 models/batch), the
  auditor cost per GI scales significantly — warrants a separate measurement run once those
  params are adopted.
