# DINTaskAuditor — Technical Documentation

> **File:** `hardhat/contracts/DINTaskAuditor.sol`
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DINTaskAuditor` is the **evaluation and quality-control contract** for each Global Iteration (GI). Its responsibilities:

1. **Auditor registration** — Accept DIN validators as auditors for a GI.
2. **Local Model Submission (LMS)** — Accept hashed local model submissions from FL clients.
3. **Audit batch formation** — Randomly assign auditors to batches of submitted models.
4. **Model evaluation** — Record auditor scores and eligibility votes.
5. **Evaluation finalization** — Compute final average scores and determine which models are approved for aggregation.

The contract is owned by the model owner (OpenZeppelin `Ownable`) and callable by `DINTaskCoordinator` for state-transition operations.

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | Owner-restricted functions (assign test data) |
| `DINShared.sol` | Local | `GIstates` enum, cross-contract interfaces, error declarations |

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinvalidatorStakeContract` | `IDinValidatorStake` | `public` | Stake contract for auditor stake checks |
| `dintaskcoordinatorContract` | `IDINTaskCoordinator` | `public` | Coordinator for GI/state reads |
| `totalDepositedRewards` | `uint` | `public` | Accumulated reward deposits (informational only) |
| `minStake` | `uint256` | `public` | Min stake for auditor registration: `1,000,000` raw units |
| `MAX_LM_SUBMISSIONS` | `uint` | `private` | Hard cap per GI: `10,000` |
| `params` | `Params` | `public` | Per-round tunable parameters |
| `dinAuditors` | `mapping(uint => address[])` | `public` | Registered auditors per GI |
| `isRegisteredAuditor` | `mapping(uint => mapping(address => bool))` | `public` | Auditor registration membership |
| `lmSubmissions` | `mapping(uint => LMSubmission[])` | `public` | All submitted local models per GI |
| `clientHasSubmitted` | `mapping(uint => mapping(address => bool))` | `public` | One-submission-per-client guard |
| `clientSubmissionIndex` | `mapping(uint => mapping(address => uint))` | `public` | Client address → submission index |
| `auditBatches` | `mapping(uint256 => AuditBatch[])` | `public` | Formed audit batches per GI |
| `isBatchAuditor` | `mapping(uint => mapping(uint => mapping(address => bool)))` | `public` | GI → batchId → auditor → assigned |
| `isBatchModelIndex` | `mapping(uint => mapping(uint => mapping(uint => bool)))` | `public` | GI → batchId → modelIndex → assigned |
| `auditScores` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → score |
| `LMeligibleVote` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → eligibility vote |
| `hasAuditedLM` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → voted flag |
| `Is_testdataCIDs_Assigned` | `mapping(uint256 => bool)` | `public` | Whether test datasets are assigned for a GI |

---

## 4. Data Structures

### 4.1 `LMSubmission`

```solidity
struct LMSubmission {
    address client;        // Submitting FL client
    bytes32 modelCID;      // IPFS CID hash of the local model
    uint40 submittedAt;    // Block timestamp
    bool eligible;         // Passed basic conformance check (majority vote)
    bool evaluated;        // Score quorum reached and avg computed
    bool approved;         // eligible == true AND finalAvgScore >= passScore
    uint256 finalAvgScore; // Integer average score (0–100)
}
```

### 4.2 `Params` (default values)

| Parameter | Default | Spec Target |
|-----------|---------|-------------|
| `auditorsPerBatch` | 3 | 10 |
| `modelsPerBatch` | 3 | 100 |
| `minEligibilityQuorum` | 2 | 7 |
| `minScoreQuorum` | 2 | 7 |
| `passScore` | 50 | 50 |
| `minAuditorStake` | 1,000,000 | — |
| `MIN_MODELS_PER_BATCH` | 2 | — |

### 4.3 `AuditBatch`

```solidity
struct AuditBatch {
    uint batchId;           // Sequential batch index within a GI
    address[] auditors;     // Assigned auditors
    uint[] modelIndexes;    // Indexes into lmSubmissions[GI]
    bytes32 testDataCID;    // IPFS CID of test dataset for this batch
}
```

---

## 5. Access Control

```
Ownable (model owner)
  └── assignAuditTestDataset()

onlyTaskCoordinator (DINTaskCoordinator only)
  ├── createAuditorsBatches()
  ├── setTestDataAssignedFlag()
  ├── finalizeEvaluation()
  └── updatePassScore()

onlyAssignedAuditor + onlyCurrentGI
  └── setAuditScorenEligibility()

Permissionless (within GI/state guards)
  ├── registerDINAuditor()
  └── submitLocalModel()
```

---

## 6. Auditor Registration

```solidity
function registerDINAuditor(uint _GI) public onlyCurrentGI(_GI)
```

1. Check `GIstate == DINauditorsRegistrationStarted`.
2. Check not already registered.
3. Check `stake >= minStake` via `dinvalidatorStakeContract.getStake()`.
4. Push to `dinAuditors[_GI]`, set membership flag.
5. Emit `DINAuditorRegistered`.

---

## 7. Local Model Submission

```solidity
function submitLocalModel(bytes32 _clientModel, uint _GI) public onlyCurrentGI(_GI)
```

**Privacy:** Only the `bytes32` IPFS hash is stored on-chain. Actual weights remain off-chain.

1. Check `GIstate == LMSstarted`.
2. One-per-client guard (`clientHasSubmitted`).
3. Enforce `MAX_LM_SUBMISSIONS` cap.
4. Push `LMSubmission` (all flags false, scores zero).
5. Record `clientSubmissionIndex`.

---

## 8. Audit Batch Formation

### `createAuditorsBatches`

Called by `DINTaskCoordinator` after LM submission closes.

**Algorithm:**

1. Load `dinAuditors[_GI]`. Revert if fewer than `auditorsPerBatch`.
2. Shuffle auditors (Fisher-Yates, storage) using `blockhash(block.number - 1)` as entropy.
3. Build `uint[]` of model indexes `[0..N-1]`. Shuffle (memory) using `block.timestamp + msg.sender`.
4. Greedy batch formation:
   ```
   while vPtr + auditorsPerBatch <= aLen
         AND (enough models remain for a full or partial-but-minimum batch):
       Create AuditBatch:
         auditors = auditorPool[vPtr .. vPtr+auditorsPerBatch-1]
         modelsToAssign = min(modelsPerBatch, remaining models)
         modelIndexes = modelIdx[mPtr .. mPtr+modelsToAssign-1]
       vPtr += auditorsPerBatch
       mPtr += modelsToAssign
   ```
5. Emit `AuditorsBatchesCreated`.

> ⚠️ **PRNG Warning:** `blockhash` and `block.timestamp` are weak on-chain entropy sources, manipulable by block producers. Replace with Chainlink VRF in production.

---

## 9. Evaluation Mechanism

### 9.1 Score & Eligibility Submission

```solidity
function setAuditScorenEligibility(
    uint256 gi, uint batchId, uint modelIndex, uint256 score, bool vote
) public onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi)
```

1. Check `GIstate == LMSevaluationStarted`.
2. Check `score <= 100`.
3. One-vote guard (`hasAuditedLM`).
4. Record score and eligibility vote.
5. Call `_tryFinalizeEligibility()` eagerly.

### 9.2 Eligibility Finalization (`_tryFinalizeEligibility`)

Internal; triggered after each vote.

```
Count yesVotes and totalVotes for the model across batch auditors.
If totalVotes < minEligibilityQuorum → wait.
majorityEligible = (yesVotes >= minEligibilityQuorum)
Set submission.eligible = majorityEligible.
```

### 9.3 Evaluation Finalization

```solidity
function finalizeEvaluation(uint _GI) public onlyTaskCoordinator returns (bool)
```

Called by coordinator to close the evaluation phase:

```
For each batch:
  For each model in batch:
    Re-attempt eligibility finalization if not yet eligible.
    Compute avg = sum(scores from voters) / voterCount
    If votes >= minScoreQuorum:
      sub.finalAvgScore = avg
      sub.evaluated = true
      sub.approved = (sub.eligible AND avg >= params.passScore)
Return true if finalizedCount > 0.
```

**Approval condition (both must hold):**
- `eligible == true` (majority voted conformant)
- `finalAvgScore >= passScore`

### 9.4 `approvedModelIndexes`

Returns compact array of `lmSubmissions[_GI]` indexes where `approved == true`. Used by `DINTaskCoordinator` for T1/T2 batch formation.

---

## 10. Test Data Assignment

**`assignAuditTestDataset`** (owner only): Records the test dataset IPFS CID for a specific batch. Auditors retrieve data from IPFS using this CID.

**`setTestDataAssignedFlag`** (coordinator only): Sets `Is_testdataCIDs_Assigned[_GI] = true` once all datasets are assigned. One-time per GI.

---

## 11. Privacy Architecture

| Data | On-chain | Off-chain |
|------|---------|-----------|
| Model weights | ❌ | ✅ IPFS (`modelCID`) |
| Test dataset | ❌ | ✅ IPFS (`testDataCID`) |
| Submission record (client, CID, scores) | ✅ | — |
| Eligibility votes | ✅ | — |
| Final approval | ✅ | — |

---

## 12. Events

| Event | Emitted When |
|-------|--------------|
| `DINAuditorRegistered(GI, auditor)` | Auditor registers |
| `AuditScoreSubmitted(gi, batchId, auditor, modelIndex, score)` | Score submitted |
| `EligibilityVoted(gi, batchId, modelIndex, auditor, vote)` | Eligibility vote |
| `EligibilityFinalized(gi, batchId, modelIndex, eligible, totalVotes)` | Quorum reached |
| `AuditorsBatchAuto(GI, batchId)` | Individual batch created |
| `AuditorsBatchesCreated(GI, batchCount)` | All batches created |
| `PassScoreUpdated(oldScore, newScore)` | Pass score changed |

---

## 13. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Weak PRNG for shuffling | Acceptable for devnet; use Chainlink VRF in production |
| Colluding auditors | Quorum thresholds reduce individual impact |
| Sybil auditor registration | Stake requirement gates registration |
| Double voting | `hasAuditedLM` prevents repeat votes |
| Batch flooding | `MAX_LM_SUBMISSIONS` cap at 10,000 |
| Gas exhaustion in `finalizeEvaluation` | O(batches × models × auditors) — could hit limits at scale |

---

## 14. Known Limitations & Future Work

- Reward distribution to auditors not implemented (`totalDepositedRewards` is tracked but unused).
- `params` struct is immutable post-deployment except `passScore` (updatable via `updatePassScore`).
- Models not reaching score quorum are silently left unapproved with no alerting.
- No mechanism to re-open evaluation if quorum is not reached before `finalizeEvaluation` is called.
