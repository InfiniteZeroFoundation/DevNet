# DINTaskCoordinator — Technical Documentation

> **File:** `hardhat/contracts/DINTaskCoordinator.sol`
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DINTaskCoordinator` is the **central orchestration contract** for the DIN Protocol's federated learning workflow. It is the single entity that drives the 23-state Global Iteration (GI) lifecycle, coordinates between aggregators and the auditor contract, and executes slashing of misbehaving participants.

Responsibilities:
- **State machine management** — Advance `GIstate` through the full GI lifecycle.
- **Aggregator registration** — Accept staked validators as aggregators for a GI.
- **Tier-1 and Tier-2 batch creation** — Form aggregation batches from approved local models.
- **Aggregation result collection** — Accept and vote on aggregated model CIDs.
- **Slashing** — Penalise auditors and aggregators that failed to participate or submitted incorrect results.

The contract is owned by the model owner (via `Ownable`) and delegates auditor operations to `DINTaskAuditor`.

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | Owner-restricted lifecycle transitions |
| `DINShared.sol` | Local | `GIstates` enum, cross-contract interfaces, error declarations |

---

## 3. State Variables

### 3.1 Core State

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinvalidatorStakeContract` | `IDinValidatorStake` | `public` | Validator stake contract for stake checks and slashing |
| `dinTaskAuditorContract` | `IDINTaskAuditor` | `public` | Auditor contract for delegation |
| `GI` | `uint` | `public` | Current Global Iteration counter (starts at 0, first active GI = 1) |
| `GIstate` | `GIstates` | `public` | Current lifecycle state |
| `genesisModelIpfsHash` | `bytes32` | `public` | IPFS hash of the genesis model, set once before GI 1 |
| `minStake` | `uint256` | `public` | Minimum stake for aggregator registration: `1,000,000` raw units |

### 3.2 Aggregator Registry

| Variable | Type | Description |
|----------|------|-------------|
| `dinAggregators` | `mapping(uint => address[])` | Registered aggregators per GI |
| `isDINAggregator` | `mapping(uint => mapping(address => bool))` | Membership check |

### 3.3 Tier-1 Batch State

| Variable | Type | Description |
|----------|------|-------------|
| `tier1Batches` | `mapping(uint => Tier1Batch[])` | T1 batches per GI |
| `isTier1Aggregator` | `mapping(uint => mapping(uint => mapping(address => bool)))` | GI → batchId → address → assigned |
| `t1SubmissionCID` | `mapping(uint => mapping(uint => mapping(address => bytes32)))` | Submitted CID per aggregator |
| `t1Submitted` | `mapping(uint => mapping(uint => mapping(address => bool)))` | Submission flag |
| `t1Votes` | `mapping(uint => mapping(uint => mapping(bytes32 => uint)))` | Vote count per CID |

### 3.4 Tier-2 Batch State

| Variable | Type | Description |
|----------|------|-------------|
| `tier2Batches` | `mapping(uint => Tier2Batch[])` | T2 batches per GI (always exactly 1) |
| `isTier2Aggregator` | `mapping(uint => mapping(uint => mapping(address => bool)))` | Assignment check |
| `t2SubmissionCID` | `mapping(uint => mapping(uint => mapping(address => bytes32)))` | Submitted CID |
| `t2Submitted` | `mapping(uint => mapping(uint => mapping(address => bool)))` | Submission flag |
| `t2Votes` | `mapping(uint => mapping(uint => mapping(bytes32 => uint)))` | Vote count per CID |
| `tier2Score` | `mapping(uint => uint)` | Final score recorded for a GI's T2 output |

---

## 4. Data Structures

### 4.1 `Tier1Batch`

```solidity
struct Tier1Batch {
    uint batchId;           // Unique within GI (sequential)
    address[] aggregators;  // Aggregators assigned to this batch
    uint[] modelIndexes;    // Indexes into approvedModels for this GI
    bool finalized;         // True after majority winner determined
    bytes32 finalCID;       // Winning aggregated model CID
}
```

### 4.2 `Tier2Batch`

```solidity
struct Tier2Batch {
    uint batchId;           // Always 0 (only one T2 batch)
    address[] aggregators;  // T2 aggregators
    bool finalized;
    bytes32 finalCID;       // Global winning aggregated CID
}
```

### 4.3 Aggregation Constants

```solidity
uint256 public constant T1_AGGREGATORS_PER_BATCH = 3;
uint256 public constant T1_MODELS_PER_BATCH = 3;
uint256 public constant MIN_T1_MODELS_PER_BATCH = 2;
```

---

## 5. Access Control

```
Ownable (model owner)
  ├── setDINTaskAuditorContract()
  ├── setDINTaskCoordinatorAsSlasher()
  ├── setDINTaskAuditorAsSlasher()
  ├── setGenesisModelIpfsHash()
  ├── startGI()
  ├── startDINaggregatorsRegistration()
  ├── closeDINaggregatorsRegistration()
  ├── startDINauditorsRegistration()
  ├── closeDINauditorsRegistration()
  ├── startLMsubmissions()
  ├── closeLMsubmissions()
  ├── createAuditorsBatches()
  ├── setTestDataAssignedFlag()
  ├── startLMsubmissionsEvaluation()
  ├── closeLMsubmissionsEvaluation()
  ├── autoCreateTier1AndTier2()
  ├── startT1Aggregation()
  ├── finalizeT1Aggregation()
  ├── startT2Aggregation()
  ├── finalizeT2Aggregation()
  ├── slashAuditors()
  ├── slashAggregators()
  ├── setTier2Score()
  └── endGI()

Permissionless (with batch/GI guards)
  ├── registerDINaggregator()
  ├── submitT1Aggregation()
  └── submitT2Aggregation()
```

---

## 6. Initialization Sequence (Pre-GI Setup)

Before any GI can begin, a one-time setup must be completed:

```
State: [0] AwaitingDINTaskAuditorToBeSet
  → setDINTaskAuditorContract(auditorAddress)
State: [1] AwaitingDINTaskCoordinatorAsSlasher
  → (DAO calls DinCoordinator.addSlasherContract(taskCoordinatorAddress))
  → setDINTaskCoordinatorAsSlasher()    // verifies isSlasherContract(this) == true
State: [2] AwaitingDINTaskAuditorAsSlasher
  → (DAO calls DinCoordinator.addSlasherContract(taskAuditorAddress))
  → setDINTaskAuditorAsSlasher()        // verifies isSlasherContract(auditor) == true
State: [3] AwaitingGenesisModel
  → setGenesisModelIpfsHash(cid)
State: [4] GenesisModelCreated
```

---

## 7. GI Lifecycle Functions

### 7.1 `startGI`

```solidity
function startGI(uint _GI, uint score) public onlyOwner
```

1. Check `GIstate == GenesisModelCreated` or `GIstate == GIended` (allows repeat GIs).
2. Check `_GI == GI + 1` (must increment by exactly 1).
3. Call `dinTaskAuditorContract.updatePassScore(score)` — sets minimum approval threshold for this GI.
4. Set `GIstate = GIstarted`, increment `GI`.

---

### 7.2 Aggregator Registration

```solidity
function registerDINaggregator(uint _GI) public
```

Permissionless (no `onlyCurrentGI` modifier — note: `isDINAggregator[_GI]` check uses the passed `_GI`).

1. Check `GIstate == DINaggregatorsRegistrationStarted`.
2. Check `stake >= minStake`.
3. Check not already registered.
4. Push to `dinAggregators[_GI]`, set membership.
5. Emit `DINValidatorRegistered`.

---

### 7.3 Tier-1 and Tier-2 Batch Formation (`autoCreateTier1AndTier2`)

```solidity
function autoCreateTier1AndTier2(uint _GI) external onlyOwner onlyCurrentGI(_GI)
```

Called after LM evaluation closes (`LMSevaluationClosed`).

**Algorithm:**

1. **Load aggregator pool:** `valPool = dinAggregators[_GI]`. Revert if `vLen < T1_AGGREGATORS_PER_BATCH`.

2. **Shuffle aggregators (Fisher-Yates, storage):**
   ```
   j = keccak256(blockhash(block.number - 1), i, arr.length) % (i+1)
   ```

3. **Collect approved model indexes:** Calls `dinTaskAuditorContract.approvedModelIndexes(_GI)`. Revert if fewer than `T1_MODELS_PER_BATCH`.

4. **Shuffle model indexes (Fisher-Yates, memory):**
   ```
   j = keccak256(block.timestamp, i, arr.length, msg.sender) % (i+1)
   ```

5. **Greedy T1 batch creation:**
   ```
   while vPtr + T1_AGGREGATORS_PER_BATCH <= vLen
         AND (enough models for a full or minimum-size batch):
       T1 batch:
         aggregators = valPool[vPtr .. vPtr+2]
         modelsToAssign = min(T1_MODELS_PER_BATCH, remaining)
         modelIndexes = modelIdx[mPtr .. mPtr+modelsToAssign-1]
       vPtr += 3, mPtr += modelsToAssign
   ```

6. **T2 batch creation:** If `vLen - vPtr >= T1_AGGREGATORS_PER_BATCH`, create exactly one T2 batch with `valPool[vPtr .. vPtr+2]`. T2 batch always has `batchId = 0`.

7. Set `GIstate = T1nT2Bcreated`.

---

### 7.4 T1 Aggregation

**Submit:**
```solidity
function submitT1Aggregation(uint _GI, uint _batchId, bytes32 _aggregationCID) external
```
- Validates sender is assigned T1 aggregator for the batch.
- One submission per aggregator.
- Tallies votes: `t1Votes[_GI][_batchId][_aggregationCID]++`.

**Finalize:**
```solidity
function finalizeT1Aggregation(uint _GI) external onlyOwner
```
For each T1 batch, determines the winning CID by plurality (most votes):
```
For each aggregator in batch:
    if submitted:
        cid = t1SubmissionCID[...][aggregator]
        if t1Votes[...][cid] > maxVotes:
            maxVotes = t1Votes[...][cid]
            winningCID = cid
b.finalized = true
b.finalCID = winningCID
```
Reverts `TC_NoSubmissions` if no CID was submitted for a batch.

Sets `GIstate = T1AggregationDone`.

---

### 7.5 T2 Aggregation

Identical pattern to T1 but operates on `tier2Batches`. Only one batch exists (batchId = 0). Sets `GIstate = T2AggregationDone`.

---

## 8. Slashing Mechanism

### 8.1 `slashAuditors`

```solidity
function slashAuditors(uint _GI) external onlyOwner onlyCurrentGI(_GI)
```

State requirement: `T2AggregationDone`.

Current implementation is a **placeholder** — it only advances the state to `AuditorsSlashed`. The comment reads: "The Actual Slashing logic maybe implemented here." No actual calls to `dinvalidatorStakeContract.slash()` are made for auditors at this time.

### 8.2 `slashAggregators`

```solidity
function slashAggregators(uint _GI) external onlyOwner onlyCurrentGI(_GI)
```

State requirement: `AuditorsSlashed`.

**Algorithm:**

```
slashAmount = minStake

For each T1 batch:
  For each aggregator in batch:
    submitted = t1Submitted[GI][batchId][aggregator]
    submittedMatching = (submitted AND t1SubmissionCID[...] == b.finalCID)
    if NOT submitted OR NOT submittedMatching:
      dinvalidatorStakeContract.slash(aggregator, slashAmount)

For each T2 batch:
  Same logic using t2Submitted, t2SubmissionCID, b.finalCID
```

**Slash condition:** An aggregator is slashed if they either:
- Did not submit any CID, OR
- Submitted a CID that did not match the winning (plurality) CID.

**Slash amount:** Exactly `minStake` (1,000,000 raw units). This is a fixed, non-proportional penalty.

Sets `GIstate = AggregatorsSlashed`.

---

## 9. Tier-2 Score

```solidity
function setTier2Score(uint _GI, uint _score) external onlyOwner onlyCurrentGI(_GI)
function getTier2Score(uint _GI) external view returns (uint)
```

Records an off-chain computed performance score for the T2 aggregation result. Can be set during `T2AggregationDone` or `GenesisModelCreated` states. This is a metadata field — it does not affect slashing.

---

## 10. GI Termination

```solidity
function endGI(uint _GI) external onlyOwner onlyCurrentGI(_GI)
```

State requirement: `AggregatorsSlashed`. Sets `GIstate = GIended`.

After `endGI`, a new GI can be started via `startGI(_GI+1, newPassScore)`.

---

## 11. Shuffling (PRNG Details)

Two internal shuffle helpers mirror those in `DINTaskAuditor`:

| Function | Target | Entropy |
|----------|--------|---------|
| `_shuffleAddressArray` (storage) | Aggregator pool | `blockhash(block.number - 1)` |
| `_shuffleUintArray` (memory) | Model index pool | `block.timestamp + msg.sender` |

Both use Fisher-Yates algorithm. See `DINTaskAuditor` documentation and Security Considerations for PRNG weakness notes.

---

## 12. Events

| Event | Emitted When |
|-------|--------------|
| `DINValidatorRegistered(GI, validator)` | Aggregator registers |
| `Tier1BatchAuto(GI, batchId)` | T1 batch created |
| `Tier2BatchAuto(GI, batchId)` | T2 batch created |

---

## 13. Security Considerations

| Risk | Mitigation / Status |
|------|---------------------|
| Unauthorized state transitions | All owner functions guarded by `onlyOwner` |
| Wrong GI operations | `onlyCurrentGI` modifier on most functions |
| Weak PRNG for batch assignment | Known issue; use VRF in production |
| Auditor slashing not implemented | `slashAuditors()` is a placeholder only |
| Aggregator collusion (submit same wrong CID) | Plurality voting means 2-of-3 colluding aggregators win; no quorum threshold — design risk |
| No slash appeal mechanism | Slashed aggregators cannot challenge the decision on-chain |
| `minStake` fixed in code | Not configurable post-deployment without redeployment |

---

## 14. Interactions with Other Contracts

```
DINTaskCoordinator
  ├── reads  → DinValidatorStake.getStake()            [aggregator registration]
  ├── reads  → DinValidatorStake.isSlasherContract()   [coordinator/auditor slasher checks]
  ├── calls  → DinValidatorStake.slash()               [slashAggregators]
  ├── calls  → DINTaskAuditor.updatePassScore()        [startGI]
  ├── calls  → DINTaskAuditor.createAuditorsBatches()  [createAuditorsBatches]
  ├── calls  → DINTaskAuditor.setTestDataAssignedFlag() [setTestDataAssignedFlag]
  ├── calls  → DINTaskAuditor.finalizeEvaluation()     [closeLMsubmissionsEvaluation]
  └── reads  → DINTaskAuditor.approvedModelIndexes()   [autoCreateTier1AndTier2]
```

---

## 15. Known Limitations & Future Work

- `slashAuditors()` is a stub — audit-specific slashing logic is not implemented.
- Aggregator slashing is plurality-based: a 2-of-3 colluding majority wins without any cryptographic verification of the aggregated model.
- No on-chain reward distribution to aggregators — the T2 score is informational only.
- `minStake` is mutable state but there is no setter function, making it effectively constant post-deployment.
- No mechanism to recover from a stalled GI (e.g., if T1 never reaches submissions).
- T2 always produces exactly one batch; no fallback if insufficient aggregators remain after T1 assignment.
