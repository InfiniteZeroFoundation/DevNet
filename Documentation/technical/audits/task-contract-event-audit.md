# Task-contract event audit — DINTaskCoordinator & DINTaskAuditor

Conducted as part of the subgraph extension to task-level contracts
(`feat/din-indexer`). Follows the same format as the platform-contract audit
in `subgraph/docs/event-coverage-audit.md`.

> **Status update (2026-11-14).** All proposed additions in §4 have landed, plus
> the commit/reveal, test-data, dispute, seed-lock, reward, and S1/S2/S3
> governance events added by later contract work. The subgraph indexes them
> through the `DINTaskCoordinator` and `DINTaskAuditor` data source templates.
> Sections below are kept as the audit trail; each gap section records its
> resolution.

---

## §1 Scope

Two contracts deployed once per model by the model owner:

- `DINTaskCoordinator` — orchestrates the full GI lifecycle (aggregator/auditor
  registration, LMS, batch creation, T1/T2 aggregation, slashing, GI end)
- `DINTaskAuditor` — handles auditor registration, local model submission,
  eligibility voting, scoring, and auditor slashing

**Not proxied.** Both contracts are deployed fresh for each model; there is no
upgrade proxy. This has one consequence for the indexer: already-deployed
instances on `sepolia_op_devnet` will not emit the new events proposed in §4.
Dynamic data sources can only index newly deployed task contracts going forward.
State this explicitly in any dind or operator runbook.

---

## §2 Existing events (at audit time)

The tables below list only the events that existed when this audit was written.
For the full current event surface — including commit/reveal, test data,
disputes, seeds, rewards, and S1/S2/S3 governance — see §4, §4a, and
`subgraph/subgraph.yaml`.

### DINTaskCoordinator

| Event | Emitted by | Indexed fields | Notes |
|-------|-----------|---------------|-------|
| `DINValidatorRegistered(uint GI, address validator)` | `registerDINaggregator()` | `GI`, `validator` | Aggregator registration only; auditors use the auditor contract |
| `Tier1BatchAuto(uint GI, uint batchId)` | `autoCreateTier1AndTier2()` | `GI`, `batchId` | Emitted once per T1 batch created |
| `Tier2BatchAuto(uint GI, uint batchId)` | `autoCreateTier1AndTier2()` | `GI`, `batchId` | Emitted once for the single T2 batch |
| `AggregatorSlashed(uint GI, uint batchId, address aggregator, bytes32 reason, uint256 requested, uint256 actual)` | `slashAggregators()` | `GI`, `batchId`, `aggregator` | Covers both T1 and T2 slash loops |

### DINTaskAuditor

| Event | Emitted by | Indexed fields | Notes |
|-------|-----------|---------------|-------|
| `DINAuditorRegistered(uint GI, address auditor)` | `registerDINAuditor()` | `GI`, `auditor` | |
| `AuditorsBatchAuto(uint GI, uint batchId)` | `createAuditorsBatches()` | `GI`, `batchId` | Per-batch; one emit per batch created |
| `AuditorsBatchesCreated(uint GI, uint batchCount)` | `createAuditorsBatches()` | `GI` | Summary event after all batches created |
| `AuditScoreSubmitted(uint256 gi, uint batchId, address auditor, uint modelIndex, uint256 score)` | `setAuditScorenEligibility()` | `gi`, `batchId`, `auditor` | |
| `EligibilityVoted(uint256 gi, uint batchId, uint modelIndex, address auditor, bool vote)` | `setAuditScorenEligibility()` | `gi`, `batchId`, `modelIndex` | |
| `EligibilityFinalized(uint256 gi, uint batchId, uint modelIndex, bool eligible, uint totalVotes)` | `_tryFinalizeEligibility()` | `gi`, `batchId`, `modelIndex` | Fires when quorum is reached after each vote |
| `PassScoreUpdated(uint256 oldScore, uint256 newScore)` | `updatePassScore()` | none | Called by coordinator at `startGI` when score arg supplied |
| `AuditorSlashed(uint256 gi, uint batchId, address auditor, bytes32 reason, uint256 requested, uint256 actual)` | `slashAuditors()` | `gi`, `batchId`, `auditor` | |

---

## §3 Gap analysis

### §3.1 GI state machine — resolved

At audit time `GIstates` had 23 states and `DINTaskCoordinator` wrote `GIstate`
at 23 sites without emitting an event. `develop` now has **29 states**
(ordinals `0..28`, `GIended = 28`) and every transition goes through
`_setGIstate()`, which emits:

```solidity
event GIStateChanged(uint indexed GI, uint8 indexed newState);
```

The subgraph stores the current state on `GlobalIteration` and appends a
`GIStateTransition` row per change (`GI_STATES` in
`subgraph/src/taskCoordinator.ts` mirrors the enum, and
`Documentation/technical/contracts/DINShared.md §2.1` is the source of truth).

| Ordinal | State | Set by |
|---:|---|---|
| 0 | `AwaitingDINTaskAuditorToBeSet` | `constructor` |
| 1 | `AwaitingDINTaskCoordinatorAsSlasher` | `setDINTaskAuditorContract()` |
| 2 | `AwaitingDINTaskAuditorAsSlasher` | `setDINTaskCoordinatorAsSlasher()` |
| 3 | `AwaitingGenesisModel` | `setDINTaskAuditorAsSlasher()` |
| 4 | `GenesisModelCreated` | `setGenesisModelIpfsHash()` |
| 5 | `GIstarted` | `_startGI()` |
| 6 | `DINaggregatorsRegistrationStarted` | `startDINaggregatorsRegistration()` |
| 7 | `DINaggregatorsRegistrationClosed` | `closeDINaggregatorsRegistration()` |
| 8 | `DINauditorsRegistrationStarted` | `startDINauditorsRegistration()` |
| 9 | `DINauditorsRegistrationClosed` | `closeDINauditorsRegistration()` |
| 10 | `LMSstarted` | `startLMsubmissions()` |
| 11 | `LMSclosed` | `closeLMsubmissions()` |
| 12 | `AuditSeedLocked` | `lockAuditSeed()` |
| 13 | `AuditorsBatchesCreated` | `createAuditorsBatches()` |
| 14 | `AuditTestDataAssigned` | `setTestDataAssignedFlag()` |
| 15 | `LMSevaluationStarted` | `startLMsubmissionsEvaluation()` |
| 16 | `LMSevaluationRevealStarted` | `startLMsubmissionsEvaluationReveal()` |
| 17 | `LMSevaluationClosed` | `closeLMsubmissionsEvaluation()` |
| 18 | `AggSeedLocked` | `lockAggSeed()` |
| 19 | `T1nT2Bcreated` | `autoCreateTier1AndTier2()` |
| 20 | `T1AggregationStarted` | `startT1Aggregation()` |
| 21 | `T1AggregationRevealStarted` | `startT1AggregationReveal()` |
| 22 | `T1AggregationDone` | `finalizeT1Aggregation()` |
| 23 | `T2AggregationStarted` | `startT2Aggregation()` |
| 24 | `T2AggregationRevealStarted` | `startT2AggregationReveal()` |
| 25 | `T2AggregationDone` | `finalizeT2Aggregation()` |
| 26 | `AuditorsSlashed` | `slashAuditors()` |
| 27 | `AggregatorsSlashed` | `slashAggregators()` |
| 28 | `GIended` | `endGI()` |

### §3.2 Missing submission events — resolved

At audit time these submissions had no event. They now emit the events listed
in §4 and are indexed.

| Function | Contract | Impact at audit time |
|----------|---------|--------|
| `submitLocalModel()` | `DINTaskAuditor` | `lms.py ~line 62` iterates `getClientModels()` over RPC. Cannot be replaced with a GraphQL query without a `LocalModelSubmitted` event. |
| `submitT1Aggregation()` | `DINTaskCoordinator` | `aggregation.py ~lines 76, 95` iterates T1 batch submissions over RPC. No event means no indexer coverage. |
| `submitT2Aggregation()` | `DINTaskCoordinator` | `aggregation.py ~line 136` iterates T2 batch submissions over RPC. Same gap. |

### §3.3 Missing finalization events — resolved

At audit time `finalizeT1Aggregation()` iterates all T1 batches, tallies votes per CID, and
writes the majority CID to `b.finalCID` in storage — no event emitted.
`finalizeT2Aggregation()` does the same for the single T2 batch; its `b.finalCID`
is the **new global model CID** for the GI — the single most important value
produced by a completed iteration.

Without finalization events, the indexer would have to re-implement the
vote-majority tallying logic in AssemblyScript from the submission events alone.
That is complex, divergence-prone, and fragile against any future change to the
tally logic. The contract has already computed the winner; it should emit it.

**Resolution:** `T1BatchFinalized` and `T2Finalized` (plus the commit/reveal
events in §4.3/§4.5) now expose every winning CID directly.

---

## §4 Proposed additions — landed

All six additions were minimal — one declaration and one (or N, for
`GIStateChanged`) emit site per event. No storage changes, no new state. They
landed together and are indexed; later contract work extended the set with the
commit/reveal, test-data, dispute, seed-lock, reward, and governance events
listed in §4a.

### §4.1 GI state machine — catch-all event

```solidity
event GIStateChanged(uint indexed GI, uint8 indexed newState);
```

**Implementation:** replace every `GIstate = GIstates.X;` assignment in
`DINTaskCoordinator` with a call to an internal setter:

```solidity
function _setGIstate(GIstates newState) internal {
    GIstate = newState;
    emit GIStateChanged(GI, uint8(newState));
}
```

One declaration, one emit site, and it is impossible to miss a future
transition when new states are added. `newState` is indexed so consumers
(including `dind` P4-7.1) can topic-filter for a specific phase —
e.g. `newState == 16` (`T1AggregationStarted`) to queue aggregation jobs.

The schema maps `uint8` → a GraphQL enum mirroring `GIstates` from
`DINShared.sol`, so queries read as clearly as named events would.

### §4.2 Local model submission

```solidity
event LocalModelSubmitted(
    uint indexed GI,
    uint indexed modelIndex,
    address indexed client,
    bytes32 modelCID
);
```

Emit inside `DINTaskAuditor.submitLocalModel()` after the `lmSubmissions[_GI].push(...)`.
`modelIndex` is `lmSubmissions[_GI].length` before the push (already computed
as a local variable in the current code).

### §4.3 T1 and T2 aggregation submission

```solidity
event T1AggregationSubmitted(
    uint indexed GI,
    uint indexed batchId,
    address indexed aggregator,
    bytes32 cid
);

event T2AggregationSubmitted(
    uint indexed GI,
    uint indexed batchId,
    address indexed aggregator,
    bytes32 cid
);
```

Both in `DINTaskCoordinator`. `T2AggregationSubmitted.batchId` is always `0`
today (`TC_OnlyOneTier2Batch` enforces it) — kept for symmetry with T1 and
future extensibility.

### §4.4 T1 and T2 finalization

```solidity
event T1BatchFinalized(
    uint indexed GI,
    uint indexed batchId,
    bytes32 winningCID
);

event T2Finalized(
    uint indexed GI,
    bytes32 globalModelCID
);
```

`T1BatchFinalized` emits once per batch inside the `finalizeT1Aggregation()`
loop, immediately after `b.finalCID = winningCID`. `T2Finalized` emits once
inside `finalizeT2Aggregation()` — `globalModelCID` is the T2 winning CID,
i.e. the new global model for this GI.

---

### §4.5 Commit/reveal events (added later)

Commit-then-reveal was added to both auditor scoring and T1/T2 aggregation:

```solidity
event AuditScoreCommitted(uint indexed gi, uint indexed batchId, address indexed auditor, uint modelIndex, bytes32 commitHash);
event T1AggregationCommitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 commitHash);
event T2AggregationCommitted(uint indexed GI, uint indexed batchId, address indexed aggregator, bytes32 commitHash);
```

`T1AggregationSubmitted`/`T2AggregationSubmitted` are now the reveal step. The
subgraph links each revealed submission back to its commitment.

## §4a Other indexed mechanisms

| Area | Events | Entities |
|---|---|---|
| Auditor scoring | `AuditScoreSubmitted`, `AuditScoreCommitted`, `AuditorScoreDeviation` | `AuditScoreSubmission`, `AuditScoreCommitment`, `AuditorScoreDeviation` |
| Test data | `TestDataCommitmentStored`, `EncryptedTestDataKeysAssigned`, `TestDataDisputeOpened`, `TestDataDisputeUpheld`, `TestDataDisputeResolvedFalse`, `BatchPendingReassignment` | `TestDataCommitment`, `EncryptedTestDataKeys`, `TestDataDispute` |
| Seeds | `AuditSeedLocked`, `AuditSeedReanchored`, `AggSeedLocked`, `AggSeedReanchored`, `DisputeSeedLocked`, `DisputeSeedReanchored` | `SeedLock` |
| Disputes | `DisputeOpened`, `DisputeResolved`, `ReEvaluationAssigned`, `RecomputationSettled`, `DisputeBondClaimed`, `DisputeExpired` | `AggregationDispute`, `DisputeBondClaim` |
| Rewards | `RewardDeposited`, `RewardsSettled`, `RewardsClaimed`, `RewardSplitUpdated` | `RewardDeposit`, `RewardSettlement`, `RewardClaim`, `RewardSplit` |
| Governance | `S1SlashFractionBpsUpdated`, `S2SlashFractionBpsUpdated`, `S3DeviationThresholdUpdated`, `S3SlashingEnabledUpdated` | `TaskAuditorGovernance`, `TaskCoordinatorGovernance` |

---

## §5 RewardDeposited — resolved

`DINTaskAuditor` now has a real deposit flow and emits:

```solidity
event RewardDeposited(uint256 indexed gi, address indexed depositor, uint256 amount);
```

This is indexed as `RewardDeposit`, alongside `RewardsSettled`, `RewardsClaimed`,
and `RewardSplitUpdated` (see §4a).

---

## §6 Dynamic data source design note

Task contracts are factory-deployed — one `DINTaskCoordinator` + `DINTaskAuditor`
pair per model. The subgraph will use **The Graph data source templates**:

1. `DINModelRegistry` emits `ModelApproved` when a model is registered.
2. The `handleModelApproved` mapping handler reads `taskCoordinator` and
   `taskAuditor` addresses from the `DINModelRegistry` storage call (same bridge
   approach used in the platform-contract handlers).
3. The handler calls `DINTaskCoordinatorTemplate.create(taskCoordinatorAddress)`
   and `DINTaskAuditorTemplate.create(taskAuditorAddress)` to instantiate live
   indexing for that model's contracts.

Entity design and AssemblyScript handler implementation follow once this audit
and the proposed contract additions are reviewed and merged.
