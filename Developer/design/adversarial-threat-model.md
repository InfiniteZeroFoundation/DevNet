# Adversarial threat model — DIN Protocol (task_240926_17, Part 1)

**Status:** Draft — revised after verification review of PR #182  
**Date:** 2026-09-28 (revised 2026-09-28)  
**Base:** `develop` @ `1e049e9` (`foundry/src` unchanged since post-PR-#171/#172/#173)  
**Author:** @robertocarlous

This is a targeted threat model for the DIN Protocol on-chain coordination layer.
It does not cover off-chain model training, IPFS layer security, or the CLI.
Each scenario maps to one `test_defended_…`, `test_costBounded_…`, or `test_knownGap_…`
entry in `foundry/test/P3Adversarial.t.sol`.

---

## Scenario matrix

### Row 1 — Sybil N-identity no-participation

| Field | Value |
|---|---|
| **Attacker** | Sybil operator: N validator identities, each staking MIN_STAKE |
| **Capability** | Creates N accounts, deposits MIN_STAKE per account, registers each GI, never submits |
| **Protocol response today** | Concurrent-registration cap gates each address: `maxAllowed = stake / MIN_STAKE × capPerUnit` (`DINTaskCoordinator.sol:386-390`). **The cap is off by default** — `maxConcurrentRegistrationsPerStakeUnit == 0` means N Sybil addresses with MIN_STAKE each all register freely regardless of cap. Registered aggregators that batches don't need are never assigned — `autoCreateTier1AndTier2` fills batches greedily in groups of 3 (`DINTaskCoordinator.sol:551-591`); excess registrants are skipped and **face no S2 and no S5 penalty**. An identity assigned to a batch and then failing to submit receives `slashPartial` (S2: `AGG_T1_NO_SUBMISSION`, 30% of minStake) escalating to full `MIN_STAKE` + jail on the 3rd miss (S5). S6 (`recordNoParticipation`) has no call site in either task contract — the no-participation slash exists in `DinValidatorStake` but the GI flow never reaches it. |
| **Expected test outcome** | **COST-BOUNDED** — the attack cost is N × MIN_STAKE stake locked per registered identity. The test asserts: (a) N Sybil identities can all register (no identity-level barrier); (b) unassigned identities face no penalty; (c) an assigned identity that fails to submit receives S2 (AGG_T1_NO_SUBMISSION) and, on the 3rd such GI, S5 escalation. |
| **Trust assumption** | MIN_STAKE and the batch-size/registered-validator ratio together determine the minimum stake cost to reliably control majority of a batch. Requires calibration. |

---

### Row 2 — Sybil seat capture in audit batch or T1 subgroup

| Field | Value |
|---|---|
| **Attacker** | Sybil operator: k identities, each staking MIN_STAKE, targeting k-of-n seats in one batch |
| **Capability** | k × MIN_STAKE total stake; no control of randomness — batch assignment is `_shuffleAddressArray(valPool, keccak256(seed, "AGG_ADDR"))` (`DINTaskCoordinator.sol:582`) and auditor seat assignment is `_shuffleAddressArray(auditorPool, keccak256(seed, "AUD_ADDR"))` (`DINTaskAuditor.sol:871`), where `seed` is the per-GI `aggSeed`/`auditSeed`: anchored to a future block (`block.number + disputeSeedDelay`) at the preceding GI-state transition and locked permissionlessly via `lockAggSeed`/`lockAuditSeed` (issue #156 H-2, PR #191). `autoCreateTier1AndTier2` and `createAuditorsBatches` are still `onlyOwner`, but revert unless the seed is locked, so the block the owner calls in no longer changes the shuffle. |
| **Protocol response today** | No Sybil-specific defence beyond the per-identity stake requirement. Owner block-picking of the seat shuffle is closed by the H-2 fix: the seed is fixed at a block not yet mined when it is anchored, and batch creation reads the stored seed (`test_createAuditorsBatches_timingIndependent` / `test_autoCreateTier1AndTier2_timingIndependent` in `SecurityFindings.t.sol`). Residuals remain (BL-26): the owner can decline to lock a seed they dislike and let it re-anchor after the ~256-block `blockhash` window (a repeatable re-roll while nobody else locks — aggregator/auditor dincli now locks the seed from the validator side to narrow this), and a validator can unstake between lock and batch creation to reshape the active pool. The seed also trusts the sequencer not to grind `blockhash` (TA-4). None of this changes the Sybil-cost framing below — k identities still win seats at the hypergeometric rate. |
| **Expected test outcome** | **COST-BOUNDED** — the test sets up n registered identities, k of which are Sybil. P(Sybil controls ≥ majority of a 3-seat batch) is hypergeometric: ≈ 3p² − 2p³ where p = k/n (not k/n). The test asserts the fraction of batches where Sybil controls majority and the total stake cost is k × MIN_STAKE. |
| **Trust assumption** | n (total registered validators) large enough that k × MIN_STAKE to control majority is economically prohibitive relative to poisoned-model gain (TA-3); seat-shuffle seed not ground by the sequencer (TA-4). |

---

### Row 3 — Recidivist missing votes → S5 escalation and jail

| Field | Value |
|---|---|
| **Attacker** | Validator repeatedly misses S1 votes (or S2 submissions) across GIs |
| **Capability** | Registers each GI, never votes; tolerates a partial slash each time |
| **Protocol response today** | `slashPartial` in `DinValidatorStake.sol:294` maintains a per-validator, **per-slasher-contract** rolling GI list (`_partialSlashGIs[validator][msg.sender]`). When slashes within the last `s5RecidivismWindow` (default: 5) GIs for that slasher reach `s5RecidivismThreshold` (default: 3), the slash is escalated to full `MIN_STAKE` and the validator is jailed for `s5JailDuration` (default: 7 days). `isValidatorActive` returns `false` while jailed, blocking re-registration. |
| **Expected test outcome** | **DEFENDED** — the test runs the attacker through exactly `s5RecidivismThreshold` GIs of missed votes (3 missed GIs). Escalation fires on the **3rd miss** (the threshold-th slash, not threshold+1). After the 3rd slash, `isValidatorActive` is `false` and a 4th registration attempt reverts. |
| **Trust assumption** | S5 counter is per-slasher-contract (per model). A validator who spreads misses across different models' task contracts (≤ `s5RecidivismThreshold − 1` per model per window) never reaches the escalation threshold for any single model. This is a gap in the multi-model case (see gaps-before-audit). |

---

### Row 4 — Auditor bloc approves poisoned client model (S3 shadow-mode)

| Field | Value |
|---|---|
| **Attacker** | Auditor bloc (≥ audit-batch majority) colluding with one client |
| **Capability** | Controlling majority of votes in a batch; client submits a backdoored local model CID |
| **Protocol response today** | `finalizeEvaluation` approves a model when `eligible == true` AND `median >= passScore` (`DINTaskAuditor.sol:1247`). A colluding majority sets both. `AuditorScoreDeviation` is emitted when scores deviate beyond `s3DeviationThreshold` (`DINTaskAuditor.sol:1270`), but `s3SlashingEnabled = false` (`DINTaskAuditor.sol:148`) — no slash fires. Honest aggregators fold in whatever `approvedModelIndexes` returns. |
| **Expected test outcome** | **KNOWN GAP** ([#38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38)) — the test sets up a colluding auditor bloc, asserts `AuditorScoreDeviation` is emitted with `exceedsThreshold = true`, and asserts no slash occurs. When S3 graduates from shadow mode this test must flip to `test_defended_`. |
| **Trust assumption** | S3 is deliberately shadow-mode during data-collection phase; requires real-world threshold calibration before graduation. |

---

### Row 5 — T1 aggregator majority submits wrong CID

| Field | Value |
|---|---|
| **Attacker** | Majority of T1 aggregators in a batch (no auditor collusion needed) |
| **Capability** | Controls ≥ `T1_AGGREGATORS_PER_BATCH / 2 + 1` keys in one batch; submits a wrong CID |
| **Protocol response today** | The wrong CID wins the majority vote and is finalized. The honest dissenter who submitted the correct CID is slashed for `AGG_T1_BAD_CONSENSUS` (full `minStake` via `slash()`, `DINTaskCoordinator.sol:971`). S4 dispute (`openDispute` → `lockDisputeSeed` → `resolveDispute(upheld=true)` → `settleRecomputation`) is the only remedy. Adjudication is `onlyOwner` (`DINTaskCoordinator.sol:1277`, `DINTaskCoordinator.sol:1351`). When `settleRecomputation(confirmed=true)` is called: the challenger's bond is returned and the original colluding aggregators are slashed `S4_INVALID_AGGREGATION` — but **`finalCID` is not replaced and the honest dissenter's `AGG_T1_BAD_CONSENSUS` slash is not refunded**. The wrong CID remains the global model for that GI. `_assignFreshSubgroup` is bookkeeping only and does not re-run aggregation. |
| **Expected test outcome** | **KNOWN GAP** ([#194](https://github.com/InfiniteZeroFoundation/DevNet/issues/194)) — the attack partially succeeds even under TA-1: the wrong CID persists after an upheld S4 dispute and the honest dissenter's stake is not recovered. `test_knownGap_t1WrongCID` runs the full S4 flow (`openDispute` → `lockDisputeSeed` → `resolveDispute(upheld=true)` → `settleRecomputation(confirmed=true)`) and asserts: the colluders are slashed `S4_INVALID_AGGREGATION` and the challenger's bond is claimable; the batch's `finalCID` is unchanged; the dissenter's `AGG_T1_BAD_CONSENSUS` slash is not refunded. Flips to `test_defended_` once `settleRecomputation(confirmed=true)` repairs both. |
| **Trust assumption** | Even TA-1 (owner is honest adjudicator) does not defend this row: the damage is not repaired by an honest owner either. A dishonest owner is the separate Row 7 gap. |

---

### Row 6 — Cross-role dual-registration + owner block-selection

| Field | Value |
|---|---|
| **Attacker** | One address registered as both auditor and aggregator in the same GI; model owner tries to steer the batch-assignment draw (formerly by choosing which block to submit batch-creation calls in) |
| **Capability** | One address (auditor + aggregator), staking MIN_STAKE. Before issue #156 H-2 (PR #191) the owner chose which block `autoCreateTier1AndTier2` and `createAuditorsBatches` were submitted in, picking a `blockhash(block.number - 1)` that routed the poisoned model into the colluding T1 batch. Both now read a locked, future-block-anchored `aggSeed`/`auditSeed` (see Row 2), so that lever is closed; what remains is the BL-26 re-roll (decline to lock, wait out the ~256-block window) and TA-4 |
| **Protocol response today** | One address can no longer hold both roles in a GI: `registerDINAuditor` (`DINTaskAuditor.sol:668`) reverts with `TA_DualRoleNotAllowed` when the caller is already an aggregator for that GI, read from the coordinator's `isDINAggregator` (#180). The check sits on the auditor side because aggregator registration (`registerDINaggregator`, `DINTaskCoordinator.sol:401`; states 6–7) always comes before auditor registration (8–9). It is per address: a second address with its own stake still gets both roles (Sybil), so the remaining defence is that the attack costs a second stake and is visible on-chain. The concurrent-registration cap (off by default, `maxConcurrentRegistrationsPerStakeUnit == 0`) can raise that cost further when it is non-zero. |
| **Expected test outcome** | **DEFENDED** for the single-address case ([#180](https://github.com/InfiniteZeroFoundation/DevNet/issues/180), `StakingEnforcement.t.sol` `test_registerDINAuditor_aggregatorSameGI_reverts`); the Sybil variant is documented by `test_registerDINAuditor_secondAddressWithOwnStake_registers`. The [#156](https://github.com/InfiniteZeroFoundation/DevNet/issues/156) block-selection half is fixed, residuals in BL-26. The "colluding aggregators skip outlier clipping" step is off-chain (model-dependent, not testable in Forge). PR #218's `test_knownGap_dualRoleRegistration` flips to `test_defended_…` when it rebases on this change. |
| **Trust assumption** | Operators don't split one stake-holder across two funded addresses to take both roles (Sybil); the cost is a second stake. Batch-shuffle residuals as in BL-26. |

---

### Row 7 — Challenger right, owner suppresses or ignores the dispute

| Field | Value |
|---|---|
| **Attacker** | Model owner who is, or is colluding with, the T1 aggregator majority |
| **Capability** | Three suppression paths available: (a) `resolveDispute(upheld=false)` immediately forfeits the bond (50% burn / 50% treasury) and closes the dispute (`DINTaskCoordinator.sol:1312-1317`); (b) `resolveDispute(upheld=true)` followed by `settleRecomputation(confirmed=false)` forfeits the bond; (c) **never calling `resolveDispute` at all** — `expireDispute` requires `d.resolved && d.upheld` (`DINTaskCoordinator.sol:1419`), so an unresolved dispute never times out and the challenger's bond is locked in the contract indefinitely with no recovery path |
| **Protocol response today** | None — `resolveDispute` and `settleRecomputation` are `onlyOwner`. The owner is the sole adjudicator with no on-chain appeal. |
| **Expected test outcome** | **KNOWN GAP** ([#181](https://github.com/InfiniteZeroFoundation/DevNet/issues/181)) — the test covers all three suppression paths: (a) bond forfeited via `resolveDispute(false)`; (b) bond forfeited via `settleRecomputation(false)`; (c) dispute never resolved → bond locked forever. Issue #181 scope should include the indefinite-lock path as a priority. |
| **Trust assumption** | "Owner is honest adjudicator (S4, pre-decentralization)" — the gap is that this cannot be enforced on-chain. |

---

### Row 8 — Owner steering the dispute recomputation subgroup (BL-11)

| Field | Value |
|---|---|
| **Attacker** | Model owner trying to steer which validators are drawn for the fresh subgroup in `settleRecomputation` |
| **Capability** | Owner controls when to call `lockDisputeSeed` and `resolveDispute`; sees exactly which fresh subgroup is drawn before calling `resolveDispute(upheld=true)` |
| **Protocol response today** | PR #171 (`lockDisputeSeed`): after `openDispute`, `seedBlock = block.number + disputeSeedDelay` (default: 7 blocks, `DINTaskCoordinator.sol:151`). Anyone can call `lockDisputeSeed` once past `seedBlock`; it reads `blockhash(d.seedBlock)`. The seed is used by `_assignFreshSubgroup` to draw from the registered pool. Re-locking after an expired seed-window re-anchors to a new future block. **Trust caveat (TA-4):** OP Stack blockhash is sequencer-produced. The contract's own NatSpec (`DINTaskCoordinator.sol:147-150`) explicitly says this design "trusts the sequencer not to grind". Additionally, because `lockDisputeSeed` must be called before `resolveDispute(upheld=true)`, the owner can see exactly which fresh subgroup would be drawn **before deciding to uphold**. Subgroup-draw steering is defended; outcome steering is not (covered by Row 7). |
| **Expected test outcome** | **DEFENDED** (subgroup draw only) — the test advances 8 blocks, calls `lockDisputeSeed`, and asserts the fresh subgroup drawn by `resolveDispute(upheld=true)` (read via `reEvaluationAssignees` / the `ReEvaluationAssigned` event, since `_assignFreshSubgroup` is `internal`) is deterministic for the locked seed. Attempting to re-lock before seed expiry reverts. After seed-window expiry, a re-lock anchors on a new block. |
| **Trust assumption** | TA-4: "OP Stack sequencer does not grind `blockhash(seedBlock)` — sufficient for testnet." ([#178](https://github.com/InfiniteZeroFoundation/DevNet/issues/178) tracks upgrade to VRF for mainnet.) |

---

### Row 9 — Reward manipulation: auditor submits inflated scores

| Field | Value |
|---|---|
| **Attacker** | Auditor submitting inflated scores to bias reward share toward a colluding client |
| **Capability** | One or more colluding auditors in a batch; controls which scores they submit |
| **Protocol response today** | `_medianOf` in `DINTaskAuditor.sol:821` sorts scores. For an **even** reveal count it returns the average of the two middle values (`DINTaskAuditor.sol:838-840`). Quorum is `minScoreQuorum` (default 2 of 3, `:420`). With 2 revealers and 1 colluder: the median is `(honest_score + 100) / 2` — the colluder can move the median halfway to 100. COST-BOUNDED applies only when all 3 auditors reveal (odd count → true median, single outlier can't shift it). S3 deviation event is emitted but no slash fires (shadow mode, Row 4). |
| **Expected test outcome** | **COST-BOUNDED** — two sub-cases: (a) all 3 reveal: the test verifies a single inflating auditor cannot shift the median beyond the honest majority's range; `AuditorScoreDeviation` is emitted. (b) only 2 reveal (even count): the test asserts the colluder moves the median by exactly `(inflated - honest) / 2` and no slash fires. |
| **Trust assumption** | TA-5: `_medianOf` is correctly implemented (covered by `ScoringValidation.t.sol`). |

---

### Row 10 — Duplicate-update gaming

| Field | Value |
|---|---|
| **Attacker** | Client submitting duplicate local model updates to bias the global model |
| **Capability** | Client controls the content of their submission; `clientHasSubmitted[_GI][msg.sender]` gate (`DINTaskAuditor.sol:727`) prevents a single address from submitting twice — but N client addresses submitting the same update content bypass this gate entirely |
| **Protocol response today** | Single-address gate only. No on-chain mechanism detects duplicate content or weights updates by training-set size. BlockFLow fold-in scoring (#39) is not yet implemented. |
| **Expected test outcome** | **Deferred** — depends on BlockFLow fold-in scoring (#39). No test in Part 2. |
| **Trust assumption** | — |

---

### Row 11 — Per-slasher S5 ring evasion

| Field | Value |
|---|---|
| **Attacker** | Validator registered across multiple models, spreading misses so no single model's S5 ring reaches threshold |
| **Capability** | Two or more models' task contracts are separate slashers; `_partialSlashGIs[validator][msg.sender]` is namespaced per slasher (`DinValidatorStake.sol:309`). With default threshold 3, ≤ 2 misses per model per window avoids S5 on every individual model. |
| **Protocol response today** | None — S5 is per-slasher-contract, not aggregate across models. A validator can miss `(s5RecidivismThreshold − 1) × N` total votes across N models before any single model escalates. |
| **Expected test outcome** | **KNOWN GAP** ([#193](https://github.com/InfiniteZeroFoundation/DevNet/issues/193)) — the test sets up two task contracts (two models), has a validator miss threshold−1 votes on each, and asserts S5 never fires and `isValidatorActive` remains true. |
| **Trust assumption** | S5 counter would need to be aggregated across all models (or moved to a global platform-level counter) to close this gap. |

---

## Trust assumptions

| ID | Assumption | DEFENDED rows that rely on it |
|---|---|---|
| TA-1 | **Owner is honest adjudicator (S4, pre-decentralization).** `resolveDispute` and `settleRecomputation` are `onlyOwner`; no on-chain appeal exists. | Row 8 (subgroup draw only) |
| TA-2 | **S5 recidivism counter is correctly implemented and called.** `slashPartial` is the only path; each task contract must use it (not `slash()`) for liveness faults. | Row 3 |
| TA-3 | **MIN_STAKE and batch-size/validator-ratio calibration.** The cost to capture majority seats must be economically prohibitive relative to model rewards. | Rows 1, 2 |
| TA-4 | **OP Stack sequencer does not grind `blockhash(seedBlock)`.** Applies to the dispute seed and the batch-assignment seeds (`aggSeed`/`auditSeed`). Sufficient for testnet; mainnet requires VRF upgrade (#178). | Rows 2, 6, 8 |
| TA-5 | **`_medianOf` is correctly implemented.** Covered by `ScoringValidation.t.sol`. | Row 9 |

---

## Gaps before audit

| Gap | Tracking issue | Scenario | Condition to flip |
|---|---|---|---|
| S3 graduating from shadow mode | [#38](https://github.com/InfiniteZeroFoundation/DevNet/issues/38) | Row 4 (auditor bloc poisoned model) | `s3SlashingEnabled` set to `true` after threshold calibration |
| T1 wrong CID — finalCID not replaced, dissenter not refunded | [#194](https://github.com/InfiniteZeroFoundation/DevNet/issues/194) (#181 covers who adjudicates, not repairing the outcome) | Row 5 (T1 wrong CID) | `settleRecomputation(confirmed=true)` replaces `finalCID` and refunds the honest dissenter |
| Dual-role registration guard | [#180](https://github.com/InfiniteZeroFoundation/DevNet/issues/180) | Row 6 (cross-role + owner block-selection) | **Flipped by task_061026_20 Part B:** per-address guard in `registerDINAuditor` (`TA_DualRoleNotAllowed`). The Sybil variant (second funded address) remains, bounded by stake cost |
| Stronger batch-shuffle seed | [#156](https://github.com/InfiniteZeroFoundation/DevNet/issues/156) | Rows 2, 6 (owner block-selection) | **Flipped by PR #191:** shuffles seeded by the locked, future-block `aggSeed`/`auditSeed` rather than at owner-controlled call time. Residuals (decline-to-lock re-roll, post-lock pool reshaping) tracked in BL-26 |
| Decentralized dispute adjudication | [#181](https://github.com/InfiniteZeroFoundation/DevNet/issues/181) | Row 7 (owner suppresses dispute) and bond-locked-forever variant | `resolveDispute` gated by multi-sig, DAO committee, or fraud-proof; timeout added for unresolved disputes |
| Dispute timeout for unresolved disputes | [#181](https://github.com/InfiniteZeroFoundation/DevNet/issues/181) | Row 7 (owner never resolves → bond locked) | `expireDispute` (or a new function) reachable when `d.resolved == false` after a deadline |
| BlockFLow duplicate-update scoring | [#39](https://github.com/InfiniteZeroFoundation/DevNet/issues/39) | Row 10 (duplicate-update gaming) | BlockFLow fold-in scoring implemented |
| Per-slasher S5 ring evasion | [#193](https://github.com/InfiniteZeroFoundation/DevNet/issues/193) | Row 11 (multi-model S5 evasion) | S5 counter aggregated globally or per-validator across models |
| Mainnet VRF for dispute and batch seeds | [#178](https://github.com/InfiniteZeroFoundation/DevNet/issues/178) | Rows 2, 6, 8 (trust assumption TA-4) | `lockDisputeSeed`, `lockAggSeed` and `lockAuditSeed` upgraded to VRF or multi-party commit-reveal |

---

## Judgment calls (decided)

1. **Row 5 — T1 wrong CID: KNOWN GAP.**
   `settleRecomputation(confirmed=true)` does not replace `finalCID` and does not refund the honest dissenter's `AGG_T1_BAD_CONSENSUS` slash, so the attack partially succeeds regardless of TA-1. COST-BOUNDED was rejected because it would pass a test while the honest dissenter is never made whole. Test: `test_knownGap_t1WrongCID`.

2. **Row 6 — Dual-role registration: DEFENDED (single address).**
   Not accepted as intended. [#180](https://github.com/InfiniteZeroFoundation/DevNet/issues/180) chose the per-address guard (PR #219 Decision 2): `registerDINAuditor` refuses an address already registered as an aggregator for the GI. It is Sybil-bypassable (a second address with its own stake), which the tests document; the concurrent-registration cap bounds that cost further only when it is non-zero.
