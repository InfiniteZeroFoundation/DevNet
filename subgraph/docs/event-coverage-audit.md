# Event Coverage Audit — DIN Platform Contracts

**Scope:** The four platform contracts indexed in P4-IDX1:
`DINModelRegistry`, `DinValidatorStake`, `DinCoordinator`, `DinToken`.

**Principle:** Every meaningful state transition must be reconstructable
from events alone. Where reconstruction requires a storage call, a minimal
event addition is preferable to a call handler — call handlers are not
supported on all Graph node backends and degrade indexing performance.

**Outcome:** Two confirmed event additions (coordinated with Umer, 2026-07-09)
to be landed as one small PR after this audit is reviewed. No storage-layout
changes. All four contracts are behind proxies (PR #13), so re-deploying
locally with updated event signatures is low-friction.

---

## 1. DINModelRegistry

### 1.1 Events audited

| Event | Indexed fields | Non-indexed fields | Assessment |
|---|---|---|---|
| `ModelRegistrationRequested` | `requestId`, `requester` | — | **Gap — see §3.1** |
| `ModelApproved` | `requestId`, `modelId` | — | Sufficient |
| `ModelRejected` | `requestId` | — | Sufficient |
| `ManifestUpdateRequested` | `requestId`, `modelId` | — | **Gap — see §3.2** |
| `ManifestUpdated` | `requestId`, `modelId` | `newCID` | Sufficient |
| `ManifestUpdateRejected` | `requestId` | — | Sufficient |
| `ModelDisabled` | `modelId` | — | Sufficient |
| `ModelEnabled` | `modelId` | — | Sufficient |
| `OpenSourceFeeUpdated` | — | `newFee` | Sufficient for timeline; no old-value field but this is acceptable |
| `ProprietaryFeeUpdated` | — | `newFee` | Same as above |
| `OpenSourceUpdateFeeUpdated` | — | `newFee` | Same as above |
| `ProprietaryUpdateFeeUpdated` | — | `newFee` | Same as above |
| `FeesUpdated` | — | `openSourceFee`, `proprietaryFee`, `openSourceUpdateFee`, `proprietaryUpdateFee` | Sufficient for atomic governance proposals |
| `FeesWithdrawn` | `to` | `amount` | Sufficient |
| `DAOAdminUpdated` | `oldAdmin`, `newAdmin` | — | Sufficient |

### 1.2 Missing transitions

**No event on `ModelRequest` task-contract addresses.** `ModelRegistrationRequested`
does not include `taskCoordinator` or `taskAuditor`. These can be recovered from the
`ModelApproved` path via the on-chain `getModel()` view, but that requires a call at
index time. The proposed addition in §3.1 does not cover these fields — they are an
additional gap. For v1 the indexer will query them via the `ModelApproved` handler
(the contracts are local-only so a call in the mapping is currently acceptable as a
one-time lookup on approval, not on every request). Flagged as a follow-up candidate
for a future event extension.

---

## 2. DinValidatorStake

### 2.1 Events audited

| Event | Indexed fields | Non-indexed fields | Assessment |
|---|---|---|---|
| `ValidatorStaked` | `validator` | `amount` | Sufficient |
| `ValidatorSlashed` | `validator`, `reason`, `slasher` | `amount` | Sufficient — all key query fields indexed |
| `ValidatorUnstakeRequested` | `validator` | `amount`, `withdrawAvailableAt` | Sufficient |
| `ValidatorWithdrawalClaimed` | `validator` | `amount` | Sufficient |
| `ValidatorBlacklisted` | `validator` | — | Sufficient |
| `ValidatorUnblacklisted` | `validator` | — | Sufficient |
| `SlasherContractAdded` | `slasher` | — | **Signature conflict — see §4** |
| `SlasherContractRemoved` | `slasher` | — | **Signature conflict — see §4** |

### 2.2 Missing transitions

**No `ValidatorJailed` event.** `ValidatorInfo` carries a `jailedUntil` timestamp and
the `_syncValidatorStatus` helper transitions validators into `Jailed` status when
`jailedUntil > block.timestamp`, but no function in the current contract sets
`jailedUntil` or emits a jailing event. The Jailed status path is currently dead code.
No action required for the indexer now; flagged for the slashing/dispute spec (P3-4.x)
— when a jailing mechanism is added, it must emit a `ValidatorJailed` event with the
`jailedUntil` timestamp for the indexer to reconstruct status correctly.

**Validator status derivable from existing events.** Current live status transitions
(None → Active → Exiting → Active, Blacklisted, Unblacklisted) are fully reconstructable
from `ValidatorStaked`, `ValidatorUnstakeRequested`, `ValidatorWithdrawalClaimed`,
`ValidatorBlacklisted`, and `ValidatorUnblacklisted`. No additional event needed for
the current status machine.

---

## 3. DinCoordinator

### 3.1 Events audited

| Event | Indexed fields | Non-indexed fields | Assessment |
|---|---|---|---|
| `EthDepositAndDINminted` | `user` | `ethAmount`, `mintAmount` | Sufficient |
| `SlasherContractAdded` | `slasher` | — | **Signature conflict — see §4** |
| `SlasherContractRemoved` | `slasher` | — | **Signature conflict — see §4** |
| `ValidatorStakeContractUpdated` | `validatorStakeContract` | — | Sufficient |
| `DinPerEthUpdated` | — | `newRate` | Sufficient; old rate omitted but can be derived from the previous snapshot entity |

### 3.2 Missing transitions

**`withdraw()` emits no event.** The owner ETH withdrawal function transfers the
coordinator's entire ETH balance with no event. This makes treasury outflow invisible
to the indexer.

**Proposed addition:** `ETHTreasuryWithdrawn(address indexed to, uint256 amount)`
emitted at the end of `withdraw()`. This is a pure observatory addition — one event,
one line. See §3.3.

---

## 4. DinToken

### 4.1 Events audited

| Event | Indexed fields | Non-indexed fields | Assessment |
|---|---|---|---|
| `TokensMinted` | `to` | `amount` | Sufficient |
| `Transfer` (ERC20 inherited) | `from`, `to` | `value` | Sufficient — standard |
| `Approval` (ERC20 inherited) | `owner`, `spender` | `value` | Sufficient — standard |

No gaps identified.

---

## 5. Cross-contract issue: SlasherContractAdded / SlasherContractRemoved

Both `DinCoordinator` and `DinValidatorStake` emit events with **identical signatures**:

```
event SlasherContractAdded(address indexed slasher)
event SlasherContractRemoved(address indexed slasher)
```

This is intentional at the Solidity level — `DinCoordinator.addSlasherContract`
forwards the call to `DinValidatorStake`, so both contracts emit the same event for
the same action.

**Indexer implication:** If both events are processed without tracking the source
contract address, a single slasher add/remove operation creates two identical entity
records and slasher counts become inflated.

**Resolution (schema-level, no contract change needed):** The subgraph data source
for each contract processes its own event; the `SlasherRegistration` entity carries a
`sourceContract` field (set to the emitting contract's address in the mapping handler).
`DinCoordinator`-sourced and `DinValidatorStake`-sourced events are therefore kept
as distinct records. The canonical slasher set is derived only from
`DinValidatorStake` events, since that contract owns the actual `slasherContracts`
mapping. `DinCoordinator` events are recorded for audit trail completeness only.

---

## 6. Proposed event additions

The following two additions were confirmed by Umer (2026-07-09, issue #24). All
other gaps noted in this document are either handled at the schema level (§5) or
deferred to future work.

### 6.1 `DINModelRegistry.ModelRegistrationRequested`

**Current:**
```solidity
event ModelRegistrationRequested(
    uint256 indexed requestId,
    address indexed requester
);
```

**Proposed:**
```solidity
event ModelRegistrationRequested(
    uint256 indexed requestId,
    address indexed requester,
    bool    isOpenSource,
    uint256 fee
);
```

**Why:** Without `isOpenSource`, the indexer cannot distinguish open-source from
proprietary pending requests without a storage call. Without `fee`, the indexer
cannot surface fee amounts for pending-request dashboards. Both fields are already
in storage (`modelRequests[requestId].isOpenSource` / `.feePaid`) — emitting them
costs one additional log word each.

### 6.2 `DINModelRegistry.ManifestUpdateRequested`

**Current:**
```solidity
event ManifestUpdateRequested(
    uint256 indexed requestId,
    uint256 indexed modelId
);
```

**Proposed:**
```solidity
event ManifestUpdateRequested(
    uint256 indexed requestId,
    uint256 indexed modelId,
    address indexed requester
);
```

**Why:** Without `requester`, the indexer cannot attribute a pending manifest update
to its submitter. The requester address is already available as `msg.sender` at emit
time — adding it costs nothing beyond the extra log topic slot.

### 6.3 `DinCoordinator.ETHTreasuryWithdrawn` (new event)

**Proposed addition to `withdraw()`:**
```solidity
event ETHTreasuryWithdrawn(address indexed to, uint256 amount);
```

**Why:** The coordinator's `withdraw()` function transfers the full ETH balance to
the owner with no trace. For treasury governance and audit purposes, every outflow
should be observable on-chain. This addition is independent of the §6.1/6.2 changes
and can be batched into the same PR.

---

## 7. Daemon event schema (P4-7.1 feed)

The following platform-contract events are the minimum the `dind` daemon (issue #21)
needs to subscribe to for reactive job scheduling. Coverage gaps are noted.

| Event | Contract | dind use | Gap |
|---|---|---|---|
| `ModelRegistrationRequested` | DINModelRegistry | Notify DAO admin of new pending request | After §6.1 addition: adequate |
| `ModelApproved` | DINModelRegistry | Trigger model-owner onboarding flow | Adequate |
| `ModelRejected` | DINModelRegistry | Notify model owner | Adequate |
| `ManifestUpdateRequested` | DINModelRegistry | Notify DAO admin | After §6.2 addition: adequate |
| `ManifestUpdated` | DINModelRegistry | Trigger manifest refresh in local cache | Adequate |
| `ValidatorStaked` | DinValidatorStake | Update local validator-eligibility cache | Adequate |
| `ValidatorSlashed` | DinValidatorStake | Log slash for local validator operator | Adequate |
| `ValidatorBlacklisted` | DinValidatorStake | Halt local validator process immediately | Adequate |
| `DinPerEthUpdated` | DinCoordinator | Update local exchange-rate cache | Adequate — old rate derivable from prior snapshot |
| `DAOAdminUpdated` | DINModelRegistry | Alert operator of governance-key rotation | Adequate |

**Events not yet needed by dind v1** (task-contract GI events): not in scope here.
These belong in the P4-IDX3 handoff notes once platform-contract indexing is stable.
