# DINShared — Technical Documentation

> **File:** `hardhat/contracts/DINShared.sol`
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
 13    LMSevaluationStarted                Auditors can now submit scores and eligibility votes.
 14    LMSevaluationClosed                 Evaluation finalized; approved models identified.
 15    T1nT2Bcreated                       Tier-1 and Tier-2 aggregation batches formed.
 16    T1AggregationStarted                Tier-1 aggregators can submit their aggregated CIDs.
 17    T1AggregationDone                   Tier-1 finalized; winning CIDs per batch recorded.
 18    T2AggregationStarted                Tier-2 aggregators can submit their aggregated CIDs.
 19    T2AggregationDone                   Tier-2 finalized; global winning CID recorded.
 20    AuditorsSlashed                     Auditor slashing phase executed.
 21    AggregatorsSlashed                  Aggregator slashing phase executed.
 22    GIended                             GI is complete; system is ready for next GI.
```

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
[4] GenesisModelCreated ◄──────────────────────────────── [22] GIended
        │ startGI()                                               ▲
        ▼                                                         │ endGI()
[5] GIstarted                                             [21] AggregatorsSlashed
        │ startDINaggregatorsRegistration()                       ▲
        ▼                                                         │ slashAggregators()
[6] DINaggregatorsRegistrationStarted               [20] AuditorsSlashed
        │ closeDINaggregatorsRegistration()                       ▲
        ▼                                                         │ slashAuditors()
[7] DINaggregatorsRegistrationClosed                [19] T2AggregationDone
        │ startDINauditorsRegistration()                          ▲
        ▼                                                         │ finalizeT2Aggregation()
[8] DINauditorsRegistrationStarted                  [18] T2AggregationStarted
        │ closeDINauditorsRegistration()                          ▲
        ▼                                                         │ startT2Aggregation()
[9] DINauditorsRegistrationClosed                   [17] T1AggregationDone
        │ startLMsubmissions()                                    ▲
        ▼                                                         │ finalizeT1Aggregation()
[10] LMSstarted                                     [16] T1AggregationStarted
        │ closeLMsubmissions()                                    ▲
        ▼                                                         │ startT1Aggregation()
[11] LMSclosed                                      [15] T1nT2Bcreated
        │ createAuditorsBatches()                                 ▲
        ▼                                                         │ autoCreateTier1AndTier2()
[12] AuditorsBatchesCreated                         [14] LMSevaluationClosed
        │ startLMsubmissionsEvaluation()                          ▲
        ▼                                                         │ closeLMsubmissionsEvaluation()
[13] LMSevaluationStarted ────────────────────────────────────────┘
```

---

## 3. Cross-Contract Interfaces

### 3.1 `IDinValidatorStake`

```solidity
interface IDinValidatorStake {
    function getStake(address validator) external view returns (uint256);
    function slash(address validator, uint256 amount) external;
    function isSlasherContract(address slasherContract) external view returns (bool);
}
```

Used by: `DINTaskCoordinator`, `DINTaskAuditor`

| Method | Purpose |
|--------|---------|
| `getStake` | Check if a registrant has sufficient stake before accepting registration |
| `slash` | Penalise misbehaving aggregators (called by TaskCoordinator during `slashAggregators`) |
| `isSlasherContract` | Verify a contract is registered as a slasher (used during model registration) |

### 3.2 `IDINTaskCoordinator`

```solidity
interface IDINTaskCoordinator {
    function GI() external view returns (uint256);
    function GIstate() external view returns (GIstates);
}
```

Used by: `DINTaskAuditor`

| Method | Purpose |
|--------|---------|
| `GI()` | Read the current Global Iteration counter for validation in modifiers |
| `GIstate()` | Check the current lifecycle state to gate operations |

### 3.3 `IDINTaskAuditor`

```solidity
interface IDINTaskAuditor {
    function createAuditorsBatches(uint _GI) external returns (bool);
    function setTestDataAssignedFlag(uint _GI, bool flag) external;
    function finalizeEvaluation(uint _GI) external returns (bool);
    function approvedModelIndexes(uint _GI) external view returns (uint[] memory);
    function updatePassScore(uint256 newPassScore) external;
}
```

Used by: `DINTaskCoordinator`

| Method | Purpose |
|--------|---------|
| `createAuditorsBatches` | Called by coordinator to trigger batch formation in auditor contract |
| `setTestDataAssignedFlag` | Signals that test datasets have been distributed to batches |
| `finalizeEvaluation` | Computes final scores and approval decisions for all submissions |
| `approvedModelIndexes` | Returns indexes of models that passed evaluation (used for T1/T2 batch formation) |
| `updatePassScore` | Sets the minimum average score required for model approval (called at start of each GI) |

---

## 4. Custom Error Catalogue

### 4.1 DINTaskAuditor Errors (`TA_*`)

| Error | Description |
|-------|-------------|
| `TA_NotTaskCoordinator` | Function restricted to the TaskCoordinator was called by another address |
| `TA_AmountMustBePositive` | Deposit or reward amount is zero |
| `TA_InvalidPassScore` | Pass score set outside 0–100 range |
| `TA_AuditorRegistrationNotOpen` | Registration attempted outside registration window |
| `TA_WrongGI` | Global Iteration mismatch |
| `TA_AuditorAlreadyRegistered` | Duplicate auditor registration for same GI |
| `TA_InsufficientStake` | Auditor's stake below minimum threshold |
| `TA_LMSubmissionsNotOpen` | Local model submission attempted outside submission window |
| `TA_AlreadySubmitted` | Client has already submitted a model this GI |
| `TA_MaxLMSubmissionsReached` | Submission count reached `MAX_LM_SUBMISSIONS` (10,000) |
| `TA_NotEnoughAuditors` | Too few auditors to form even one batch |
| `TA_CannotCreateAuditorsBatches` | State is not `LMSclosed` |
| `TA_BatchNotFound` | Batch ID query out of bounds |
| `TA_BatchDoesNotExist` | Batch ID >= batch array length |
| `TA_BatchIDMismatch` | Internal sanity check failure on batch ID |
| `TA_CannotSetTestDataAssignedFlag` | State is not `AuditorsBatchesCreated` |
| `TA_FlagMustBeTrue` | `setTestDataAssignedFlag` called with `flag = false` |
| `TA_FlagAlreadySet` | Flag was already set for this GI |
| `TA_NotAssignedAuditor` | Score submission from auditor not in the batch |
| `TA_InvalidModelIndex` | Model index not assigned to this batch |
| `TA_CannotSetAuditScore` | State is not `LMSevaluationStarted` |
| `TA_ScoreOutOfRange` | Score > 100 |
| `TA_AlreadyVoted` | Auditor has already submitted score for this model |
| `TA_CannotFinalizeEvaluation` | State is not `LMSevaluationStarted` |

### 4.2 DINTaskCoordinator Errors (`TC_*`)

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
| `TC_InsufficientStake` | Aggregator stake below threshold |
| `TC_ValidatorAlreadyRegistered` | Duplicate aggregator registration |
| `TC_AggregatorsRegistrationCannotBeFinished` | Close called in wrong state |
| `TC_AuditorsRegistrationCannotBeStarted` | Auditor registration start in wrong state |
| `TC_AuditorsRegistrationCannotBeFinished` | Auditor registration close in wrong state |
| `TC_LMSubmissionsCannotBeStarted` | LM submission window start in wrong state |
| `TC_LMSubmissionsNotStarted` | LM submission close when not started |
| `TC_LMEvalCannotBeStarted` | Evaluation start in wrong state |
| `TC_LMEvalCannotBeFinished` | Evaluation close in wrong state |
| `TC_FailedToCreateAuditorsBatches` | `createAuditorsBatches` returned false |
| `TC_CannotSetTestDataAssignedFlag` | Test data flag set in wrong state |
| `TC_EvalPhaseNotClosed` | T1/T2 batch creation before evaluation close |
| `TC_NotEnoughValidators` | Too few aggregators for T1 batches |
| `TC_NotEnoughApprovedModels` | Fewer than `T1_MODELS_PER_BATCH` models approved |
| `TC_BatchNotFound` | Tier-1 batch ID out of bounds |
| `TC_OnlyOneTier2Batch` | Tier-2 batch ID != 0 |
| `TC_NotReadyForT1Aggregation` | T1 start in wrong state |
| `TC_T1AggregationNotStarted` | Submission or finalize called before T1 start |
| `TC_InvalidBatch` | Batch ID >= tier1Batches length |
| `TC_NotBatchAggregator` | Submitter not assigned to the batch |
| `TC_AlreadySubmitted` | Aggregator has already submitted for this batch |
| `TC_NoSubmissions` | No CIDs were submitted; cannot determine winner |
| `TC_NotReadyToFinalizeT1` | T1 finalize called in wrong state |
| `TC_NotReadyForT2Aggregation` | T2 start in wrong state |
| `TC_T2AggregationNotStarted` | T2 submission or finalize called before T2 start |
| `TC_NotReadyToFinalizeT2` | T2 finalize called in wrong state |
| `TC_NotReadyToSlashAuditors` | Auditor slash called before T2 done |
| `TC_NotReadyToSlashAggregators` | Aggregator slash called before auditors slashed |
| `TC_NotReadyToSetTier2Score` | Tier-2 score set in wrong state |
| `TC_NotReadyToEndGI` | `endGI` called before aggregators slashed |
| `TC_FailedToFinalizeEvaluation` | `finalizeEvaluation` returned false |

---

## 5. Design Rationale

### Why a Shared File?

Both `DINTaskCoordinator` and `DINTaskAuditor` need to read each other's state (via interfaces) and react to shared lifecycle states (via `GIstates`). Without `DINShared.sol`:
- The enum would be duplicated across contracts, risking value drift.
- Interface definitions could go stale when one contract is updated without updating the other.

### Error Namespacing

The `TA_` and `TC_` prefixes make it immediately clear in stack traces and event logs which contract emitted an error, even when both contracts are interacting in the same transaction.
