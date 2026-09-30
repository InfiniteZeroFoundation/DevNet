# DINShared — Technical Documentation

> **File:** [`foundry/src/DINShared.sol`](../../../foundry/src/DINShared.sol)
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DINShared.sol` is a **shared type library** for the DIN Protocol. It is not a deployable contract — it contains no constructor, no state variables, and no functions. It is imported by both `DINTaskCoordinator` and `DINTaskAuditor` (and any future protocol contracts) to ensure they share:

1. The `GIstates` enum — the canonical lifecycle state machine for a Global Iteration.
2. Cross-contract interfaces (`IDinValidatorStake`, `IDINTaskCoordinator`, `IDINTaskAuditor`).
3. All custom error declarations for both `DINTaskAuditor` (`TA_*`) and `DINTaskCoordinator` (`TC_*`).

Centralising these definitions prevents ABI drift between contracts and makes the state machine a single source of truth.

---

## 2. Global Iteration State Machine

### 2.1 `GIstates` Enum

The `GIstates` enum defines every discrete state a Global Iteration (GI) can occupy, in sequential order. The `DINTaskCoordinator` transitions through these states in a strictly enforced linear progression.

```
Value  State Name                          Description
─────  ──────────────────────────────────  ────────────────────────────────────────────────────────
  0    AwaitingDINTaskAuditorToBeSet       Initial state after DINTaskCoordinator deployment.
  1    AwaitingDINTaskCoordinatorAsSlasher TaskAuditor has been set; coordinator not yet slasher.
  2    AwaitingDINTaskAuditorAsSlasher     Coordinator is slasher; auditor not yet slasher.
  3    AwaitingGenesisModel                Both contracts are slashers; genesis model not yet set.
  4    GenesisModelCreated                 Genesis model IPFS hash has been recorded.
  5    GIstarted                           A new GI has been incremented and started.
  6    DINaggregatorsRegistrationStarted   Aggregator registration window is open.
  7    DINaggregatorsRegistrationClosed    Aggregator registration window is closed.
  8    DINauditorsRegistrationStarted      Auditor registration window is open.
  9    DINauditorsRegistrationClosed       Auditor registration window is closed.
 10    LMSstarted                          Local Model Submission window is open.
 11    LMSclosed                           Local Model Submission window is closed.
 12    AuditorsBatchesCreated              Audit batches have been formed.
 13    LMSevaluationStarted                Commit phase: auditors submit hidden score/vote commitments via `commitAuditScore`.
 14    LMSevaluationRevealStarted          Reveal phase: auditors reveal (score, vote, salt) via `revealAuditScore`; eligibility and median scoring are computed from revealed values only.
 15    LMSevaluationClosed                 Evaluation finalized; approved models identified.
 16    T1nT2Bcreated                       Tier-1 and Tier-2 aggregation batches formed.
 17    T1AggregationStarted                Commit phase: Tier-1 aggregators submit hidden CID commitments via `commitT1Aggregation`.
 18    T1AggregationRevealStarted          Reveal phase: Tier-1 aggregators reveal (cid, salt) via `revealT1Aggregation`; only revealed CIDs count toward finalization.
 19    T1AggregationDone                   Tier-1 finalized; winning CIDs per batch recorded.
 20    T2AggregationStarted                Commit phase: Tier-2 aggregators submit hidden CID commitments via `commitT2Aggregation`.
 21    T2AggregationRevealStarted          Reveal phase: Tier-2 aggregators reveal (cid, salt) via `revealT2Aggregation`; only revealed CIDs count toward finalization.
 22    T2AggregationDone                   Tier-2 finalized; global winning CID recorded.
 23    AuditorsSlashed                     Auditor slashing phase executed.
 24    AggregatorsSlashed                  Aggregator slashing phase executed.
 25    GIended                             GI is complete; system is ready for next GI.
```

> **Ordinal note:** `LMSevaluationRevealStarted` (commit-then-reveal auditor scoring, task_210726_6 §2a) sits between `LMSevaluationStarted` and `LMSevaluationClosed` at ordinal 14. `T1AggregationRevealStarted` and `T2AggregationRevealStarted` (commit-then-reveal T1/T2 aggregation, issue #156 M-1, task_240926_18 Part C) sit at ordinals 18 and 21 respectively, immediately after their corresponding commit-phase state — same insert-in-lifecycle-position precedent, not appended. Each insertion shifts every later ordinal by +1 relative to the prior numbering. `dincli/cli/utils.py`'s `states`/`stateDescription` positional mirrors (indexed by this same raw ordinal) have been updated to match — see `dincli/cli/utils.py`'s `states`/`stateDescription` lists.

### 2.2 State Transition Diagram

```
[0] AwaitingDINTaskAuditorToBeSet
        │ setDINTaskAuditorContract()
        ▼
[1] AwaitingDINTaskCoordinatorAsSlasher
        │ setDINTaskCoordinatorAsSlasher()
        ▼
[2] AwaitingDINTaskAuditorAsSlasher
        │ setDINTaskAuditorAsSlasher()
        ▼
[3] AwaitingGenesisModel
        │ setGenesisModelIpfsHash()
        ▼
[4] GenesisModelCreated ◄──────────────────────────────── [25] GIended
        │ startGI()                                               ▲
        ▼                                                         │ endGI()
[5] GIstarted                                             [24] AggregatorsSlashed
        │ startDINaggregatorsRegistration()                       ▲
        ▼                                                         │ slashAggregators()
[6] DINaggregatorsRegistrationStarted               [23] AuditorsSlashed
        │ closeDINaggregatorsRegistration()                       ▲
        ▼                                                         │ slashAuditors()
[7] DINaggregatorsRegistrationClosed                [22] T2AggregationDone
        │ startDINauditorsRegistration()                          ▲
        ▼                                                         │ finalizeT2Aggregation()
[8] DINauditorsRegistrationStarted                  [21] T2AggregationRevealStarted
        │ closeDINauditorsRegistration()                          ▲
        ▼                                                         │ startT2AggregationReveal()
[9] DINauditorsRegistrationClosed                   [20] T2AggregationStarted
        │ startLMsubmissions()                                    ▲
        ▼                                                         │ startT2Aggregation()
[10] LMSstarted                                     [19] T1AggregationDone
        │ closeLMsubmissions()                                    ▲
        ▼                                                         │ finalizeT1Aggregation()
[11] LMSclosed                                      [18] T1AggregationRevealStarted
        │ createAuditorsBatches()                                 ▲
        ▼                                                         │ startT1AggregationReveal()
[12] AuditorsBatchesCreated                         [17] T1AggregationStarted
        │ startLMsubmissionsEvaluation()                          ▲
        ▼                                                         │ startT1Aggregation()
[13] LMSevaluationStarted                           [16] T1nT2Bcreated
        │ (auditors: commitAuditScore, commit phase)               ▲
        └──────────── startLMsubmissionsEvaluationReveal() ────────┤ autoCreateTier1AndTier2()
                       (auditors: revealAuditScore, reveal phase)  │
                                                         [15] LMSevaluationClosed
                                                                    ▲
                                                                    │ closeLMsubmissionsEvaluation()
                                                         [14] LMSevaluationRevealStarted
```

T1/T2 aggregation submissions follow the same commit-then-reveal shape as LMS evaluation above: `commitT1Aggregation`/`commitT2Aggregation` during the `*AggregationStarted` (commit) state, then the model owner calls `startT1AggregationReveal`/`startT2AggregationReveal` to open `*AggregationRevealStarted`, during which aggregators call `revealT1Aggregation`/`revealT2Aggregation`. Only revealed CIDs are counted by `finalizeT1Aggregation`/`finalizeT2Aggregation`; a committed-but-never-revealed aggregator is excluded from finalization and remains slashable via `slashAggregators`' existing "no submission" (S2) check (issue #156 M-1, task_240926_18 Part C).

---

## 3. Cross-Contract Interfaces

### 3.1 `IDinValidatorStake`

```solidity
interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);
    function minStake() external view returns (uint256);
    function isValidatorActive(address validator) external view returns (bool);
    function slash(address validator, uint256 amount, bytes32 reason) external returns (uint256);
    function isSlasherContract(address slasherContract) external view returns (bool);
    function getEncryptionKey(address validator) external view returns (bytes memory);
    function getModelStakeMin(uint256 modelId) external view returns (uint256);
    function activeRegistrationCount(address validator) external view returns (uint256);
    function incrementActiveRegistration(address validator) external;
    function decrementActiveRegistration(address validator) external;
    function maxConcurrentRegistrationsPerStakeUnit() external view returns (uint256);
    function slashPartial(address validator, uint256 amount, bytes32 reason, uint256 giIndex) external returns (uint256);
    function recordNoParticipation(address validator, bytes32 reason) external returns (uint256);
    function slashTreasury() external view returns (address);
}
```

Used by: `DINTaskCoordinator`, `DINTaskAuditor`

| Method | Purpose |
|--------|---------|
| `getStake` / `minStake` | Per-model floor and concurrency-cap checks at registration; `minStake` also sizes every slash |
| `isValidatorActive` | Gate on registration, auditor and aggregator commit/reveal, `openDispute`, and batch formation (inactive registrants are filtered out) |
| `slash` | Full-severity slash (`AGG_T*_BAD_CONSENSUS`, `AUD_SCORE_DEVIATION`, `S4_*`) |
| `slashPartial` | S1/S2 liveness slash with S5 recidivism tracking (`AUD_NO_VOTE`, `AGG_T*_NO_SUBMISSION`) |
| `recordNoParticipation` | S6 counter — declared, but no task contract calls it |
| `isSlasherContract` | Setup-state checks (`setDINTaskCoordinatorAsSlasher` / `setDINTaskAuditorAsSlasher`) |
| `getEncryptionKey` | `DINTaskAuditor` requires each batch auditor to have an X25519 key before assigning encrypted test-data keys |
| `getModelStakeMin` | Per-model stake floor (`TC_/TA_StakeBelowModelFloor`) |
| `activeRegistrationCount` / `maxConcurrentRegistrationsPerStakeUnit` | Concurrent-registration cap (`TC_/TA_ConcurrentRegistrationCapReached`) |
| `incrementActiveRegistration` / `decrementActiveRegistration` | Counter maintenance at registration and in `releaseGIRegistrationSlots` |
| `slashTreasury` | Platform treasury address. Both task contracts forward the treasury reward share and the treasury half of forfeited bonds and penalties to it, and burn that part if it is unset |

### 3.2 `IDINTaskCoordinator`

```solidity
interface IDINTaskCoordinator {
    function GI() external view returns (uint256);
    function GIstate() external view returns (GIstates);
    function aggregatorWeight(uint256 gi, address aggregator) external view returns (uint256);
}
```

Used by: `DINTaskAuditor`

| Method | Purpose |
|--------|---------|
| `GI()` | Current GI counter, for `onlyCurrentGI` and `depositRewards` validation |
| `GIstate()` | Lifecycle gate for every auditor-side phase |
| `aggregatorWeight` | Read at `claimReward` time to compute each aggregator's weighted share |

### 3.3 `IDINTaskAuditor`

```solidity
interface IDINTaskAuditor {
    function createAuditorsBatches(uint _GI, bytes32 seed) external returns (bool);
    function setTestDataAssignedFlag(uint _GI, bool flag) external;
    function finalizeEvaluation(uint _GI) external returns (bool);
    function slashAuditors(uint _GI) external returns (bool);
    function approvedModelIndexes(uint _GI) external view returns (uint[] memory);
    function updatePassScore(uint256 newPassScore) external;
    function giRewardPool(uint256 gi) external view returns (uint256);
    function settleRewards(uint256 gi, uint256 aggregatorTotalWeight) external;
    function decrementAuditorRegistrations(uint256 _GI) external;
}
```

Used by: `DINTaskCoordinator`

| Method | Purpose |
|--------|---------|
| `createAuditorsBatches` | Batch formation, triggered by the coordinator in `LMSclosed`. `seed` is the coordinator's locked `auditSeed[_GI]`; a zero seed reverts `TA_AuditSeedNotLocked` |
| `setTestDataAssignedFlag` | Records that test datasets were distributed (informational — nothing gates on it) |
| `finalizeEvaluation` | Median scores + approval; requires `LMSevaluationRevealStarted` |
| `slashAuditors` | S1/S3 auditor slashing; requires `T2AggregationDone` |
| `approvedModelIndexes` | Approved models for T1/T2 batch formation |
| `updatePassScore` | Pass score update from the two-argument `startGI` |
| `giRewardPool` | `_startGI` refuses to start a GI whose pool is empty (`TC_GIRewardPoolNotFunded`) |
| `settleRewards` | Called from `endGI` with the coordinator's `totalAggregatorWeight` |
| `decrementAuditorRegistrations` | Called from `releaseGIRegistrationSlots` |

---

## 4. Custom Error Catalogue

### 4.1 Commit-Then-Reveal Auditor Scoring (task_210726_6 §2a–2b)

| Error | Description |
|-------|-------------|
| `TA_CommitPhaseNotOpen` | `commitAuditScore` called while `GIstate != LMSevaluationStarted` |
| `TA_AlreadyCommitted` | Auditor has already committed a score for this `(gi, batchId, modelIndex)` |
| `TA_EmptyCommitHash` | `commitHash` argument is `bytes32(0)` |
| `TA_RevealPhaseNotOpen` | `revealAuditScore` called while `GIstate != LMSevaluationRevealStarted` |
| `TA_NoCommitFound` | No prior `commitAuditScore` recorded for this auditor/model — reveal without a commit |
| `TA_RevealHashMismatch` | `keccak256(abi.encodePacked(score, vote, salt))` does not match the stored commit hash |
| `TC_RevealCannotBeStarted` | `startLMsubmissionsEvaluationReveal` called while `GIstate != LMSevaluationStarted` |
| `TA_EncryptedKeyCountMismatch` | `assignAuditTestDataset`'s `encryptedKeys` array length does not match the batch's auditor count |

### 4.2 DINTaskAuditor Errors (`TA_*`)

| Error | Description |
|-------|-------------|
| `TA_NotTaskCoordinator` | Function restricted to the TaskCoordinator was called by another address |
| `TA_AmountMustBePositive` | Deposit or reward amount is zero |
| `TA_InvalidPassScore` | Pass score set outside 0–100 range |
| `TA_AuditorRegistrationNotOpen` | Registration attempted outside registration window |
| `TA_WrongGI` | Global Iteration mismatch |
| `TA_AuditorAlreadyRegistered` | Duplicate auditor registration for same GI |
| `TA_LMSubmissionsNotOpen` | Local model submission attempted outside submission window |
| `TA_AlreadySubmitted` | Client has already submitted a model this GI |
| `TA_MaxLMSubmissionsReached` | Submission count reached `MAX_LM_SUBMISSIONS` (10,000) |
| `TA_NotEnoughAuditors` | Too few auditors to form even one batch |
| `TA_CannotCreateAuditorsBatches` | State is not `LMSclosed` |
| `TA_BatchDoesNotExist` | Batch ID >= batch array length |
| `TA_BatchIDMismatch` | Internal sanity check failure on batch ID |
| `TA_CannotSetTestDataAssignedFlag` | State is not `AuditorsBatchesCreated` |
| `TA_FlagMustBeTrue` | `setTestDataAssignedFlag` called with `flag = false` |
| `TA_FlagAlreadySet` | Flag was already set for this GI |
| `TA_NotAssignedAuditor` | Score commit/reveal from auditor not assigned to the batch |
| `TA_InvalidModelIndex` | Model index not assigned to this batch |
| `TA_CannotSetAuditScore` | Declared but unused — left over from the pre-commit-reveal `setAuditScorenEligibility`. |
| `TA_ScoreOutOfRange` | Score > 100 (checked at reveal time) |
| `TA_AlreadyVoted` | Auditor has already revealed a score for this model |
| `TA_CannotFinalizeEvaluation` | State is not `LMSevaluationRevealStarted` |
| `TA_AuditorNotActive` | Auditor's `DinValidatorStake.isValidatorActive()` is false — checked on both commit and reveal |
| `TA_InvalidDeviationThreshold` | S3 deviation threshold set outside 0–100 range |
| `TA_EmptyScoreSet` | `_medianOf` called with zero scores to compute a median over |
| `TA_RegistrationCapReached` | `dinAuditors[GI].length` reached `MAX_REGISTERED_AUDITORS` (300) |
| `TA_CannotSlashAuditors` | `slashAuditors` called while `GIstate != T2AggregationDone` |
| `TA_InvalidSlashFraction` | `setS1SlashFractionBps` with 0 or a value above 10 000 |
| `TA_StakeBelowModelFloor` | Auditor's stake below the model's `getModelStakeMin` floor |
| `TA_ConcurrentRegistrationCapReached` | Auditor already at `(stake / minStake) × maxConcurrentRegistrationsPerStakeUnit` open registrations |
| `TA_AuditorEncryptionKeyNotRegistered` | A batch auditor has no X25519 key on `DinValidatorStake` when test-data keys are assigned |
| `TA_InsufficientStake` | Declared but unused — registration gates on `isValidatorActive` instead |
| `TA_BatchNotFound` | Declared but unused (`TA_BatchDoesNotExist` is used) |

### 4.3 DINTaskCoordinator Errors (`TC_*`)

| Error | Description |
|-------|-------------|
| `TC_TaskAuditorContractCannotBeSet` | Task auditor set attempted in wrong state |
| `TC_CoordinatorCannotBeSetAsSlasher` | Set-slasher called in wrong state |
| `TC_CoordinatorIsNotSlasher` | Coordinator not in `DinValidatorStake.slasherContracts` |
| `TC_AuditorCannotBeSetAsSlasher` | Auditor slasher set called in wrong state |
| `TC_AuditorIsNotSlasher` | Auditor not in `DinValidatorStake.slasherContracts` |
| `TC_GenesisModelHashCannotBeSet` | Genesis hash set in wrong state |
| `TC_GICannotBeStarted` | `startGI` called in wrong state |
| `TC_WrongGI` | GI index argument does not match current `GI` counter |
| `TC_AggregatorsRegistrationCannotBeStarted` | Registration start called in wrong state |
| `TC_AggregatorsRegistrationNotOpen` | Aggregator registration in wrong state |
| `TC_InsufficientStake` | Declared but unused — registration gates on `isValidatorActive` instead |
| `TC_AggregatorAlreadyRegistered` | Duplicate aggregator registration |
| `TC_AggregatorsRegistrationCannotBeFinished` | Close called in wrong state |
| `TC_AuditorsRegistrationCannotBeStarted` | Auditor registration start in wrong state |
| `TC_AuditorsRegistrationCannotBeFinished` | Auditor registration close in wrong state |
| `TC_LMSubmissionsCannotBeStarted` | LM submission window start in wrong state |
| `TC_LMSubmissionsNotStarted` | LM submission close when not started |
| `TC_LMEvalCannotBeStarted` | Reused by two functions: `createAuditorsBatches` when state is not `LMSclosed`, and `startLMsubmissionsEvaluation` (opens the commit phase) when state is not `AuditorsBatchesCreated` |
| `TC_LMEvalCannotBeFinished` | `closeLMsubmissionsEvaluation` called when state is not `LMSevaluationRevealStarted` |
| `TC_FailedToCreateAuditorsBatches` | `createAuditorsBatches` returned false |
| `TC_CannotSetTestDataAssignedFlag` | Test data flag set in wrong state |
| `TC_EvalPhaseNotClosed` | T1/T2 batch creation before evaluation close |
| `TC_NotEnoughValidators` | Too few aggregators for T1 batches |
| `TC_NotEnoughApprovedModels` | Fewer than `T1_MODELS_PER_BATCH` models approved |
| `TC_BatchNotFound` | `getTier1Batch` with a batch ID out of bounds |
| `TC_OnlyOneTier2Batch` | Tier-2 batch ID != 0 (T2 commit/reveal, `getTier2Batch`) |
| `TC_NotReadyForT1Aggregation` | T1 start in wrong state |
| `TC_T1AggregationNotStarted` | `commitT1Aggregation` called while the state is not `T1AggregationStarted` |
| `TC_InvalidBatch` | Batch ID out of range (T1 commit/reveal, `openDispute`) |
| `TC_NotBatchAggregator` | Commit or reveal from an address not assigned to the batch |
| `TC_AlreadySubmitted` | Aggregator has already revealed for this batch |
| `TC_NoSubmissions` | No CID was revealed for a batch; cannot determine a winner |
| `TC_NotReadyToFinalizeT1` | T1 finalize called in wrong state |
| `TC_NotReadyForT2Aggregation` | T2 start in wrong state |
| `TC_T2AggregationNotStarted` | `commitT2Aggregation` called while the state is not `T2AggregationStarted` |
| `TC_NotReadyToFinalizeT2` | T2 finalize called in wrong state |
| `TC_NotReadyToSlashAuditors` | Auditor slash called before T2 done |
| `TC_NotReadyToSlashAggregators` | Aggregator slash called before auditors slashed |
| `TC_NotReadyToSetTier2Score` | Tier-2 score set in wrong state |
| `TC_NotReadyToEndGI` | `endGI` called before aggregators slashed |
| `TC_FailedToFinalizeEvaluation` | `finalizeEvaluation` returned false |
| `TC_AggregatorNotActive` | Aggregator's `DinValidatorStake.isValidatorActive()` is false |
| `TC_FailedToSlashAuditors` | `DINTaskAuditor.slashAuditors()` returned false |
| `TC_GIRewardPoolNotFunded` | `startGI` for a GI whose `giRewardPool` on the auditor is zero |
| `TC_RegistrationCapReached` | `dinAggregators[GI].length` reached `MAX_REGISTERED_AGGREGATORS` (300) |
| `TC_StakeBelowModelFloor` | Aggregator's stake below the model's `getModelStakeMin` floor |
| `TC_ConcurrentRegistrationCapReached` | Aggregator already at its concurrent-registration cap |
| `TC_ZeroCID` | T1/T2 reveal of `bytes32(0)` (reserved as the "no submission" sentinel) |
| `TC_InsufficientSubmissions` | A T1/T2 batch finalized with fewer than `T1_AGGREGATORS_PER_BATCH / 2 + 1` revealed CIDs |
| `TC_InvalidSlashFraction` | `setS2SlashFractionBps` with 0 or a value above 10 000 |

### 4.4 Rewards (`TA_*`, task_210726_6 §3)

| Error | Description |
|-------|-------------|
| `TA_InvalidAddress` | Zero address passed to the constructor or `setDinToken` |
| `TA_InvalidRewardSplit` | `setRewardSplit` fields do not sum to 10 000 bps |
| `TA_NoRewardsToClaim` | `claimRewards` with a zero `claimable` balance |
| `TA_InvalidRewardGI` | `depositRewards` for GI 0 or a GI that has already passed |
| `TA_RewardsNotSettled` | `claimReward(gi)` before `endGI` settled that GI |
| `TA_RewardAlreadyClaimed` | Second `claimReward(gi)` by the same address |
| `TA_NoRewardEarned` | Caller has no client, auditor or aggregator share in that GI |

### 4.5 Test-data disputes (`TA_*`, task_240826_10 §B)

| Error | Description |
|-------|-------------|
| `TA_NoCommitmentStored` | `openTestDataDispute` on a batch with no test-data commitment |
| `TA_DisputeAlreadyActive` | A dispute is already open for the batch |
| `TA_NoActiveDispute` | Resolve/close on a batch with no open dispute; also `reassignAuditTestDataset` when no reassignment is pending |
| `TA_DisputeWindowClosed` | `resolveTestDataDispute` after the window, or `closeExpiredDispute` before it ends (the same error is reused for both) |
| `TA_InvalidDisputeBond` | Reused by `setDisputePenaltyBps` for a value above 10 000 |
| `TA_BatchPendingReassignment` | New assignment or dispute on a batch awaiting `reassignAuditTestDataset` |
| `TA_InsufficientDisputeBond` | Declared but unused |

### 4.6 Aggregation disputes (`TC_*`, task_210726_6 §4c)

| Error | Description |
|-------|-------------|
| `TC_InvalidAddress` | Zero address passed to the constructor, `setDINTaskAuditorContract` or `setDinToken` |
| `TC_InvalidDisputeParams` | `setDisputeParams` with a zero bond, window or resolution window, or a seed delay outside 1–256 |
| `TC_BatchNotFinalized` | `openDispute` on a batch that has not finalized |
| `TC_DisputeWindowClosed` | `openDispute` after `finalizedAt + disputeWindow` |
| `TC_DisputeAlreadyOpen` | A dispute already exists for the batch |
| `TC_DisputeNotOpen` | `resolveDispute` or `lockDisputeSeed` with no dispute |
| `TC_DisputeAlreadyResolved` | Second `resolveDispute`, or `lockDisputeSeed` after resolution |
| `TC_NoBondClaimable` | `claimDisputeBond` with nothing to claim |
| `TC_DisputeNotAwaitingRecomputation` | `settleRecomputation` / `expireDispute` on a dispute that was not upheld |
| `TC_ResolutionWindowOpen` | `expireDispute` before `resolutionDeadline` |
| `TC_DisputeAlreadyFinalized` | Second `settleRecomputation` / `expireDispute` |
| `TC_DisputeSeedBlockNotMined` | `lockDisputeSeed` before the anchor block is mined |
| `TC_DisputeSeedAlreadyLocked` | `lockDisputeSeed` when the seed is already set |
| `TC_DisputeSeedNotLocked` | `resolveDispute(…, upheld=true)` before the dispute seed is locked |

### 4.7 Batch-assignment seed lock (issue #156 H-2)

One set per seed, mirroring the dispute-seed errors in §4.6. See [DINTaskCoordinator §6.3](DINTaskCoordinator.md#63-batch-assignment-seed-lock) for the mechanism.

| Error | Description |
|-------|-------------|
| `TC_AggSeedNotAnchored` | `lockAggSeed` called before `aggSeedBlock[_GI]` has been set (i.e. before `closeLMsubmissionsEvaluation`) |
| `TC_AggSeedBlockNotMined` | `lockAggSeed` called before `block.number > aggSeedBlock[_GI]` |
| `TC_AggSeedAlreadyLocked` | `lockAggSeed` called when `aggSeed[_GI]` is already non-zero |
| `TC_AggSeedNotLocked` | `autoCreateTier1AndTier2` called while `aggSeed[_GI] == bytes32(0)` |
| `TC_AuditSeedNotAnchored` | `lockAuditSeed` called before `auditSeedBlock[_GI]` has been set (i.e. before `closeLMsubmissions`) |
| `TC_AuditSeedBlockNotMined` | `lockAuditSeed` called before `block.number > auditSeedBlock[_GI]` |
| `TC_AuditSeedAlreadyLocked` | `lockAuditSeed` called when `auditSeed[_GI]` is already non-zero |
| `TC_AuditSeedNotLocked` | `createAuditorsBatches` called while `auditSeed[_GI] == bytes32(0)` |
| `TA_AuditSeedNotLocked` | `DINTaskAuditor.createAuditorsBatches(uint, bytes32)` rejects a zero seed itself, as a second guard behind the coordinator's `TC_AuditSeedNotLocked` check |

### 4.8 Commit-then-reveal T1/T2 aggregation (`TC_*`, issue #156 M-1)

The T2 errors are the exact counterparts of the T1 errors. See [DINTaskCoordinator §6.5](DINTaskCoordinator.md#65-aggregation-t1--t2-commit-reveal-finalize).

| Error | Description |
|-------|-------------|
| `TC_T1RevealCannotBeStarted` / `TC_T2RevealCannotBeStarted` | `startT1AggregationReveal` / `startT2AggregationReveal` called while the state is not `T1AggregationStarted` / `T2AggregationStarted` |
| `TC_T1RevealPhaseNotOpen` / `TC_T2RevealPhaseNotOpen` | `revealT1Aggregation` / `revealT2Aggregation` called outside the reveal state |
| `TC_T1AlreadyCommitted` / `TC_T2AlreadyCommitted` | Second commit by the same aggregator for the batch |
| `TC_T1EmptyCommitHash` / `TC_T2EmptyCommitHash` | `commitHash` is `bytes32(0)` |
| `TC_T1NoCommitFound` / `TC_T2NoCommitFound` | Reveal without a prior commit |
| `TC_T1RevealHashMismatch` / `TC_T2RevealHashMismatch` | `keccak256(abi.encode(cid, salt, msg.sender, GI, TierKind, batchId))` does not match the stored commit hash |

---

## 5. Design Rationale

### Why a Shared File?

Both `DINTaskCoordinator` and `DINTaskAuditor` need to read each other's state (via interfaces) and react to shared lifecycle states (via `GIstates`). Without `DINShared.sol`:
- The enum would be duplicated across contracts, risking value drift.
- Interface definitions could go stale when one contract is updated without updating the other.

### Error Namespacing

The `TA_` and `TC_` prefixes make it immediately clear in stack traces and event logs which contract emitted an error, even when both contracts are interacting in the same transaction. `TC_RevealCannotBeStarted` is the one exception worth calling out: it's grouped with the commit-then-reveal errors in the source (§4.1 above) because it gates the coordinator-side phase transition those errors depend on, but it keeps the `TC_` prefix since it's the coordinator, not the auditor, that reverts with it.

### Commit-Then-Reveal Auditor Scoring

`LMSevaluationStarted` and `LMSevaluationRevealStarted` split what was previously a single evaluation phase into two: auditors first commit `keccak256(score, vote, salt)` (hiding their vote from other auditors until everyone has committed), then, once the model owner closes the commit window via `DINTaskCoordinator.startLMsubmissionsEvaluationReveal`, reveal the underlying `(score, vote, salt)` for it to be counted. An auditor who commits but never reveals is simply excluded from quorum/median counting, and remains slashable via the existing "missed vote" check in `slashAuditors` — no separate non-reveal handling needed.
