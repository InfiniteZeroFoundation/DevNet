# GI abort: recovering a stalled Global Iteration (issue #222, BL-30)

**Status:** proposal for review. Nothing here is implemented. Per the P3 rule, contract work starts only once this design is agreed and recorded in [MECHANISM_DESIGN.md](MECHANISM_DESIGN.md).

**Decided policy (Abraham, [#222](https://github.com/InfiniteZeroFoundation/DevNet/issues/222), 2026-10-26):** anyone may abort once a GI has been stalled past a timeout, with no early abort; locked rewards go back to whoever funded them; the GI's registration slots are released; participants who failed to reveal are still penalised under the existing rules, and honest participants are not; engineers propose the timeout value. This note turns that policy into a contract design and sizes it.

## 1. The problem

`finalizeT1Aggregation` / `finalizeT2Aggregation` revert the whole call when any one batch has no winning CID or fewer than 2 of 3 reveals ([`DINTaskCoordinator.sol`](../../foundry/src/DINTaskCoordinator.sol)). `endGI` needs `AggregatorsSlashed`, and `startGI` needs `GenesisModelCreated` or `GIended`. Nothing can skip a batch or end the GI early. So two aggregators who never reveal stop the model for good, and its reward pool and the validators' registration slots stay locked. The same happens if the model owner simply stops calling the phase functions, since almost every transition is `onlyOwner`.

The task contracts are not upgradeable. An abort path only helps models deployed after it lands, so it has to be in before the DevNet 2.0 deploy ([#284](https://github.com/InfiniteZeroFoundation/DevNet/issues/284)).

## 2. Proposed design

### 2.1 Stall detection

- Add `uint64 giStateChangedAt` to `DINTaskCoordinator` and set it in the existing `_setGIstate` (one extra SSTORE per transition, and `_setGIstate` is already the single place every transition goes through).
- A GI counts as **stalled** when `block.timestamp >= giStateChangedAt + giAbortTimeout` and the state is neither `GenesisModelCreated`, `GIended` nor `GIaborted`.
- The timer measures time since the last transition, not since `startGI`. A GI that is still making progress can't be aborted however long it runs, and one that stops anywhere, whether it's owner-driven or a missing reveal quorum, becomes abortable after the timeout.

### 2.2 `abortGI(gi)`: permissionless

- `abortGI(uint gi)`: `onlyCurrentGI(gi)`, reverts `TC_GINotStalled` unless stalled, then `_setGIstate(GIaborted)` and calls `dinTaskAuditorContract.onGIAborted(gi)`.
- **New terminal state `GIaborted`, appended after `GIended` (ordinal 29).** Appending, unlike the earlier mid-enum insertions, keeps every existing ordinal stable for `dincli/cli/utils.py`'s mirrors and the subgraph's `GIStateChanged` mapping.
- `_startGI` accepts `GIaborted` as well as `GenesisModelCreated` / `GIended`, so the model can run GI + 1 straight after an abort. The genesis/global model carries over unchanged, since the aborted GI never produced a new one.

### 2.3 Rewards: refunded to their funders (pull)

`depositRewards` is open to anyone and today records only the pooled `giRewardPool[gi]`. Refunding to funders needs per-funder attribution:

- `DINTaskAuditor.depositRewards` additionally records `rewardDeposits[gi][msg.sender] += amount` (one extra SSTORE per deposit; deposits are rare).
- `onGIAborted(gi)` (`onlyTaskCoordinator`) sets `giAborted[gi] = true`. It loops over nothing.
- `refundAbortedRewards(gi)`: the caller withdraws their own `rewardDeposits[gi][msg.sender]`, which is then zeroed. This is a pull, like `claimReward`, so it stays O(1).
- An aborted GI never reaches `settleRewards`, so `claimReward` already reverts for it (`TA_RewardsNotSettled`), and nobody else can claim the pool.

**Emission-funded amounts go to the treasury, not back into the schedule.** `DinEmission.fundGI` is the `msg.sender` of its deposits, so its refund belongs to the emission contract. Add a permissionless `DinEmission.reclaimAborted(taskAuditor, gi)` that calls `refundAbortedRewards(gi)` and forwards the DIN to the treasury. Returning it to the schedule would let the emission be re-used, which the policy rules out. Burning is the alternative Abraham left open. **Recommendation: treasury**, matching how slashed and stranded DIN is already handled (`_forwardToTreasury`) and keeping supply effects in one place. `DinEmission` has about 20 KB of headroom, so this costs nothing that matters.

### 2.4 Registration slots

`releaseGIRegistrationSlots(gi)` already does the work, bounded by `MAX_REGISTERED_AGGREGATORS` / `MAX_REGISTERED_AUDITORS` and guarded against a second call. Two changes:

- Treat `GIaborted` like `GIended` in its ended-GI check.
- **Drop `onlyOwner`.** The function is idempotent and only valid for an ended GI, so making it permissionless is safe, and the abort path then never depends on the owner. It also removes bytecode.

`abortGI` itself does not loop over registrants.

### 2.5 Penalties: only the faults the stall reveals

Validators can only cause a stall in the T1/T2 reveal phases. Evaluation tolerates non-votes, and every other transition is owner-driven. So:

- **Stalled in `T1AggregationRevealStarted` / `T2AggregationRevealStarted`:** `abortGI` applies the existing S2 liveness slash (`AGG_T1_NO_SUBMISSION` / `AGG_T2_NO_SUBMISSION`, `s2SlashFractionBps`) to every assigned aggregator in that tier's batches who did not reveal. It reuses the per-batch S2 loop already in `slashAggregators`, factored into an internal helper that both call. These slashes feed the per-slasher and global S5 rings as usual. There's no `BAD_CONSENSUS` slash, because no consensus was ever reached.
- **Stalled anywhere else:** no slashing. The stall is the owner's inaction, and nobody else is at fault. The owner pays through the delay and the lost GI, and their deposit comes back to them, so there is no gain in stalling on purpose.
- Auditors' S1 slashes for the GI are not run on abort. `slashAuditors` needs `T2AggregationDone`, and an aborted GI ends before that. Auditor non-votes in an aborted GI go unpenalised, which is consistent with the honest-only rule, since nobody is paid either.

### 2.6 Timeout value

Proposed testnet default: **`giAbortTimeout` = 3 days**. It's an owner-settable parameter with a hard cap (`MAX_GI_ABORT_TIMEOUT` = 30 days), so the owner can't set it so high that abort is effectively disabled, and a floor (1 day) so it can't be used for an early abort. 3 days is well above any phase window used on DevNet today and short enough that validators' slots and funders' DIN aren't locked for long. The final value goes into [#155](https://github.com/InfiniteZeroFoundation/DevNet/issues/155) with the other testnet parameters.

## 3. Contract size: this needs room made first

| Contract | Today (Nov 13, via_ir) | Margin under EIP-170 | Above the 1,024 B fail line |
|---|---|---|---|
| `DINTaskCoordinator` | 23,321 B | 1,255 B | 231 B |
| `DINTaskAuditor` | 21,887 B | 2,689 B | 1,665 B |

Rough cost on the coordinator: `giStateChangedAt` and its write, `abortGI`, the timeout setter with bounds, three new errors, the `_startGI` and `releaseGIRegistrationSlots` condition changes, and the stalled-tier S2 call come to an **estimated 500–800 B**. That would push the coordinator past the CI gate's fail line. The auditor side (`rewardDeposits`, `onGIAborted`, `refundAbortedRewards`) is roughly 300–400 B, which fits.

**Sequencing:** do a size-reduction PR on `DINTaskCoordinator` first ([#201](https://github.com/InfiniteZeroFoundation/DevNet/issues/201) Part A), then the abort. The biggest candidate is deduplicating the T1/T2 paths: `commitT*`, `revealT*` and `finalizeT*Aggregation` are near-identical per tier. One tier-parameterised internal each (the `TierKind` enum already exists for the commit hash) should save well over 1 KB. That also leaves room for [#194](https://github.com/InfiniteZeroFoundation/DevNet/issues/194) and the #201 Part B slash reason, which add coordinator code too.

## 4. What this design leaves out

- **Skipping a single stuck batch and continuing the GI.** This was rejected as the default. T2 combines every T1 result, so continuing without one batch changes the model, and it needs its own rules for rewards and disputes. A full abort is simpler and matches the decided policy.
- **Who pays gas for an abort.** Nobody is reimbursed. Funders and blocked validators have the incentive to call it themselves.
- **Disputes open at abort time.** Bonds of disputes still active when the GI aborts are returned to the challengers. Nobody adjudicates, and since the challenger isn't at fault, the bond shouldn't be forfeited. This needs a check in the dispute paths during implementation.

## 5. Questions for review

1. Timeout default: 3 days, owner-settable between 1 and 30 days?
2. Emission refund: treasury (recommended) or burn?
3. Is it acceptable that auditors aren't S1-slashed when a GI aborts (§2.5)?
4. Size-reduction PR (T1/T2 dedup) before the abort PR, as in §3?

## Verification plan (for the implementation PR)

- Unit tests:
  - abort reverts before the timeout and succeeds after it, from each stallable state
  - no early abort right after a transition
  - `startGI(gi + 1)` works after an abort
  - each funder, including `DinEmission` via `reclaimAborted`, gets back exactly what they deposited, and a second refund reverts
  - `claimReward` reverts for the aborted GI
  - slots are released by a non-owner
  - stalled-tier non-revealers are S2-slashed and revealers are not
  - S5 rings count the abort slashes
- Add an adversarial scenario to `P3Adversarial.t.sol`: 2 of 3 T1 aggregators withhold reveals, the GI aborts after the timeout, the next GI runs.
- Contract size gate in CI, and `dincli`: a `model-owner gi abort` (or any-role) command plus the `GIaborted` state in `dincli/cli/utils.py`.
