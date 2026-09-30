# DINTaskCoordinator — Technical Documentation

> **File:** [`foundry/src/DINTaskCoordinator.sol`](../../../foundry/src/DINTaskCoordinator.sol)
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`
> **Deployment:** once per model by the model owner (plain `Ownable`, **not** upgradeable)

---

## 1. Overview

`DINTaskCoordinator` orchestrates the **Global Iteration (GI)** lifecycle of one federated-learning model. The model owner drives every phase transition; validators act only inside the phase that is open. It owns:

- the one-time **setup sequence** (pair with `DINTaskAuditor`, confirm both are slashers, record the genesis model);
- **aggregator registration** (active-validator, per-model stake floor, concurrent-registration cap, 300-per-GI cap);
- the **batch-assignment seeds** for auditor batches and T1/T2 batches (future-block hash, locked by anyone);
- **Tier-1 / Tier-2 batch formation** and commit-then-reveal, majority-CID **aggregation** with a submission quorum;
- **aggregator slashing** (S2 partial for no submission, full for bad consensus);
- per-aggregator **reward weights**, handed to `DINTaskAuditor.settleRewards` at `endGI`;
- the **aggregation dispute** scaffold (S4): bonded challenges, fresh-subgroup reassignment, owner adjudication.

Auditor registration, client submissions, scoring and rewards live in the paired [`DINTaskAuditor`](DINTaskAuditor.md); the shared state enum, interfaces and errors are in [`DINShared`](DINShared.md).

---

## 2. Inheritance & Dependencies

| Component | Purpose |
|-----------|---------|
| `Ownable` (OpenZeppelin, non-upgradeable) | Model owner = deployer; drives all phase transitions |
| `ReentrancyGuardTransient` | Guards `openDispute` / `claimDisputeBond` |
| `SafeERC20` / `IERC20` | DIN dispute bonds |
| `IBurnableDinToken` (local) | Burns the burn half of a forfeited dispute bond (all of it if no treasury is set) |
| `DINShared.sol` | `GIstates`, `IDinValidatorStake`, `IDINTaskAuditor`, `TC_*` errors |

---

## 3. State

### 3.1 Wiring & lifecycle

| Variable | Description |
|----------|-------------|
| `dinvalidatorStakeContract` | `DinValidatorStake` proxy (constructor) |
| `dinTaskAuditorContract` | Paired auditor (`setDINTaskAuditorContract`) |
| `modelId` (`immutable`) | Registry model ID, used for the per-model stake floor (constructor) |
| `GI` | Current GI counter (starts at 0; the first GI is 1) |
| `GIstate` | Current `GIstates` value |
| `genesisModelIpfsHash` | Genesis model CID (bytes32) |
| `dinToken` | DIN token for dispute bonds (`setDinToken`) |

### 3.2 Aggregators & batches

| Variable | Description |
|----------|-------------|
| `dinAggregators[gi]`, `isDINAggregator[gi][addr]` | Registration list and flag |
| `registrationSlotsReleased[gi]` | Guard for `releaseGIRegistrationSlots` |
| `tier1Batches[gi]`, `tier2Batches[gi]` | Batch arrays (`Tier1Batch` / `Tier2Batch`); T2 always has at most one batch, id 0 |
| `isTier1Aggregator`, `isTier2Aggregator` | Batch assignment flags (not public) |
| `t1CommitHash`, `t1Committed` (and `t2*`) | Commit hash and commit flag per `[gi][batchId][aggregator]` |
| `t1SubmissionCID`, `t1Submitted`, `t1Votes` (and `t2*`) | Revealed CID, revealed flag and per-CID vote count. Written only by the reveal functions; `t*Submitted` stays `false` for an aggregator who committed but never revealed |
| `tier1FinalizedAt`, `tier2FinalizedAt` | Finalization timestamps (dispute window start) |
| `tier2Score[gi]` | Owner-recorded quality score for the T2 model |
| `aggregatorWeight[gi][addr]`, `totalAggregatorWeight[gi]` | Reward weights (one unit per aggregator per finalized batch) |
| `auditSeedBlock[gi]`, `auditSeed[gi]` | Anchor block and locked seed for auditor batch assignment (§6.3) |
| `aggSeedBlock[gi]`, `aggSeed[gi]` | Anchor block and locked seed for T1/T2 batch assignment (§6.3) |

### 3.3 Constants

| Constant | Value | Meaning |
|----------|-------|---------|
| `T1_AGGREGATORS_PER_BATCH` | 3 | Aggregators per T1 batch — and per T2 batch and fresh dispute subgroup |
| `T1_MODELS_PER_BATCH` | 3 | Target models per T1 batch; also the minimum number of approved models to form batches |
| `MIN_T1_MODELS_PER_BATCH` | 2 | Smallest allowed final T1 batch |
| `MAX_REGISTERED_AGGREGATORS` | 300 | Registration cap per GI |

### 3.4 Governable parameters (owner-settable)

| Variable | Default | Setter |
|----------|---------|--------|
| `s2SlashFractionBps` | 3000 (30%) | `setS2SlashFractionBps` (1 – 10 000) |
| `disputeBond` | 100 DIN | `setDisputeParams` (non-zero) |
| `disputeWindow` | 1 day | `setDisputeParams` (non-zero) |
| `resolutionWindow` | 2 days | `setDisputeParams` (non-zero) |
| `disputeSeedDelay` | 7 blocks | `setDisputeParams` (1 – 256). Also the delay for the two batch-assignment seeds |
| `networkFeeFloor` | 0 | `setNetworkFeeFloor` (stored only, not enforced) |

The S1/S2 slash-fraction default is one of the testnet values still to be decided (issue #155). There is no treasury address on this contract: forfeited bonds go to `dinvalidatorStakeContract.slashTreasury()` (§7).

### 3.5 Disputes

`disputes[gi][tierKind][batchId]` (`Dispute`: challenger, bond, openedAt, resolutionDeadline, seedBlock, resolved, upheld, finalized, seed), `reEvaluationAssignees[gi][tierKind][batchId]`, `disputeBondClaimable[addr]`, `treasuryAccrued` (a running counter of forfeited bonds routed out; no tokens are held against it).

---

## 4. Access Control

| Caller | Functions |
|--------|-----------|
| `owner()` (model owner) | Setup, every phase transition, `createAuditorsBatches`, `autoCreateTier1AndTier2`, `finalizeT1/T2Aggregation`, `slashAuditors`, `slashAggregators`, `setTier2Score`, `endGI`, `releaseGIRegistrationSlots`, `resolveDispute`, `settleRecomputation`, all setters |
| Any active validator | `registerDINaggregator`, `openDispute` |
| Assigned active aggregator | `commitT1Aggregation`, `revealT1Aggregation`, `commitT2Aggregation`, `revealT2Aggregation` |
| Anyone | `lockAuditSeed`, `lockAggSeed`, `lockDisputeSeed`, `expireDispute` (after the deadline), `claimDisputeBond` (own balance), views |

---

## 5. Setup Sequence (before GI 1)

```
constructor(dinValidatorStake, modelId)        → AwaitingDINTaskAuditorToBeSet
setDINTaskAuditorContract(auditor)             → AwaitingDINTaskCoordinatorAsSlasher
  [DIN-Representative: DinCoordinator.addSlasherContract(this)]
setDINTaskCoordinatorAsSlasher()               → AwaitingDINTaskAuditorAsSlasher   (checks isSlasherContract)
  [DIN-Representative: DinCoordinator.addSlasherContract(auditor)]
setDINTaskAuditorAsSlasher()                   → AwaitingGenesisModel
setGenesisModelIpfsHash(cid)                   → GenesisModelCreated
setDinToken(dinToken)                          (needed for dispute bonds)
```

---

## 6. GI Lifecycle

The numbers are `GIstates` ordinals (see [DINShared §2.1](DINShared.md)).

| Step | Function (owner unless noted) | From → To state |
|------|-------------------------------|-----------------|
| Start | `startGI(gi)` / `startGI(gi, passScore)` | `GenesisModelCreated` (4) or `GIended` (25) → `GIstarted` (5) |
| Aggregator registration | `startDINaggregatorsRegistration` → *validators:* `registerDINaggregator` → `closeDINaggregatorsRegistration` | → 6 → 7 |
| Auditor registration | `startDINauditorsRegistration` → *validators on the auditor contract* → `closeDINauditorsRegistration` | → 8 → 9 |
| Local model submissions | `startLMsubmissions` → *clients on the auditor contract* → `closeLMsubmissions` (anchors the audit seed) | → 10 → 11 |
| Audit seed | *anyone:* `lockAuditSeed` | stays 11 |
| Audit batches | `createAuditorsBatches` (delegates to the auditor, passing the seed) | → 12 |
| Test data | `DINTaskAuditor.assignAuditTestDataset` per batch; `setTestDataAssignedFlag` | stays 12 |
| Score commit | `startLMsubmissionsEvaluation` → *auditors commit on the auditor contract* | → 13 |
| Score reveal | `startLMsubmissionsEvaluationReveal` → *auditors reveal* | → 14 |
| Finalize evaluation | `closeLMsubmissionsEvaluation` (calls `finalizeEvaluation`; anchors the aggregation seed) | → 15 |
| Aggregation seed | *anyone:* `lockAggSeed` | stays 15 |
| Batches | `autoCreateTier1AndTier2` | → 16 |
| T1 commit | `startT1Aggregation` → *aggregators:* `commitT1Aggregation` | → 17 |
| T1 reveal | `startT1AggregationReveal` → *aggregators:* `revealT1Aggregation` → `finalizeT1Aggregation` | → 18 → 19 |
| T2 commit | `startT2Aggregation` → *aggregators:* `commitT2Aggregation` | → 20 |
| T2 reveal | `startT2AggregationReveal` → *aggregators:* `revealT2Aggregation` → `finalizeT2Aggregation` | → 21 → 22 |
| Slash | `slashAuditors` → `slashAggregators` | → 23 → 24 |
| End | `endGI` (settles rewards) | → 25 |
| Housekeeping | `releaseGIRegistrationSlots(gi)` | no state change |

Every owner transition after `startGI` takes the expected `_GI` and reverts `TC_WrongGI` if it is not the current one. Every state change goes through `_setGIstate`, which emits `GIStateChanged(GI, newState)`.

The three reveal-opening calls (`startLMsubmissionsEvaluationReveal`, `startT1AggregationReveal`, `startT2AggregationReveal`) are manual owner steps. Forgetting one stalls the GI in the commit window (finalize reverts) without corrupting state.

### 6.1 `startGI`
Requires `_GI == GI + 1` and a funded reward pool: `dinTaskAuditorContract.giRewardPool(_GI) > 0`, otherwise `TC_GIRewardPoolNotFunded`. The two-argument overload also calls `updatePassScore`. Then `GI++`.

### 6.2 `registerDINaggregator`
In `DINaggregatorsRegistrationStarted` only. There is no `onlyCurrentGI` modifier: the checks and the registration list use the `_GI` the caller passes. Checks in order: `isValidatorActive` (`TC_AggregatorNotActive`), not already registered, fewer than 300 registered (`TC_RegistrationCapReached`), stake ≥ `getModelStakeMin(modelId)` when non-zero (`TC_StakeBelowModelFloor`), and — when `maxConcurrentRegistrationsPerStakeUnit > 0` — `activeRegistrationCount < (stake / minStake) × cap` (`TC_ConcurrentRegistrationCapReached`). Then records the aggregator, calls `incrementActiveRegistration`, emits `DINValidatorRegistered`.

### 6.3 Batch-Assignment Seed Lock

Both batch-creation steps shuffle with a seed that must be locked first (issue #156 H-2, PR #191). It replaces `blockhash(block.number - 1)` / `block.timestamp` entropy, which the caller could grind. The pattern is the same as the dispute seed (§7): a future block is anchored, and anyone may lock its hash once it is mined.

| | Auditor batches | T1/T2 batches |
|---|---|---|
| Anchor | `closeLMsubmissions` sets `auditSeedBlock[gi] = block.number + disputeSeedDelay` | `closeLMsubmissionsEvaluation` sets `aggSeedBlock[gi]` the same way |
| Lock (anyone, current GI) | `lockAuditSeed(gi)` | `lockAggSeed(gi)` |
| Seed | `keccak256(blockhash(seedBlock), gi, "AUD")` | `keccak256(blockhash(seedBlock), gi, "AGG")` |
| Consumer | `createAuditorsBatches` (`TC_AuditSeedNotLocked` if unset; the auditor contract also rejects a zero seed with `TA_AuditSeedNotLocked`) | `autoCreateTier1AndTier2` (`TC_AggSeedNotLocked` if unset) |
| Events | `AuditSeedLocked`, `AuditSeedReanchored` | `AggSeedLocked`, `AggSeedReanchored` |

A lock call reverts if the seed isn't anchored yet (`TC_*SeedNotAnchored`), is already locked (`TC_*SeedAlreadyLocked`), or the anchor block isn't mined yet (`TC_*SeedBlockNotMined`). If more than 256 blocks have passed and `blockhash(seedBlock)` is zero, the call re-anchors to `block.number + disputeSeedDelay` and emits the `…Reanchored` event; it never stores a zero-derived seed.

**Residual trust and gaps** (from the PR #191 review; tracked as BL-26 in [`Developer/BACK_LOG.md`](../../../Developer/BACK_LOG.md)):
- **Sequencer trust.** `blockhash` is sequencer-produced on OP Stack, so this design trusts the sequencer not to grind. VRF is the mainnet-grade follow-up (issue #178).
- **Re-roll by declining to lock.** Once `seedBlock` is mined, anyone can compute the resulting shuffle off-chain. A model owner who dislikes it can simply not lock, wait out the 256-block window, and get a fresh anchor on the next lock call. The permissionless lock only prevents this if another party locks first.
- **Post-lock pool reshaping.** The active pools are read when `createAuditorsBatches` / `autoCreateTier1AndTier2` run, after the seed is public. A validator can unstake between the lock and the create call, which changes the pool size and so reshuffles everyone. An attacker with several registered addresses can compute each outcome off-chain and unstake whichever address gives the batch they want.

### 6.4 `autoCreateTier1AndTier2`
Requires `LMSevaluationClosed` and a locked `aggSeed[gi]`.
1. Filters the registered aggregators to those still `Active` at call time (`_activeAggregatorPool`); needs ≥ 3 (`TC_NotEnoughValidators`).
2. Shuffles the aggregators with `keccak256(seed, "AGG_ADDR")` and the approved model indexes with `keccak256(seed, "AGG_IDX")` (Fisher-Yates, in memory). Needs ≥ `T1_MODELS_PER_BATCH` approved models (`TC_NotEnoughApprovedModels`).
3. Greedily fills T1 batches with 3 aggregators and 3 models each (the last batch may take 2 models).
4. If ≥ 3 aggregators remain, forms the single T2 batch (id 0) from the next 3.

Leftover aggregators and models are simply not used this GI. If fewer than 3 aggregators remain for T2, no T2 batch exists and `finalizeT2Aggregation` has nothing to finalize.

### 6.5 Aggregation (T1 / T2): commit, reveal, finalize

Submissions are commit-then-reveal (issue #156 M-1, PR #197). With a single-shot submit, a late aggregator could read an earlier aggregator's CID from public state and copy it. Now no CID is visible while commits are open.

- **Commit** (`T1AggregationStarted` / `T2AggregationStarted`): `commitT1Aggregation(gi, batchId, commitHash)` / `commitT2Aggregation(…)`. The caller must be an assigned (`TC_NotBatchAggregator`), active (`TC_AggregatorNotActive`) aggregator of an existing batch (`TC_InvalidBatch`; for T2 any `batchId != 0` reverts `TC_OnlyOneTier2Batch`). A zero hash (`TC_T*EmptyCommitHash`) and a second commit (`TC_T*AlreadyCommitted`) are rejected. Emits `T1AggregationCommitted` / `T2AggregationCommitted`.
- **Commit hash:** `keccak256(abi.encode(cid, salt, msg.sender, gi, TierKind, batchId))`. Because the sender, GI, tier and batch are bound in, an aggregator who copies a peer's commit hash cannot later reveal the peer's `(cid, salt)` under their own address.
- **Open reveals** (owner): `startT1AggregationReveal` / `startT2AggregationReveal`. No further commits are accepted.
- **Reveal** (`T1AggregationRevealStarted` / `T2AggregationRevealStarted`): `revealT1Aggregation(gi, batchId, cid, salt)` / `revealT2Aggregation(…)`. Same batch, assignment and active checks; requires a prior commit (`TC_T*NoCommitFound`), no prior reveal (`TC_AlreadySubmitted`), a non-zero CID (`TC_ZeroCID`) and a matching hash (`TC_T*RevealHashMismatch`). Records the CID, increments `t*Votes[cid]`, emits `T1AggregationSubmitted` / `T2AggregationSubmitted`.
- **Finalize** (owner, from the reveal state): per batch, the CID with the most votes wins (on a tie, the first tied CID in batch order). Reverts `TC_NoSubmissions` if nobody revealed, and `TC_InsufficientSubmissions` if fewer than `3 / 2 + 1 = 2` revealed. Records `finalCID` and the finalization time, emits `T1BatchFinalized` / `T2Finalized`, and adds one `aggregatorWeight` unit for **every assigned aggregator** of the batch, whether or not they revealed or matched consensus. A failing batch reverts the whole call, so no weight persists for unfinalized batches.

An aggregator who commits but never reveals is treated exactly like one who never committed: excluded from the vote and slashed as a non-submitter (§6.6).

### 6.6 `slashAggregators`
For every T1 and T2 batch member:
- **No reveal (S2):** `slashPartial(agg, minStake × s2SlashFractionBps / 10 000, "AGG_T1_NO_SUBMISSION" | "AGG_T2_NO_SUBMISSION", GI)` — liveness fault with S5 recidivism escalation. Covers both never committing and committing without revealing.
- **Revealed a non-consensus CID:** `slash(agg, minStake, "AGG_T1_BAD_CONSENSUS" | "AGG_T2_BAD_CONSENSUS")` — full severity.

`minStake` is read from `DinValidatorStake` at call time. Emits `AggregatorSlashed(gi, batchId, aggregator, reason, requested, actual)`; `actual` can be lower than `requested` if the aggregator's remaining stake is smaller. The S6 counter is deliberately not fired here (it would stack with S2/S5).

### 6.7 `slashAuditors`, `setTier2Score`, `endGI`, `releaseGIRegistrationSlots`
- `slashAuditors(gi)` requires `T2AggregationDone` and only delegates to `DINTaskAuditor.slashAuditors` (see [DINTaskAuditor §8](DINTaskAuditor.md#8-auditor-slashing--slashauditorsgi)), then moves to `AuditorsSlashed`.
- `setTier2Score(gi, score)` is allowed in `T2AggregationDone` or `GenesisModelCreated`; stored only, it does not affect slashing or rewards.
- `endGI` requires `AggregatorsSlashed`, calls `dinTaskAuditorContract.settleRewards(GI, totalAggregatorWeight[GI])` and moves to `GIended`. It runs no participant loops (BL-10).
- `releaseGIRegistrationSlots(gi)` (owner, once per ended GI) decrements the active-registration counters of that GI's aggregators and, via `decrementAuditorRegistrations`, its auditors. Until it is called, those validators keep occupying concurrent-registration slots.

---

## 7. Aggregation Disputes (S4 scaffold)

Bond custody, windows and fresh-subgroup assignment are on-chain; **adjudication is not** (the owner decides — verifying an aggregation CID would mean re-running aggregation).

| Step | Who | Effect |
|------|-----|--------|
| `openDispute(gi, tierKind, batchId)` | Any active validator | Within `disputeWindow` of the batch's finalization; pulls `disputeBond` DIN; anchors the dispute seed at `block.number + disputeSeedDelay` |
| `lockDisputeSeed(gi, tierKind, batchId)` | Anyone, once the anchor block is mined and before resolution | Stores `seed = keccak256(blockhash(seedBlock), gi, tierKind, batchId)`; re-anchors if the block hash is no longer available (emits `DisputeSeedReanchored`) |
| `resolveDispute(…, upheld=false)` | Owner | Dispute closed; bond forfeited |
| `resolveDispute(…, upheld=true)` | Owner | Requires a locked seed (`TC_DisputeSeedNotLocked`). Shuffles the GI's registered aggregators with the seed and takes the first 3 that are active and were not in the disputed batch (`TC_NotEnoughValidators` if fewer than 3). Starts `resolutionWindow` |
| `settleRecomputation(…, confirmed=true)` | Owner | Bond credited back to the challenger; every original aggregator whose revealed CID matched the disputed `finalCID` is slashed `minStake` (`S4_INVALID_AGGREGATION`) |
| `settleRecomputation(…, confirmed=false)` | Owner | Bond forfeited |
| `expireDispute(…)` | Anyone, after `resolutionDeadline` | Bond credited back; every fresh-subgroup member slashed `minStake` (`S4_FRESH_SUBGROUP_TIMEOUT`) |
| `claimDisputeBond()` | Challenger | Pull payment of credited bonds |

A forfeited bond is split 50% burned / 50% forwarded to `dinvalidatorStakeContract.slashTreasury()`; both halves are burned if no treasury is set. `treasuryAccrued` counts the full forfeited amount.

The fresh subgroup is bookkeeping only: nothing re-opens the state machine for it to submit a recomputation on-chain (§10 No. 3).

---

## 8. Events

| Group | Events |
|-------|--------|
| Lifecycle | `GIStateChanged(GI, newState)` on every state change (`GI` is 0 during setup) |
| Registration & batches | `DINValidatorRegistered`, `Tier1BatchAuto`, `Tier2BatchAuto` |
| Seeds | `AuditSeedLocked`, `AuditSeedReanchored`, `AggSeedLocked`, `AggSeedReanchored`, `DisputeSeedLocked`, `DisputeSeedReanchored` |
| Aggregation | `T1AggregationCommitted`, `T1AggregationSubmitted` (on reveal), `T1BatchFinalized`, `T2AggregationCommitted`, `T2AggregationSubmitted` (on reveal), `T2Finalized` |
| Slashing | `AggregatorSlashed`, `S2SlashFractionBpsUpdated` |
| Disputes | `DisputeOpened`, `DisputeResolved`, `ReEvaluationAssigned`, `RecomputationSettled`, `DisputeExpired`, `DisputeBondClaimed` |

---

## 9. Interactions

```
DINTaskCoordinator
  ├── DinValidatorStake: isSlasherContract, isValidatorActive, getStake, minStake,
  │                      getModelStakeMin, maxConcurrentRegistrationsPerStakeUnit,
  │                      activeRegistrationCount, increment/decrementActiveRegistration,
  │                      slashPartial (S2), slash (bad consensus, S4), slashTreasury
  ├── DINTaskAuditor:    giRewardPool, updatePassScore, createAuditorsBatches (with the audit seed),
  │                      setTestDataAssignedFlag, finalizeEvaluation, approvedModelIndexes,
  │                      slashAuditors, settleRewards, decrementAuditorRegistrations
  └── DinToken:          safeTransferFrom / safeTransfer / burn (dispute bonds)

DINTaskAuditor → DINTaskCoordinator: GI, GIstate, aggregatorWeight (at claim time)
```

`DINModelRegistry` is never read: disabling a model has no effect here.

---

## 10. Review Notes & Open Caveats

Earlier findings from the [foundry/src security review](../audits/foundry-src-security-review.md) should be read alongside these. Several are now fixed: unbounded registration (capped at 300), zero-CID collision (`TC_ZeroCID`), missing quorum (`TC_InsufficientSubmissions`), grindable shuffle (H-2, §6.3) and copy-the-leader aggregation (M-1, §6.5).

- **No. 1 — Runtime bytecode is over the EIP-170 limit.** With commit-reveal aggregation merged, this contract compiles to 24,585 bytes, 9 over the 24,576-byte limit, so it cannot be deployed to Optimism Sepolia or any other real chain from `develop`. `foundry/anvil.sh` starts anvil with `--code-size-limit 4294967295`, and neither `forge test` nor CI checks contract size, so the local devnet and a green test run do not show the problem. Tracked in issue #201 (Part A), which also sets a size budget for every contract.
- **No. 2 — Selective non-reveal is cheaper than being wrong.** Reveals land one at a time. A committed aggregator who sees that peers' CIDs differ from their own can withhold the reveal and take the S2 liveness slash (30% of `minStake` by default) instead of the full-`minStake` bad-consensus slash. The same trade-off exists for auditors. Whether committed-but-unrevealed gets its own reason code and fraction is open in issue #201 (Part B).
- **No. 3 — `expireDispute` can slash an idle fresh subgroup that had no on-chain way to act.** The fresh subgroup cannot submit a recomputation to this contract, so the only thing preventing the timeout slash is the owner calling `settleRecomputation` in time. If the owner does nothing, anyone can slash three uninvolved validators a full `minStake` each.
- **No. 4 — `modelId` is fixed at construction, but assigned at registry approval.** The registry assigns the ID only when it approves the request, which requires this contract to already exist. The deployer must predict the ID. A wrong guess silently applies another model's stake floor (or none).
- **No. 5 — Plurality with three aggregators.** Two colluding aggregators in a batch win the vote; nothing verifies the aggregated model itself. The dispute path (§7) is the only recourse, and the owner adjudicates it.
- **No. 6 — No recovery from a stalled GI.** If a batch never reaches the reveal quorum, `finalizeT1Aggregation` / `finalizeT2Aggregation` keep reverting and there is no owner path to skip the batch or abort the GI.
- **No. 7 — Stale NatSpec:** `slashAggregators` says the slash is always `minStake()` (no-reveal is now the S2 fraction). Comments around the dispute scaffold still say `DinTreasury` "doesn't exist on develop yet" (forfeitures are already forwarded). Several parameters are described as "DAO-settable"; they are `onlyOwner`, i.e. set by the model owner.
- **No. 8 — Leftovers:** `networkFeeFloor` is stored but not enforced. `setTestDataAssignedFlag` gates nothing: evaluation can start without test data being assigned. `releaseGIRegistrationSlots` uses string `require` messages, unlike the rest of the contract.
- **No. 9 — Not upgradeable:** a bug in a model's task contracts requires redeploying them and re-registering the model.
- **No. 10 — dincli lags this contract:** `dincli model-owner deploy task-coordinator` still calls the older one-argument constructor (no `modelId`). `dincli aggregator aggregate-t2` names its working directory, worker job and container after the last T1 batch id, not the T2 batch id (issue #202, Part 2); the on-chain commit is unaffected.
- **No. 11 — `registerDINaggregator` doesn't check the GI.** Unlike `DINTaskAuditor.registerDINAuditor`, it has no `onlyCurrentGI`: while any GI's registration window is open, a validator can register for a future GI (§6.2). Up to 300 addresses can fill GI N+1's list during GI N's window, which locks out honest registrants and hands the attacker every T1/T2 batch. Registering for an already-released past GI leaks the caller's own concurrent-registration slot. dincli always passes the current GI. Tracked in issue #206; the fix (add `onlyCurrentGI`) has to fit within the EIP-170 budget from No. 1.

---

## 11. Change Log

### P3 (foundry)

- Reward pool gate on `startGI`; per-aggregator reward weights handed to `settleRewards` at `endGI` (BL-10).
- Commit-then-reveal evaluation phase (`startLMsubmissionsEvaluationReveal`, `LMSevaluationRevealStarted`).
- Registration caps and floors (`MAX_REGISTERED_AGGREGATORS`, per-model stake floor, concurrent-registration cap) with `releaseGIRegistrationSlots`.
- Submission quorum and zero-CID rejection on T1/T2 finalization.
- S2 partial slashing via `slashPartial`; full-severity slashing kept for bad consensus.
- S4 aggregation dispute scaffold (bonds, fresh subgroups, recomputation settlement, expiry), with a locked future-block seed for the fresh subgroup.
- Forfeited dispute bonds forwarded to the platform treasury (`slashTreasury()`), replacing the per-contract treasury address (issue #152).
- `GIStateChanged` emitted on every state change; `T1BatchFinalized` / `T2Finalized` on finalization.
- `modelId` constructor argument.
- Locked batch-assignment seeds for auditor and T1/T2 batches (`lockAuditSeed`, `lockAggSeed`; issue #156 H-2, PR #191).
- Commit-then-reveal T1/T2 aggregation with a sender-bound commit hash (`commitT*Aggregation`, `revealT*Aggregation`, `startT*AggregationReveal`; issue #156 M-1, PR #197). Adds states `T1AggregationRevealStarted` (18) and `T2AggregationRevealStarted` (21), shifting later ordinals.
