# Daemon Event Schema — DIN Platform Contracts (P4-IDX1)

**Consumer:** `dind` — the DIN daemon (issue #21, P4-7.1)
**Authored by:** Robbert (P4-IDX1 deliverable)
**Status:** Design — feeds Santiago's P4-7.1 on-chain event listening engine

> **Status update (2026-11-14).** The subgraph now covers six platform
> contracts (the original four plus `DinFeeRouter` and `DinTreasury`) and the
> task contracts through data source templates. Task-level GI events are no
> longer out of scope: `GIStateChanged` carries every `GIstates` transition, and
> the commit/reveal, reward, test-data, dispute, seed, and governance events
> listed in `Documentation/technical/audits/task-contract-event-audit.md` are
> indexed. The "PENDING" notes in §2 and the "out of scope" wording in §3.1
> describe the original design cut, not the current surface.

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
    // isOpenSource / fee are not in the event; the indexer fills them from
    // the registration request storage (audit §6.1 was not landed)
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
    // requester is not in the event; the indexer fills it from storage
    // (audit §6.2 was not landed)
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

// Fee sweeps: FeeRouterUpdated(address indexed feeRouter)
//             FeesSweptToRouter(uint256 amount)
// Treasury outflows are now emitted by DinTreasury:
//   EthReceived(address indexed from, uint256 amount)
//   EthWithdrawn(address indexed to, uint256 amount)
//   ERC20Withdrawn(address indexed token, address indexed to, uint256 amount)
```

---

## 3. Coverage gaps

### 3.1 Task-level GI events — now indexed

At design time these events did not exist on the four platform contracts and
task-level contracts were out of scope. Both changed:

- `DINTaskCoordinator` now emits `GIStateChanged(uint indexed GI, uint8 indexed newState)`
  for every `GIstates` transition (29 states, `GIended = 28`).
- The subgraph indexes `DINTaskCoordinator` and `DINTaskAuditor` through data
  source templates, so the daemon can filter on the task-contract addresses it
  discovers from `DINModelRegistry.ModelApproved`.

The daemon still needs to map the numeric state to the lifecycle actions below.

| `GIstates` state | Daemon action |
|---|---|
| `DINaggregatorsRegistrationStarted` (6) | Queue aggregator registration job |
| `DINauditorsRegistrationStarted` (8) | Queue auditor registration job |
| `LMSstarted` (10) | Queue local model submission job |
| `AuditorsBatchesCreated` (13) | Trigger test data fetch for assigned auditor batch |
| `AuditTestDataAssigned` (14) | Confirm test-data assignment |
| `LMSevaluationStarted` (15) | Queue commit-phase audit scoring job |
| `LMSevaluationRevealStarted` (16) | Queue reveal-phase audit scoring job |
| `T1AggregationStarted` (20) | Queue T1 aggregation commit job |
| `T1AggregationRevealStarted` (21) | Queue T1 aggregation reveal job |
| `T2AggregationStarted` (23) | Queue T2 aggregation commit job |
| `T2AggregationRevealStarted` (24) | Queue T2 aggregation reveal job |
| `GIended` (28) | Finalize round, archive local model artifacts |

Dedicated events (`T1AggregationSubmitted`, `T2Finalized`, `LocalModelSubmitted`,
etc.) carry the payloads; `GIStateChanged` is the trigger signal.

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

### 3.3 `ETHTreasuryWithdrawn` — superseded

`DinCoordinator` no longer withdraws fees directly; it sweeps them to
`DinFeeRouter` (`FeesSweptToRouter`). Treasury outflows are emitted by
`DinTreasury` as `EthWithdrawn`/`ERC20Withdrawn`, so the daemon can observe them
without a new coordinator event.

---

## 4. Subscription mechanics for Santiago (P4-7.1)

The daemon can subscribe to events by polling the JSON-RPC `eth_getLogs`
endpoint with the contract address and topic filters, or by using a WebSocket
connection (`eth_subscribe` with `logs` filter).

Recommended approach for `dind` v1:
- **WebSocket `eth_subscribe` logs filter** per contract address — one
  subscription per contract, six total. Lower latency than polling and
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
| P4-IDX2 (now) | `dincli` | Replace the `dinrep.py` RPC loop with a GraphQL query to the subgraph |
| P4-IDX3 | `dincli` test suite | Wire call site replacement into existing tests |
| P4-1.2 (SDK extraction) | `dincli/sdk/` | Event subscription helpers extracted from CLI internals |
| P4-7.1 | `dind` | Santiago implements listening engine using this schema as spec |
