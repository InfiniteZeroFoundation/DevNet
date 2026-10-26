# Task-contract event audit — DINTaskCoordinator & DINTaskAuditor

Conducted as part of the subgraph extension to task-level contracts
(`feat/din-indexer`). Follows the same format as the platform-contract audit
in `subgraph/docs/event-coverage-audit.md`.

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

## §2 Existing events

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

### §3.1 Silent GI state machine

`GIstates` (defined in `DINShared.sol`) has 23 states. `DINTaskCoordinator`
writes to `GIstate` at 23 sites — the constructor, the four pre-GI setup steps,
and every phase-transition function — and **none of them emit an event**. The
full list of silent write sites:

| Site | Transition |
|------|-----------|
| `constructor` | → `AwaitingDINTaskAuditorToBeSet` |
| `setDINTaskAuditorContract()` | → `AwaitingDINTaskCoordinatorAsSlasher` |
| `setDINTaskCoordinatorAsSlasher()` | → `AwaitingDINTaskAuditorAsSlasher` |
| `setDINTaskAuditorAsSlasher()` | → `AwaitingGenesisModel` |
| `setGenesisModelIpfsHash()` | → `GenesisModelCreated` |
| `_startGI()` | → `GIstarted` |
| `startDINaggregatorsRegistration()` | → `DINaggregatorsRegistrationStarted` |
| `closeDINaggregatorsRegistration()` | → `DINaggregatorsRegistrationClosed` |
| `startDINauditorsRegistration()` | → `DINauditorsRegistrationStarted` |
| `closeDINauditorsRegistration()` | → `DINauditorsRegistrationClosed` |
| `startLMsubmissions()` | → `LMSstarted` |
| `closeLMsubmissions()` | → `LMSclosed` |
| `createAuditorsBatches()` | → `AuditorsBatchesCreated` |
| `startLMsubmissionsEvaluation()` | → `LMSevaluationStarted` |
| `closeLMsubmissionsEvaluation()` | → `LMSevaluationClosed` |
| `autoCreateTier1AndTier2()` | → `T1nT2Bcreated` |
| `startT1Aggregation()` | → `T1AggregationStarted` |
| `finalizeT1Aggregation()` | → `T1AggregationDone` |
| `startT2Aggregation()` | → `T2AggregationStarted` |
| `finalizeT2Aggregation()` | → `T2AggregationDone` |
| `slashAuditors()` | → `AuditorsSlashed` |
| `slashAggregators()` | → `AggregatorsSlashed` |
| `endGI()` | → `GIended` |

The indexer cannot track which phase a model is currently in without a storage
call per block — defeating the purpose of event-driven indexing.

### §3.2 Missing submission events

| Function | Contract | Impact |
|----------|---------|--------|
| `submitLocalModel()` | `DINTaskAuditor` | `lms.py ~line 62` iterates `getClientModels()` over RPC. Cannot be replaced with a GraphQL query without a `LocalModelSubmitted` event. |
| `submitT1Aggregation()` | `DINTaskCoordinator` | `aggregation.py ~lines 76, 95` iterates T1 batch submissions over RPC. No event means no indexer coverage. |
| `submitT2Aggregation()` | `DINTaskCoordinator` | `aggregation.py ~line 136` iterates T2 batch submissions over RPC. Same gap. |

### §3.3 Missing finalization events

`finalizeT1Aggregation()` iterates all T1 batches, tallies votes per CID, and
writes the majority CID to `b.finalCID` in storage — no event emitted.
`finalizeT2Aggregation()` does the same for the single T2 batch; its `b.finalCID`
is the **new global model CID** for the GI — the single most important value
produced by a completed iteration.

Without finalization events, the indexer would have to re-implement the
vote-majority tallying logic in AssemblyScript from the submission events alone.
That is complex, divergence-prone, and fragile against any future change to the
tally logic. The contract has already computed the winner; it should emit it.

---

## §4 Proposed additions

All six additions are minimal — one declaration and one (or N, for
`GIStateChanged`) emit site per event. No storage changes, no new state. To be
landed as one small reviewed PR before handler implementation begins.

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

## §5 Dead code — RewardDeposited

`DINTaskAuditor` declares:

```solidity
event RewardDeposited(address indexed modelOwner, uint256 amount);
```

No `depositRewards` function exists anywhere in the contract. The event is
never emitted. **Proposal:** remove in the same PR as the event additions above,
unless P3-5.1–5.3 (fee routing / reward distribution) introduces a real deposit
flow — that work should decide whether the event gets an emitter or is deleted.
Do not add an emitter here without the corresponding P3 design.

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
