# DINModelRegistry — Technical Documentation

> **File:** `hardhat/contracts/DINModelRegistry.sol`
> **Version:** v2 — Request / Approval Based
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.20`

---

## 1. Overview

`DINModelRegistry` is the **governed admission gateway** for AI models in the Decentralised Intelligence Network. It evolved from a simple storage contract into a DAO-controlled registry where every model and every manifest change must pass an explicit approval step before taking effect.

Core capabilities:

- **Two-phase model registration** — submit a request, DAO approves or rejects.
- **Two-phase manifest updates** — same request/approval flow.
- **Kill switch** — DAO can instantly disable any model.
- **Dynamic fee governance** — all four fee parameters are DAO-adjustable.
- **Transferable DAO admin** — admin role can be handed to a multisig or timelock.

---

## 2. Inline Interfaces

```solidity
interface IDinValidatorStake {
    function isSlasherContract(address slasherContract) external view returns (bool);
}

interface IOwnable {
    function owner() external view returns (address);
}
```

Used during registration request validation and approval-time revalidation.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `daoAdmin` | `address` | `public` | Deployer-set DAO representative. Transferable via `setDAOAdmin()`. |
| `dinValidatorStake` | `IDinValidatorStake` | `public` | Reference to the validator stake contract for slasher verification. |
| `openSourceFee` | `uint256` | `public` | ETH fee to register an open-source model. Default: `0.000001 ETH`. |
| `proprietaryFee` | `uint256` | `public` | ETH fee to register a proprietary model. Default: `0.00001 ETH`. |
| `openSourceUpdateFee` | `uint256` | `public` | ETH fee to request a manifest update for an open-source model. Default: `0.0000001 ETH`. |
| `proprietaryUpdateFee` | `uint256` | `public` | ETH fee to request a manifest update for a proprietary model. Default: `0.000001 ETH`. |
| `models` | `Model[]` | `private` | Append-only array of approved models. Index is the model ID. |
| `modelRequests` | `ModelRequest[]` | `public` | All registration requests (pending, approved, rejected). |
| `manifestRequests` | `ManifestUpdateRequest[]` | `public` | All manifest update requests. |
| `modelDisabled` | `mapping(uint256 => bool)` | `public` | Kill-switch flag per model ID. |
| `_modelIdByTaskCoordinator` | `mapping(address => uint256)` | `private` | Maps TaskCoordinator → `modelId + 1` (0 = unregistered). |
| `_modelIdByTaskAuditor` | `mapping(address => uint256)` | `private` | Maps TaskAuditor → `modelId + 1` (0 = unregistered). |

---

## 4. Data Structures

### `Model`

```solidity
struct Model {
    address owner;           // Model owner's wallet
    bool isOpenSource;       // Open-source vs proprietary flag
    bytes32 manifestCID;     // IPFS CID (bytes32 encoding) of the current manifest
    address taskCoordinator; // DINTaskCoordinator contract for this model
    address taskAuditor;     // DINTaskAuditor contract for this model
    uint256 createdAt;       // Block timestamp at approval
}
```

### `ModelRequest`

```solidity
struct ModelRequest {
    address requester;
    bool isOpenSource;
    bytes32 manifestCID;
    address taskCoordinator;
    address taskAuditor;
    uint256 feePaid;
    bool processed;   // true after approve or reject
    bool approved;    // true only if approved
    uint256 createdAt;
}
```

### `ManifestUpdateRequest`

```solidity
struct ManifestUpdateRequest {
    uint256 modelId;
    bytes32 newManifestCID;
    address requester;
    uint256 feePaid;
    bool processed;
    bool approved;
}
```

---

## 5. Custom Errors

| Error | Condition |
|-------|-----------|
| `NotDINDAOAdmin()` | Caller is not `daoAdmin` |
| `NotModelOwner()` | Caller does not own the referenced model |
| `InvalidModelId()` | Model ID is out of bounds |
| `InvalidRequestId()` | Request ID is out of bounds |
| `AlreadyProcessed()` | Request has already been approved or rejected |
| `InsufficientFee()` | `msg.value` is below the required fee |
| `TaskCoordinatorEqualsTaskAuditor()` | `taskCoordinator == taskAuditor` |
| `NotOwnerOfTaskCoordinator()` | Requester does not own the coordinator contract |
| `NotOwnerOfTaskAuditor()` | Requester does not own the auditor contract |
| `ModelIsDisabled(uint256 modelId)` | Model is currently disabled |
| `TaskCoordinatorAlreadyRegistered()` | Coordinator is already linked to another approved model |
| `TaskAuditorAlreadyRegistered()` | Auditor is already linked to another approved model |
| `ZeroAddress()` | `address(0)` passed where a valid address is required |
| `CoordinatorNoLongerSlasher()` | Coordinator lost its slasher status between request and approval |
| `AuditorNoLongerSlasher()` | Auditor lost its slasher status between request and approval |
| `CoordinatorOwnershipChanged()` | Coordinator ownership changed between request and approval |
| `AuditorOwnershipChanged()` | Auditor ownership changed between request and approval |

---

## 6. Events

### Registration Flow

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `ModelRegistrationRequested` | `uint256 indexed requestId`, `address indexed requester` | `requestModelRegistration()` succeeds |
| `ModelApproved` | `uint256 indexed requestId`, `uint256 indexed modelId` | `approveModel()` succeeds |
| `ModelRejected` | `uint256 indexed requestId` | `rejectModel()` succeeds |

### Manifest Update Flow

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `ManifestUpdateRequested` | `uint256 indexed requestId`, `uint256 indexed modelId` | `requestManifestUpdate()` succeeds |
| `ManifestUpdated` | `uint256 indexed requestId`, `uint256 indexed modelId`, `bytes32 newCID` | `approveManifestUpdate()` succeeds |
| `ManifestUpdateRejected` | `uint256 indexed requestId` | `rejectManifestUpdate()` succeeds |

### Kill Switch

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `ModelDisabled` | `uint256 indexed modelId` | `disableModel()` succeeds |
| `ModelEnabled` | `uint256 indexed modelId` | `enableModel()` succeeds |

### Fee Governance

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `OpenSourceFeeUpdated` | `uint256 newFee` | `setOpenSourceFee()` |
| `ProprietaryFeeUpdated` | `uint256 newFee` | `setProprietaryFee()` |
| `OpenSourceUpdateFeeUpdated` | `uint256 newFee` | `setOpenSourceUpdateFee()` |
| `ProprietaryUpdateFeeUpdated` | `uint256 newFee` | `setProprietaryUpdateFee()` |
| `FeesUpdated` | `uint256 openSourceFee`, `uint256 proprietaryFee`, `uint256 openSourceUpdateFee`, `uint256 proprietaryUpdateFee` | `setFees()` — atomic update |
| `FeesWithdrawn` | `address indexed to`, `uint256 amount` | `withdrawFees()` |

### DAO Administration

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `DAOAdminUpdated` | `address indexed oldAdmin`, `address indexed newAdmin` | `setDAOAdmin()` |

---

## 7. Access Control

```
daoAdmin
  ├── approveModel()
  ├── rejectModel()
  ├── approveManifestUpdate()
  ├── rejectManifestUpdate()
  ├── disableModel()
  ├── enableModel()
  ├── setOpenSourceFee()
  ├── setProprietaryFee()
  ├── setOpenSourceUpdateFee()
  ├── setProprietaryUpdateFee()
  ├── setFees()
  ├── withdrawFees()
  └── setDAOAdmin()

Model Owner (per-model — onlyModelOwner + notDisabled modifiers)
  └── requestManifestUpdate()   ← blocked if model is disabled

Any address (permissionless, fee-gated)
  └── requestModelRegistration()
```

---

## 8. Model Registration Flow

### 8.1 `requestModelRegistration`

```solidity
function requestModelRegistration(
    bytes32 manifestCID,
    address taskCoordinator,
    address taskAuditor,
    bool isOpenSource
) external payable returns (uint256 requestId)
```

**Validation (sequential):**

1. **Fee check:** `msg.value >= openSourceFee` (open-source) or `>= proprietaryFee` (proprietary) — revert `InsufficientFee`.
2. **Slasher check — Coordinator:** `dinValidatorStake.isSlasherContract(taskCoordinator)` must be `true`.
3. **Slasher check — Auditor:** same for `taskAuditor`.
4. **Distinctness:** `taskCoordinator != taskAuditor` — revert `TaskCoordinatorEqualsTaskAuditor`.
5. **Ownership — Coordinator:** `IOwnable(taskCoordinator).owner() == msg.sender` — revert `NotOwnerOfTaskCoordinator`.
6. **Ownership — Auditor:** same for `taskAuditor` — revert `NotOwnerOfTaskAuditor`.
7. **Write:** Push `ModelRequest` to `modelRequests[]`. `requestId = modelRequests.length` (before push).
8. **Emit** `ModelRegistrationRequested`.

> **Note:** The fee is held in the contract regardless of whether the request is approved or rejected.

---

### 8.2 `approveModel`

```solidity
function approveModel(uint256 requestId) external onlyDAOAdmin
```

**Algorithm:**

1. Bounds check `requestId` — revert `InvalidRequestId`.
2. `req.processed` must be `false` — revert `AlreadyProcessed`.
3. **Duplicate coordinator check:** `_modelIdByTaskCoordinator[req.taskCoordinator] == 0` — revert `TaskCoordinatorAlreadyRegistered`.
4. **Duplicate auditor check:** `_modelIdByTaskAuditor[req.taskAuditor] == 0` — revert `TaskAuditorAlreadyRegistered`.
5. **Revalidation — Coordinator slasher:** `dinValidatorStake.isSlasherContract(req.taskCoordinator)` — revert `CoordinatorNoLongerSlasher`.
6. **Revalidation — Auditor slasher:** same — revert `AuditorNoLongerSlasher`.
7. **Revalidation — Coordinator ownership:** `IOwnable(req.taskCoordinator).owner() == req.requester` — revert `CoordinatorOwnershipChanged`.
8. **Revalidation — Auditor ownership:** same — revert `AuditorOwnershipChanged`.
9. **Write model:** Push `Model` to `models[]`. Set `_modelIdByTaskCoordinator` and `_modelIdByTaskAuditor` to `modelId + 1`.
10. Mark `req.processed = true`, `req.approved = true`.
11. **Emit** `ModelApproved(requestId, modelId)`.

> **Why revalidate at approval?** Requests may sit pending for days or weeks. A coordinator/auditor could lose its slasher status or be transferred to a different owner in that window. Revalidating at approval time closes that gap.

---

### 8.3 `rejectModel`

```solidity
function rejectModel(uint256 requestId) external onlyDAOAdmin
```

Marks the request as processed and rejected. Fee is retained. Emits `ModelRejected`.

---

## 9. Manifest Update Flow

### 9.1 `requestManifestUpdate`

```solidity
function requestManifestUpdate(
    uint256 modelId,
    bytes32 newManifestCID
) external payable onlyModelOwner(modelId) notDisabled(modelId) returns (uint256 requestId)
```

- **`onlyModelOwner`** — caller must be the model's registered owner.
- **`notDisabled`** — reverts `ModelIsDisabled(modelId)` if the model is currently disabled.
- Fee: `openSourceUpdateFee` or `proprietaryUpdateFee` based on `models[modelId].isOpenSource`.
- Pushes a `ManifestUpdateRequest`. Emits `ManifestUpdateRequested`.

### 9.2 `approveManifestUpdate`

```solidity
function approveManifestUpdate(uint256 requestId) external onlyDAOAdmin
```

1. Bounds check, duplicate-processed check.
2. **Disabled check:** `modelDisabled[req.modelId]` must be `false` — revert `ModelIsDisabled`. Prevents approving a manifest update for a model that was disabled after the request was submitted.
3. Updates `models[req.modelId].manifestCID`. Emits `ManifestUpdated`.

### 9.3 `rejectManifestUpdate`

Marks processed/rejected, retains fee. Emits `ManifestUpdateRejected`.

---

## 10. Kill Switch

```solidity
function disableModel(uint256 modelId) external onlyDAOAdmin
function enableModel(uint256 modelId)  external onlyDAOAdmin
```

- Sets / clears `modelDisabled[modelId]`.
- `modelDisabled` is `public` — downstream contracts (`TaskCoordinator`, `TaskAuditor`) can read it directly: `modelRegistry.modelDisabled(modelId)`.
- Emits `ModelDisabled` / `ModelEnabled`.
- **Disabled ≠ Deleted.** History, ownership, and manifest are preserved for auditability.

| Scenario | Protection |
|----------|-----------|
| Malicious manifest discovered | Disable instantly |
| Compromised model owner key | Cut off model from participating |
| Buggy coordinator/auditor logic | Pause safely without redeployment |
| Ongoing attack | Stop further participation |

---

## 11. Fee Mechanism

| Parameter | Default | Applies To |
|-----------|---------|-----------|
| `openSourceFee` | `0.000001 ETH` | Open-source model registration |
| `proprietaryFee` | `0.00001 ETH` | Proprietary model registration |
| `openSourceUpdateFee` | `0.0000001 ETH` | Open-source manifest update requests |
| `proprietaryUpdateFee` | `0.000001 ETH` | Proprietary manifest update requests |

Fees accumulate in the contract balance. Only `daoAdmin` can withdraw via `withdrawFees()`.

**Individual setters** — for single-fee adjustments:
`setOpenSourceFee`, `setProprietaryFee`, `setOpenSourceUpdateFee`, `setProprietaryUpdateFee`

**Combined setter** — for atomic governance proposals:
```solidity
function setFees(
    uint256 _openSourceFee,
    uint256 _proprietaryFee,
    uint256 _openSourceUpdateFee,
    uint256 _proprietaryUpdateFee
) external onlyDAOAdmin
```
Emits `FeesUpdated` with all four values as a state snapshot.

---

## 12. Lookup Functions

| Function | Parameters | Returns | Description |
|----------|-----------|---------|-------------|
| `getModel` | `uint256 modelId` | `owner, isOpenSource, manifestCID, createdAt, taskCoordinator, taskAuditor` | Full approved model record |
| `totalModels` | — | `uint256` | Total number of approved models |
| `getModelIdByTaskCoordinator` | `address taskCoordinator` | `(bool exists, uint256 modelId)` | Reverse lookup: coordinator → model |
| `getModelIdByTaskAuditor` | `address taskAuditor` | `(bool exists, uint256 modelId)` | Reverse lookup: auditor → model |

**Offset decoding:** Stored value is `modelId + 1`. View functions subtract 1 before returning the 0-indexed model ID.

---

## 13. DAO Admin Transfer

```solidity
function setDAOAdmin(address newAdmin) external onlyDAOAdmin
```

Transfers the DAO admin role. Reverts `ZeroAddress()` if `newAdmin == address(0)`. Emits `DAOAdminUpdated(oldAdmin, newAdmin)`. This is the migration path for moving to a multisig or on-chain timelock without redeploying the registry.

---

## 14. Interactions with Other Contracts

```
DINModelRegistry
  ├── reads → DinValidatorStake.isSlasherContract()   [at request and approval]
  ├── reads → taskCoordinator.owner()                  [IOwnable, at request and approval]
  └── reads → taskAuditor.owner()                      [IOwnable, at request and approval]

Downstream (reads DINModelRegistry)
  ├── TaskCoordinator → modelRegistry.modelDisabled(modelId)
  └── TaskAuditor     → modelRegistry.modelDisabled(modelId)
```

---

## 15. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Arbitrary contracts registered as coordinators/auditors | `isSlasherContract()` checked at request time and revalidated at approval |
| Ownership transferred between request and approval | `IOwnable.owner()` revalidated inside `approveModel()` |
| Slasher status revoked between request and approval | `isSlasherContract()` revalidated inside `approveModel()` |
| Coordinator / auditor reused across models | `_modelIdByTaskCoordinator` / `_modelIdByTaskAuditor` uniqueness enforced at approval |
| Silent manifest change by model owner | Manifest updates require DAO approval |
| Malicious approved model | Kill switch (`disableModel`) provides instant remediation |
| Disabled model manifest still approved | `approveManifestUpdate` checks `modelDisabled` before writing |
| Fee spam on registration | Fee required at request time; retained on rejection |
| DAO admin key compromise | `setDAOAdmin` enables migration to multisig / timelock |

---

## 16. Known Limitations & Future Work

- `taskCoordinator` and `taskAuditor` addresses are permanent after approval — no mechanism to update them.
- Pending requests never expire — a stale request remains approvable indefinitely (a `uint256 expiresAt` field could address this).
- Single DAO admin — no multi-sig quorum or on-chain voting yet (use `setDAOAdmin` to migrate).
