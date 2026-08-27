# DINTaskAuditor — Technical Documentation

> **File:** `foundry/src/DINTaskAuditor.sol`
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DINTaskAuditor` is the **evaluation and quality-control contract** for each Global Iteration (GI). Its responsibilities:

1. **Auditor registration** — Accept active DIN validators as auditors for a GI.
2. **Local Model Submission (LMS)** — Accept hashed local model submissions from FL clients.
3. **Audit batch formation** — Randomly assign currently-active auditors to batches of submitted models.
4. **Test dataset distribution** — Record each batch's test-data CID and each assigned auditor's individually-encrypted decryption key (task_210726_6 §2b).
5. **Model evaluation** — Commit-then-reveal auditor scoring and eligibility voting (task_210726_6 §2a).
6. **Evaluation finalization** — Compute final median scores and determine which models are approved for aggregation.
7. **Auditor slashing** — Penalise auditors who missed a vote (S1), and, once enabled, auditors whose revealed score deviates too far from the model's median (S3).

The contract is owned by the model owner (OpenZeppelin `Ownable`) and callable by `DINTaskCoordinator` for state-transition operations.

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | Owner-restricted functions (test data assignment, S3 threshold/toggle) |
| `DINShared.sol` | Local | `GIstates` enum, cross-contract interfaces, error declarations |

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinvalidatorStakeContract` | `IDinValidatorStake` | `public` | Stake contract for auditor activity checks and slashing; also the source of `minStake()` used as the slash amount |
| `dintaskcoordinatorContract` | `IDINTaskCoordinator` | `public` | Coordinator for GI/state reads |
| `totalDepositedRewards` | `uint` | `public` | Accumulated reward deposits (informational only) |
| `MAX_LM_SUBMISSIONS` | `uint` | *(default, internal)* | Hard cap per GI: `10,000` |
| `params` | `Params` | `public` | Per-round tunable parameters |
| `s3DeviationThreshold` | `uint256` | `public` | S3 auditor-deviation threshold, 0–100 scale; default `40` (deliberately wide, not a validated production value — see §6 below) |
| `s3SlashingEnabled` | `bool` | `public` | Whether S3 deviation actually triggers slashing in `slashAuditors`; default `false` (shadow mode) |
| `dinAuditors` | `mapping(uint => address[])` | `public` | Registered auditors per GI |
| `isRegisteredAuditor` | `mapping(uint => mapping(address => bool))` | `public` | Auditor registration membership |
| `lmSubmissions` | `mapping(uint => LMSubmission[])` | `public` | All submitted local models per GI |
| `clientHasSubmitted` | `mapping(uint => mapping(address => bool))` | `public` | One-submission-per-client guard |
| `clientSubmissionIndex` | `mapping(uint => mapping(address => uint))` | `public` | Client address → submission index |
| `auditBatches` | `mapping(uint256 => AuditBatch[])` | `public` | Formed audit batches per GI |
| `isBatchAuditor` | `mapping(uint => mapping(uint => mapping(address => bool)))` | `public` | GI → batchId → auditor → assigned |
| `isBatchModelIndex` | `mapping(uint => mapping(uint => mapping(uint => bool)))` | `public` | GI → batchId → modelIndex → assigned |
| `auditScores` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → revealed score |
| `LMeligibleVote` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → revealed eligibility vote |
| `hasAuditedLM` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → has revealed (single source of truth for quorum/median counting) |
| `auditScoreCommits` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → `keccak256(score, vote, salt)` commit hash |
| `hasCommittedLM` | 4-level mapping | `public` | GI → batchId → auditor → modelIndex → has committed (distinct from `hasAuditedLM` — see §9.1) |
| `encryptedTestDataKey` | `mapping(uint256 => mapping(uint => mapping(address => bytes)))` | `public` | GI → batchId → auditor → that auditor's individually-encrypted copy of the test-data decryption key |
| `Is_testdataCIDs_Assigned` | `mapping(uint256 => bool)` | `public` | Whether test datasets are assigned for a GI |

> **Note:** there is no `minStake` state variable on this contract (auditor registration and slashing both go through `dinvalidatorStakeContract` — `isValidatorActive()` for registration/commit/reveal, `minStake()` for the slash amount — not a locally-cached threshold).

---

## 4. Data Structures

### 4.1 `LMSubmission`

```solidity
struct LMSubmission {
    address client;        // Submitting FL client
    bytes32 modelCID;      // IPFS CID hash of the local model
    uint40 submittedAt;    // Block timestamp
    bool eligible;         // Passed basic conformance check (majority vote)
    bool evaluated;        // Score quorum reached and finalMedianScore computed
    bool approved;         // eligible == true AND finalMedianScore >= passScore
    uint256 finalMedianScore; // 0-100, canonical per-model score for both S3 slashing and the reward basis
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
  ├── assignAuditTestDataset()
  ├── setS3DeviationThreshold()
  └── setS3SlashingEnabled()

onlyTaskCoordinator (DINTaskCoordinator only)
  ├── createAuditorsBatches()
  ├── setTestDataAssignedFlag()
  ├── finalizeEvaluation()
  ├── slashAuditors()
  └── updatePassScore()

onlyAssignedAuditor + onlyCurrentGI
  ├── commitAuditScore()
  └── revealAuditScore()

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
3. Check `dinvalidatorStakeContract.isValidatorActive(msg.sender)`.
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

Called by `DINTaskCoordinator` after LM submission closes (`GIstate == LMSclosed`).

**Algorithm:**

1. Filter the historical registration list `dinAuditors[_GI]` down to auditors still `isValidatorActive` at call time (`_activeAuditorPool`). Revert (`TA_NotEnoughAuditors`) if fewer than `params.auditorsPerBatch` remain active.
2. Shuffle the active pool (Fisher-Yates, storage) using `blockhash(block.number - 1)` as entropy.
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

Auditor scoring is **commit-then-reveal** (task_210726_6 §2a), split across two GI states: `LMSevaluationStarted` (commit phase) and `LMSevaluationRevealStarted` (reveal phase, opened by `DINTaskCoordinator.startLMsubmissionsEvaluationReveal`). This hides each auditor's score/vote from the others until every commit is in, preventing later auditors from anchoring on earlier ones' revealed scores.

### 9.1 Commit Phase — `commitAuditScore`

```solidity
function commitAuditScore(
    uint256 gi, uint batchId, uint modelIndex, bytes32 commitHash
) external onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi)
```

`commitHash` must equal `keccak256(abi.encodePacked(score, vote, salt))` for the values the auditor intends to reveal later; the contract cannot and does not validate this at commit time.

1. Check `GIstate == LMSevaluationStarted`.
2. Check `dinvalidatorStakeContract.isValidatorActive(msg.sender)`.
3. Check `commitHash != bytes32(0)`.
4. One-commit-per-model guard (`hasCommittedLM`).
5. Record the commit hash, set `hasCommittedLM`, emit `AuditScoreCommitted`.

### 9.2 Reveal Phase — `revealAuditScore`

```solidity
function revealAuditScore(
    uint256 gi, uint batchId, uint modelIndex, uint256 score, bool vote, bytes32 salt
) external onlyAssignedAuditor(gi, batchId, modelIndex) onlyCurrentGI(gi)
```

1. Check `GIstate == LMSevaluationRevealStarted`.
2. Check `dinvalidatorStakeContract.isValidatorActive(msg.sender)`.
3. Check `score <= 100`.
4. Check a commit exists (`hasCommittedLM`) and hasn't already been revealed (`hasAuditedLM`).
5. Recompute `keccak256(abi.encodePacked(score, vote, salt))` and check it matches the stored commit hash.
6. Record score and eligibility vote, set `hasAuditedLM`, emit `AuditScoreSubmitted` + `EligibilityVoted`.
7. Call `_tryFinalizeEligibility()` eagerly.

`hasCommittedLM` and `hasAuditedLM` are deliberately distinct: an auditor who commits but never reveals ends up with `hasCommittedLM=true, hasAuditedLM=false`, so they're excluded from quorum/median counting exactly like a non-participant, and remain slashable via `slashAuditors`' "missed vote" check — no special-casing needed for the non-reveal case.

### 9.3 Eligibility Finalization (`_tryFinalizeEligibility`)

Internal; triggered after each reveal.

```
Count yesVotes and totalVotes for the model across batch auditors (via hasAuditedLM).
If totalVotes < minEligibilityQuorum → wait.
majorityEligible = (yesVotes >= minEligibilityQuorum)
Set submission.eligible = majorityEligible.
```

### 9.4 Evaluation Finalization

```solidity
function finalizeEvaluation(uint _GI) public onlyTaskCoordinator returns (bool)
```

Called by the coordinator to close the reveal phase (`GIstate` must be `LMSevaluationRevealStarted`, else `TA_CannotFinalizeEvaluation`):

```
For each batch:
  For each model in batch:
    Re-attempt eligibility finalization if not yet eligible.
    Collect scores from auditors who actually revealed (hasAuditedLM).
    If revealed-vote count >= minScoreQuorum:
      sub.finalMedianScore = _medianOf(votedScores)   // MEDIAN, not mean — task_210726_6 §1c
      sub.evaluated = true
      sub.approved = (sub.eligible AND finalMedianScore >= params.passScore)
      Emit AuditorScoreDeviation for every revealed voter (S3 shadow mode, §9.5)
Return true if finalizedCount > 0.
```

The score is the **median** across the auditor batch, not a mean — a mean lets a single dishonest auditor drag the score arbitrarily far, while a median tolerates fewer than 50% dishonest auditors (BlockFlow Algorithm 1). `_medianOf` sorts in place; even-length batches median as the integer-divided average of the two middle elements.

**Approval condition (both must hold):**
- `eligible == true` (majority voted conformant)
- `finalMedianScore >= passScore`

### 9.5 S3 Deviation Tracking (shadow mode)

For every model that reaches score quorum, `finalizeEvaluation` also emits `AuditorScoreDeviation(gi, batchId, modelIndex, auditor, auditorScore, medianScore, deviation, exceedsThreshold)` for each auditor who revealed a score on it, where `deviation = |auditorScore - medianScore|` and `exceedsThreshold = deviation > s3DeviationThreshold`. This is purely observational unless `s3SlashingEnabled` is turned on (see §10) — per `MECHANISM_DESIGN.md` §6, the threshold (default `40`) must be empirically validated against real audit-score variance before it's allowed to cost auditors stake. The owner tunes it via `setS3DeviationThreshold`/`setS3SlashingEnabled`.

### 9.6 `approvedModelIndexes`

Returns compact array of `lmSubmissions[_GI]` indexes where `approved == true`. Used by `DINTaskCoordinator` for T1/T2 batch formation.

---

## 10. Auditor Slashing

```solidity
function slashAuditors(uint _GI) external onlyTaskCoordinator onlyCurrentGI(_GI) returns (bool)
```

Called by the coordinator once `GIstate == T2AggregationDone`. For every auditor in every batch:

- **S1 — missed vote:** if the auditor never revealed (`hasAuditedLM == false`) for *any* model assigned to their batch, slash with reason `AUD_NO_VOTE`. Takes priority over S3 — an auditor who missed a vote is not also re-evaluated for S3 in the same batch.
- **S3 — score deviation:** only checked when `s3SlashingEnabled == true` and the auditor revealed on every model in the batch. If any revealed score deviated from that model's `finalMedianScore` by more than `s3DeviationThreshold`, slash with reason `AUD_SCORE_DEVIATION` (at most once per batch, even if multiple votes deviated).

Slash amount is `dinvalidatorStakeContract.minStake()` at call time for both reasons (see `MECHANISM_DESIGN.md` §9 item 2 on the still-open flat-vs-partial slash-fraction question). Each slashed auditor emits `AuditorSlashed(gi, batchId, auditor, reason, requested, actual)`. Always returns `true`; individual slash failures do not halt the loop.

---

## 11. Test Data Assignment

```solidity
function assignAuditTestDataset(
    uint256 gi, uint256 batchId, bytes32 testDataCID, bytes[] calldata encryptedKeys
) external onlyOwner onlyCurrentGI(gi)
```

Owner-only. Records the test dataset IPFS CID for a batch, and — per task_210726_6 §2b / whitepaper §5.2.3b — each assigned auditor's individually-encrypted copy of the test-data decryption key. `encryptedKeys[i]` must correspond to `auditBatches[gi][batchId].auditors[i]` (same order `createAuditorsBatches` populated them in); reverts with `TA_EncryptedKeyCountMismatch` if the lengths differ. The model owner is responsible for producing `encryptedKeys` off-chain (a symmetric test-data key encrypted to each auditor's public key) — the contract only stores what it's given and cannot validate the encryption itself. Emits `EncryptedTestDataKeysAssigned`.

**`setTestDataAssignedFlag`** (coordinator only): Sets `Is_testdataCIDs_Assigned[_GI] = true` once all datasets are assigned. One-time per GI.

---

## 12. Privacy Architecture

| Data | On-chain | Off-chain |
|------|---------|-----------|
| Model weights | ❌ | ✅ IPFS (`modelCID`) |
| Test dataset | ❌ | ✅ IPFS (`testDataCID`) |
| Test-data decryption key (per-auditor) | ✅ (encrypted `bytes`, `encryptedTestDataKey`) | key material itself only ever exists off-chain, decrypted client-side by the auditor |
| Submission record (client, CID) | ✅ | — |
| Audit score / eligibility vote before reveal | ❌ (only the commit hash, `auditScoreCommits`) | actual `(score, vote, salt)` known only to the committing auditor |
| Audit score / eligibility vote after reveal | ✅ | — |
| Final approval | ✅ | — |

---

## 13. Events

| Event | Emitted When |
|-------|--------------|
| `DINAuditorRegistered(GI, auditor)` | Auditor registers |
| `AuditScoreCommitted(gi, batchId, auditor, modelIndex, commitHash)` | Commit phase: score/vote hash committed |
| `AuditScoreSubmitted(gi, batchId, auditor, modelIndex, score)` | Reveal phase: score revealed |
| `EligibilityVoted(gi, batchId, modelIndex, auditor, vote)` | Reveal phase: eligibility vote revealed |
| `EligibilityFinalized(gi, batchId, modelIndex, eligible, totalVotes)` | Eligibility quorum reached |
| `EncryptedTestDataKeysAssigned(gi, batchId, testDataCID, auditorCount)` | Test dataset + per-auditor keys assigned to a batch |
| `AuditorsBatchAuto(GI, batchId)` | Individual batch created |
| `AuditorsBatchesCreated(GI, batchCount)` | All batches created |
| `PassScoreUpdated(oldScore, newScore)` | Pass score changed |
| `S3DeviationThresholdUpdated(oldThreshold, newThreshold)` | S3 threshold changed |
| `S3SlashingEnabledUpdated(oldValue, newValue)` | S3 shadow mode toggled |
| `AuditorScoreDeviation(gi, batchId, modelIndex, auditor, auditorScore, medianScore, deviation, exceedsThreshold)` | Emitted for every revealed voter on a finalized model (S3 shadow mode, always emitted regardless of `s3SlashingEnabled`) |
| `AuditorSlashed(gi, batchId, auditor, reason, requested, actual)` | Auditor slashed (S1 or S3) |

---

## 14. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Weak PRNG for shuffling | Acceptable for devnet; use Chainlink VRF in production |
| Colluding/copying auditors | Commit-then-reveal (§9.1–9.2) prevents an auditor from anchoring their score on others' already-revealed votes |
| Sybil auditor registration | Gated by `isValidatorActive` (DinValidatorStake), not a raw stake threshold on this contract |
| Double voting / double committing | `hasCommittedLM` and `hasAuditedLM` each prevent a repeat |
| Reveal without a matching commit | `TA_NoCommitFound` / `TA_RevealHashMismatch` reject reveals that don't match a prior commit |
| Batch flooding | `MAX_LM_SUBMISSIONS` cap at 10,000 |
| Gas exhaustion in `finalizeEvaluation` / `slashAuditors` | O(batches × models × auditors) — could hit limits at scale |
| Untuned S3 threshold slashing honest variance | Defaults to shadow mode (`s3SlashingEnabled = false`); must be empirically validated before enabling (`MECHANISM_DESIGN.md` §6) |
| Model owner supplies invalid/wrong-recipient encrypted test-data keys | Not detectable on-chain — `assignAuditTestDataset` stores whatever `encryptedKeys` it's given; no on-chain dispute mechanism exists yet for this (see `Developer/tasks/task_240826_10.md`) |

---

## 15. Known Limitations & Future Work

- Reward distribution to auditors not implemented (`totalDepositedRewards` is tracked but unused).
- `params` struct is immutable post-deployment except `passScore` (updatable via `updatePassScore`).
- Models not reaching score quorum are silently left unapproved with no alerting.
- No mechanism to re-open evaluation if quorum is not reached before `finalizeEvaluation` is called.
- No on-chain dispute resolution if a model owner distributes an incorrect or wrong-recipient `encryptedTestDataKey` — an auditor who can't decrypt the test data currently has no on-chain recourse. Tracked in `Developer/tasks/task_240826_10.md`.
- `s3DeviationThreshold`'s default (`40`) is a deliberately wide placeholder, not a tuned production value.
