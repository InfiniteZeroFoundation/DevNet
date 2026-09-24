# Daemon Event Schema — DIN Platform Contracts (P4-IDX1)

**Consumer:** `dind` — the DIN daemon (issue #21, P4-7.1)
**Authored by:** Robbert (P4-IDX1 deliverable)
**Status:** Design — feeds Santiago's P4-7.1 on-chain event listening engine

---

## Purpose

This document defines which platform-contract events `dind` must subscribe to,
what each event means for the daemon's job queue, and where current event
coverage is insufficient. It is the handoff from the indexer design (P4-IDX1)
to the daemon implementation (P4-7.1).

The indexer subgraph and the daemon share the same event surface. The subgraph
indexes events for historical queries and pagination; the daemon subscribes to
the same events in real time to trigger job execution without manual CLI
invocation.

---

## 1. Subscription priority

Events are grouped by how immediately the daemon must react.

### 1.1 Immediate — daemon must act within the same block or next block

| Event | Contract | Trigger | Daemon action |
|---|---|---|---|
| `ValidatorBlacklisted(address validator)` | DinValidatorStake | Validator address matches local operator | **Halt all active tasks immediately.** Stop any in-flight LMS, aggregation, or audit jobs. Alert operator via structured log at CRITICAL level. |
| `ModelDisabled(uint256 modelId)` | DINModelRegistry | modelId is one the local operator runs | Abort any in-flight work for that model. Remove model from active-participation list. Alert operator. |

### 1.2 High-priority — daemon should react within a few blocks

| Event | Contract | Trigger | Daemon action |
|---|---|---|---|
| `ValidatorSlashed(address validator, uint256 amount, bytes32 reason, address slasher)` | DinValidatorStake | Validator address matches local operator | Log slash with amount and reason. Recalculate active stake. If stake falls below `MIN_STAKE`, suspend new task registration until stake is topped up. |
| `ModelApproved(uint256 requestId, uint256 modelId)` | DINModelRegistry | requester matches local operator | Model registration confirmed. Cache the new modelId locally; the operator can now run `dincli model-owner gi start`. In future daemon automation, this triggers the GI-start workflow. |
| `ManifestUpdated(uint256 requestId, uint256 modelId, bytes32 newCID)` | DINModelRegistry | modelId is one the local operator participates in | Invalidate local manifest cache for that modelId. Re-fetch manifest from IPFS at the new CID before the next task action. |
| `ValidatorUnblacklisted(address validator)` | DinValidatorStake | Validator address matches local operator | Restore participation eligibility. Log at INFO level; do not auto-resume — operator must explicitly re-register for active tasks. |

### 1.3 Informational — daemon should record and expose via `/health` or status API

| Event | Contract | Notes |
|---|---|---|
| `ModelRegistrationRequested(uint256 requestId, address requester)` | DINModelRegistry | Relevant to DAO admin operators: new request pending review. Notify via log. |
| `ManifestUpdateRequested(uint256 requestId, uint256 modelId)` | DINModelRegistry | Same — DAO admin operators should be alerted. |
| `ModelRejected(uint256 requestId)` | DINModelRegistry | Relevant if local operator was the requester. |
| `ManifestUpdateRejected(uint256 requestId)` | DINModelRegistry | Same. |
| `ModelEnabled(uint256 modelId)` | DINModelRegistry | Model re-enabled after a kill-switch. Operator may choose to resume participation. |
| `ValidatorStaked(address validator, uint256 amount)` | DinValidatorStake | Useful for dashboard: record in local stake history. |
| `ValidatorUnstakeRequested(address validator, uint256 amount, uint64 withdrawAvailableAt)` | DinValidatorStake | Record in local unstake tracker. Daemon can surface `withdrawAvailableAt` countdown in `/health`. |
| `ValidatorWithdrawalClaimed(address validator, uint256 amount)` | DinValidatorStake | Record completion of withdrawal in local history. |
| `DinPerEthUpdated(uint256 newRate)` | DinCoordinator | Update local exchange-rate cache. Relevant for cost estimation in future reward projections. |
| `DAOAdminUpdated(address oldAdmin, address newAdmin)` | DINModelRegistry | Alert operator of governance-key rotation. Log at WARN level. |
| `EthDepositAndDINminted(address user, uint256 ethAmount, uint256 dinAmount)` | DinCoordinator | Relevant only if user matches local operator wallet. Record in local token history. |

---

## 2. Event payload reference

Full field inventory for events the daemon consumes. Includes current field
set and pending additions from the event-coverage audit.

### DINModelRegistry

```
ModelRegistrationRequested(
    uint256 indexed requestId,
    address indexed requester
    // PENDING: bool isOpenSource     (audit §6.1)
    // PENDING: uint256 fee           (audit §6.1)
)

ModelApproved(
    uint256 indexed requestId,
    uint256 indexed modelId
)

ModelRejected(
    uint256 indexed requestId
)

ManifestUpdateRequested(
    uint256 indexed requestId,
    uint256 indexed modelId
    // PENDING: address indexed requester  (audit §6.2)
)

ManifestUpdated(
    uint256 indexed requestId,
    uint256 indexed modelId,
    bytes32 newCID
)

ManifestUpdateRejected(
    uint256 indexed requestId
)

ModelDisabled(uint256 indexed modelId)
ModelEnabled(uint256 indexed modelId)

DAOAdminUpdated(
    address indexed oldAdmin,
    address indexed newAdmin
)
```

### DinValidatorStake

```
ValidatorStaked(
    address indexed validator,
    uint256 amount
)

ValidatorSlashed(
    address indexed validator,
    uint256 amount,
    bytes32 indexed reason,
    address indexed slasher
)

ValidatorUnstakeRequested(
    address indexed validator,
    uint256 amount,
    uint64 withdrawAvailableAt
)

ValidatorWithdrawalClaimed(
    address indexed validator,
    uint256 amount
)

ValidatorBlacklisted(address indexed validator)
ValidatorUnblacklisted(address indexed validator)
```

### DinCoordinator

```
EthDepositAndDINminted(
    address indexed user,
    uint256 ethAmount,
    uint256 mintAmount
)

DinPerEthUpdated(uint256 newRate)

ValidatorStakeContractUpdated(address indexed validatorStakeContract)

// PENDING: ETHTreasuryWithdrawn(address indexed to, uint256 amount)
//          (audit §6.3 — not yet emitted by withdraw())
```

---

## 3. Coverage gaps

### 3.1 Task-level GI events — out of scope for platform subgraph

P4-7.1 notes that the daemon must "at minimum wire: `T1AggregationStarted` →
queue aggregation job." None of the GI-lifecycle events exist on the four
platform contracts. They live on the task-level contracts `DINTaskCoordinator`
and `DINTaskAuditor`, which are out of scope for this subgraph (P5+).

Events the daemon needs from task-level contracts once those are indexed:

| Event | Contract | Daemon action |
|---|---|---|
| `DINaggregatorsRegistrationStarted` | DINTaskCoordinator | Queue aggregator registration job |
| `DINauditorsRegistrationStarted` | DINTaskCoordinator | Queue auditor registration job |
| `LMSstarted` | DINTaskCoordinator | Queue local model submission job |
| `AuditorsBatchesCreated` | DINTaskCoordinator | Trigger test data fetch for assigned auditor batch |
| `LMSevaluationStarted` | DINTaskCoordinator | Queue audit scoring job |
| `T1AggregationStarted` | DINTaskCoordinator | Queue T1 aggregation job (explicitly called out in P4-7.1) |
| `T2AggregationStarted` | DINTaskCoordinator | Queue T2 aggregation job |
| `GIended` | DINTaskCoordinator | Finalize round, archive local model artifacts |

These events do not exist in the task contracts under these names today — the
`GIstates` enum drives state transitions but the state-change itself is not
emitted as an event with an indexed GI number. When task-level indexing is
designed (P5+), each `GIstate` transition should emit a dedicated event with
`uint256 indexed modelId` and `uint256 indexed gi` so the daemon can filter
by model and iteration without scanning all events.

### 3.2 `ValidatorJailed` — dead code path

`DinValidatorStake` has a `Jailed` status and a `jailedUntil` timestamp but no
function that sets `jailedUntil` and no `ValidatorJailed` event. When the
slashing/dispute spec (P3-4.x) lands a jailing mechanism, it must emit:

```
ValidatorJailed(
    address indexed validator,
    uint64 jailedUntil
)
```

Without this event the daemon cannot react to a jailing in real time — it
would only discover the status change on the next stake-related event for that
validator.

### 3.3 `ETHTreasuryWithdrawn` — missing

`DinCoordinator.withdraw()` emits no event. The daemon has no way to observe
ETH treasury outflows. Proposed addition documented in audit §6.3.

---

## 4. Subscription mechanics for Santiago (P4-7.1)

The daemon can subscribe to events by polling the JSON-RPC `eth_getLogs`
endpoint with the contract address and topic filters, or by using a WebSocket
connection (`eth_subscribe` with `logs` filter).

Recommended approach for `dind` v1:
- **WebSocket `eth_subscribe` logs filter** per contract address — one
  subscription per contract, four total. Lower latency than polling and
  avoids block re-org edge cases that polling must handle explicitly.
- Maintain a local `lastProcessedBlock` per contract in the daemon's
  persistent state store (SQLite or JSON per P4-1.1 choice) so subscriptions
  can be replayed from the correct block on daemon restart.
- Filter by `address` + `topics[0]` (event selector). The Graph node itself
  uses the same mechanism internally.

The indexer subgraph handles historical state (indexer as the query layer);
the daemon handles real-time reaction (websocket subscriptions as the trigger
layer). The two paths are complementary — the daemon does not need to re-index
historical events, only respond to new ones.

---

## 5. Integration order

Per Umer (2026-07-09): dincli first, then SDK, then daemon — in that order.

| Phase | Consumer | Integration point |
|---|---|---|
| P4-IDX2 (now) | `dincli` | Replace `dindao.py` RPC loop with GraphQL query to subgraph |
| P4-IDX3 | `dincli` test suite | Wire call site replacement into existing tests |
| P4-1.2 (SDK extraction) | `dincli/sdk/` | Event subscription helpers extracted from CLI internals |
| P4-7.1 | `dind` | Santiago implements listening engine using this schema as spec |
