# DINModelRegistry — Technical Documentation

> **File:** `hardhat/contracts/DINModelRegistry.sol`
> **Version:** v2 — Request / Approval Based (upgradeable)
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.28`
> **Deployment:** once per network behind an OpenZeppelin Transparent Proxy

---

## 1. Overview

`DINModelRegistry` is the **governed admission gateway** for AI models in the Decentralised Intelligence Network. It evolved from a simple storage contract into a DAO-controlled registry where every model and every manifest change must pass an explicit approval step before taking effect.

The admin role is the OpenZeppelin `OwnableUpgradeable` owner, set to the deployer in `initialize`. The pre-proxy `daoAdmin` ABI surface is preserved through two compatibility shims (`daoAdmin()` view and `setDAOAdmin()`) so existing dincli tooling keeps working — see [§14](#14-dao-admin--compatibility-shims).

Core capabilities:

- **Two-phase model registration** — submit a request, DAO approves or rejects.
- **Two-phase manifest updates** — same request/approval flow.
- **Kill switch** — DAO can instantly disable any model.
- **Dynamic fee governance** — all four fee parameters are DAO-adjustable.
- **Transferable DAO admin** — the owner role can be handed to a multisig or timelock (`setDAOAdmin` / `transferOwnership`).
- **Upgradeable** — logic can be replaced behind the proxy while all requests, models, and fees persist (see [§8](#8-initialization-ownership--upgradeability)).

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
| `dinValidatorStake` | `IDinValidatorStake` | `public` | Reference to the `DinValidatorStake` proxy for slasher verification. Set in `initialize`. |
| `openSourceFee` | `uint256` | `public` | ETH fee to register an open-source model. Default (set in `initialize`): `0.000001 ETH`. |
| `proprietaryFee` | `uint256` | `public` | ETH fee to register a proprietary model. Default (set in `initialize`): `0.00001 ETH`. |
| `openSourceUpdateFee` | `uint256` | `public` | ETH fee to request a manifest update for an open-source model. Default (set in `initialize`): `0.0000001 ETH`. |
| `proprietaryUpdateFee` | `uint256` | `public` | ETH fee to request a manifest update for a proprietary model. Default (set in `initialize`): `0.000001 ETH`. |
| `models` | `Model[]` | `private` | Append-only array of approved models. Index is the model ID. |
| `modelRequests` | `ModelRequest[]` | `public` | All registration requests (pending, approved, rejected). |
| `manifestRequests` | `ManifestUpdateRequest[]` | `public` | All manifest update requests. |
| `modelDisabled` | `mapping(uint256 => bool)` | `public` | Kill-switch flag per model ID. |
| `_modelIdByTaskCoordinator` | `mapping(address => uint256)` | `private` | Maps TaskCoordinator → `modelId + 1` (0 = unregistered). |
| `_modelIdByTaskAuditor` | `mapping(address => uint256)` | `private` | Maps TaskAuditor → `modelId + 1` (0 = unregistered). |
| `__gap` | `uint256[50]` | `private` | Reserved storage slots for future state variables (proxy layout safety). |

> The pre-proxy `daoAdmin` storage variable is gone; the admin is now the `OwnableUpgradeable` owner (stored in OZ's namespaced ERC-7201 storage). `daoAdmin()` remains callable as a view shim returning `owner()`.

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
| `ZeroAddress()` | `address(0)` passed where a valid address is required (used in `initialize`) |
| `CoordinatorNoLongerSlasher()` | Coordinator is not a registered slasher — checked at request time **and** re-checked at approval |
| `AuditorNoLongerSlasher()` | Auditor is not a registered slasher — checked at request time **and** re-checked at approval |
| `CoordinatorOwnershipChanged()` | Coordinator ownership changed between request and approval |
| `AuditorOwnershipChanged()` | Auditor ownership changed between request and approval |
| `TransferFailed()` | Low-level ETH transfer in `withdrawFees()` reverted |

Admin-gating reverts now surface as OpenZeppelin's `OwnableUnauthorizedAccount(address)` rather than the removed `NotDINDAOAdmin()`.

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
| `DAOAdminUpdated` | `address indexed oldAdmin`, `address indexed newAdmin` | `setDAOAdmin()` shim — **not** emitted if ownership is transferred via `transferOwnership()` directly (OZ emits only `OwnershipTransferred`) |

---

## 7. Access Control

```
owner() — OwnableUpgradeable; set to the account that ran initialize (DIN-Representative / deployer)
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
  └── setDAOAdmin()          ← shim over transferOwnership()

Model Owner (per-model — onlyModelOwner + notDisabled modifiers)
  └── requestManifestUpdate()   ← blocked if model is disabled

Any address (permissionless, fee-gated)
  └── requestModelRegistration()

ProxyAdmin (proxy level, owned by deployer)
  └── can upgrade the implementation (see §8)
```

---

## 8. Initialization, Ownership & Upgradeability

### 8.1 Constructor & `initialize`

```solidity
constructor()
```

Runs only on the raw implementation and calls `_disableInitializers()` — the implementation can never be initialized or administered directly; all state lives in the proxy.

```solidity
function initialize(address dinValidatorStake_) external initializer
```

- Runs exactly once, atomically with proxy deployment.
- Reverts with `ZeroAddress()` if `dinValidatorStake_ == address(0)` (a check the pre-proxy constructor did not have).
- `__Ownable_init(msg.sender)` — the deployer becomes `owner()` (the DIN-Representative role).
- Wires the `DinValidatorStake` proxy reference and sets the four default fees (values in §12).

### 8.2 Deployment position and wiring

From `hardhat/scripts/deploy-platform.ts`, the registry is deployed **last** (step 6) because `initialize` needs the `DinValidatorStake` proxy address:

```
1. DinToken proxy            initialize()
2. DinCoordinator proxy      initialize(dinToken)
3. dinToken.setCoordinator(dinCoordinator)
4. DinValidatorStake proxy   initialize(dinToken, dinCoordinator)
5. dinCoordinator.updateValidatorStakeContract(dinValidatorStake)
6. DINModelRegistry proxy    initialize(dinValidatorStake)     ← this contract
```

The registry needs no post-deploy wiring of its own. Note that a model registration can only succeed after its task contracts have been authorised as slashers (`DinCoordinator.addSlasherContract`), which requires steps 4–5 to be complete.

### 8.3 Ownership planes and upgrade mechanics

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | `initialize` caller (DIN-Representative) | All approval, kill-switch, fee, and withdrawal functions |
| Proxy admin (`ProxyAdmin` contract) | Deployed by the OZ upgrades plugin, owned by the deployer | Swapping the implementation |

- **Upgrade path:** `CONTRACT=DINModelRegistry npx hardhat run scripts/upgrade-platform.ts --network <network>` (reads/writes `hardhat/deployments/<network>.json`).
- **Storage-layout safety:** state may only be appended; the `__gap` array reserves 50 slots. `hardhat/test/DINModelRegistry.upgrade.test.ts` validates the upgrade with `upgrades.validateUpgrade` and asserts models, requests, and fees survive.
- **Trust implication:** the registry's guarantees (approval gating, fee levels, kill-switch state) hold only as long as the ProxyAdmin owner is honest.

---

## 9. Model Registration Flow

### 9.1 `requestModelRegistration`

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
2. **Slasher check — Coordinator:** `dinValidatorStake.isSlasherContract(taskCoordinator)` must be `true` — revert `CoordinatorNoLongerSlasher` (custom error; previously a `require` string `"Invalid Coordinator"`).
3. **Slasher check — Auditor:** same for `taskAuditor` — revert `AuditorNoLongerSlasher`.
4. **Distinctness:** `taskCoordinator != taskAuditor` — revert `TaskCoordinatorEqualsTaskAuditor`.
5. **Ownership — Coordinator:** `IOwnable(taskCoordinator).owner() == msg.sender` — revert `NotOwnerOfTaskCoordinator`.
6. **Ownership — Auditor:** same for `taskAuditor` — revert `NotOwnerOfTaskAuditor`.
7. **Write:** Push `ModelRequest` to `modelRequests[]`. `requestId = modelRequests.length` (before push).
8. **Emit** `ModelRegistrationRequested`.

> **Note:** The fee is held in the contract regardless of whether the request is approved or rejected.

---

### 9.2 `approveModel`

```solidity
function approveModel(uint256 requestId) external onlyOwner
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

### 9.3 `rejectModel`

```solidity
function rejectModel(uint256 requestId) external onlyOwner
```

Marks the request as processed and rejected. Fee is retained. Emits `ModelRejected`.

---

## 10. Manifest Update Flow

### 10.1 `requestManifestUpdate`

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

### 10.2 `approveManifestUpdate`

```solidity
function approveManifestUpdate(uint256 requestId) external onlyOwner
```

1. Bounds check, duplicate-processed check.
2. **Disabled check:** `modelDisabled[req.modelId]` must be `false` — revert `ModelIsDisabled`. Prevents approving a manifest update for a model that was disabled after the request was submitted.
3. Updates `models[req.modelId].manifestCID`. Emits `ManifestUpdated`.

### 10.3 `rejectManifestUpdate`

Marks processed/rejected, retains fee. Emits `ManifestUpdateRejected`.

---

## 11. Kill Switch

```solidity
function disableModel(uint256 modelId) external onlyOwner
function enableModel(uint256 modelId)  external onlyOwner
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

## 12. Fee Mechanism

| Parameter | Default | Applies To |
|-----------|---------|-----------|
| `openSourceFee` | `0.000001 ETH` | Open-source model registration |
| `proprietaryFee` | `0.00001 ETH` | Proprietary model registration |
| `openSourceUpdateFee` | `0.0000001 ETH` | Open-source manifest update requests |
| `proprietaryUpdateFee` | `0.000001 ETH` | Proprietary manifest update requests |

Fees accumulate in the contract balance. Only `owner()` can withdraw via `withdrawFees()`.

**Individual setters** — for single-fee adjustments:
`setOpenSourceFee`, `setProprietaryFee`, `setOpenSourceUpdateFee`, `setProprietaryUpdateFee`

**Combined setter** — for atomic governance proposals:
```solidity
function setFees(
    uint256 _openSourceFee,
    uint256 _proprietaryFee,
    uint256 _openSourceUpdateFee,
    uint256 _proprietaryUpdateFee
) external onlyOwner
```
Emits `FeesUpdated` with all four values as a state snapshot.

### `withdrawFees`

```solidity
function withdrawFees(address payable to) external onlyOwner {
    uint256 balance = address(this).balance;
    (bool success, ) = to.call{value: balance}("");
    if (!success) revert TransferFailed();
    emit FeesWithdrawn(to, balance);
}
```

Transfers the full contract balance to `to` using a **low-level `call`** instead of the previous `to.transfer(balance)`.

> **Why not `transfer`? The 2300 gas stipend limitation.** Solidity's `transfer` (and `send`) forward a fixed stipend of **2300 gas** to the recipient. That is only enough for a recipient whose `receive`/`fallback` does nothing beyond logging — an EOA, essentially. It breaks legitimate recipients:
>
> - **Smart-contract wallets and multisigs** (e.g. Gnosis Safe) execute code on ETH receipt and need more than 2300 gas, so `transfer` to them reverts. Since the DAO admin is expected to migrate to a multisig, `transfer` would have made fee withdrawal to that multisig impossible.
> - **Future-proofing:** the 2300 figure assumes today's opcode gas costs. Repricings (e.g. EIP-1884 raising `SLOAD`) have historically broken contracts that relied on the stipend, which is why `transfer`/`send` are no longer recommended.
>
> `call{value: ...}("")` forwards all remaining gas and returns a success flag, which the contract checks explicitly (revert `TransferFailed`). Forwarding all gas means the recipient could re-enter, but the function is `onlyOwner`, sends to an owner-chosen address, and performs no state accounting that re-entry could corrupt (the balance is read fresh each call), so no re-entrancy guard is needed here.

---

## 13. Lookup Functions

| Function | Parameters | Returns | Description |
|----------|-----------|---------|-------------|
| `getModel` | `uint256 modelId` | `owner, isOpenSource, manifestCID, createdAt, taskCoordinator, taskAuditor` | Full approved model record |
| `totalModels` | — | `uint256` | Total number of approved models |
| `getModelIdByTaskCoordinator` | `address taskCoordinator` | `(bool exists, uint256 modelId)` | Reverse lookup: coordinator → model |
| `getModelIdByTaskAuditor` | `address taskAuditor` | `(bool exists, uint256 modelId)` | Reverse lookup: auditor → model |

**Offset decoding:** Stored value is `modelId + 1`. View functions subtract 1 before returning the 0-indexed model ID.

---

## 14. DAO Admin & Compatibility Shims

The underlying auth model is `OwnableUpgradeable`. Two shims preserve the pre-proxy `daoAdmin` ABI surface that dincli calls:

```solidity
function daoAdmin() external view returns (address) {
    return owner();
}

function setDAOAdmin(address newAdmin) external onlyOwner {
    address old = owner();
    transferOwnership(newAdmin);
    emit DAOAdminUpdated(old, newAdmin);
}
```

- `daoAdmin()` is a read-through facade over `owner()`.
- `setDAOAdmin` delegates to OZ's single-step `transferOwnership` and additionally emits `DAOAdminUpdated` for existing indexers. The zero-address check is now enforced by OZ (`OwnableInvalidOwner`) rather than the local `ZeroAddress` error.
- This remains the migration path to a multisig or on-chain timelock without redeploying the registry.

> **Indexer caveat:** the inherited `transferOwnership()` and `renounceOwnership()` are also externally callable. Transferring ownership through them emits only OZ's `OwnershipTransferred`, **not** `DAOAdminUpdated` — off-chain services should index both events (or prefer `OwnershipTransferred`, which is emitted on every path).

---

## 15. Interactions with Other Contracts

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

## 16. Security Considerations

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
| DAO admin key compromise | `setDAOAdmin` / `transferOwnership` enables migration to multisig / timelock |
| Fee withdrawal to a contract recipient reverting | Low-level `call` (no 2300 gas stipend limit) with explicit `TransferFailed` check — see §12 |
| Re-initialization / implementation hijack | `initializer` modifier + `_disableInitializers()` in the constructor |
| Malicious upgrade | Governed by ProxyAdmin ownership; no timelock — see §8.3 |

---

## 17. Known Limitations & Future Work

- `taskCoordinator` and `taskAuditor` addresses are permanent after approval — no mechanism to update them.
- Pending requests never expire — a stale request remains approvable indefinitely (a `uint256 expiresAt` field could address this).
- Single DAO admin — no multi-sig quorum or on-chain voting yet (use `setDAOAdmin` to migrate).
- `withdrawFees` has no zero-address check on `to` — ETH sent to `address(0)` would be burned (pre-existing behavior, unchanged by the proxy conversion).

---

## 18. Change Log

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy: now inherits `Initializable` + `OwnableUpgradeable`; `constructor(_dinValidatorStake)` replaced by `_disableInitializers()` constructor plus `initialize(dinValidatorStake_)`.
- Pragma bumped `^0.8.20` → `^0.8.28`.
- **Admin model:** `daoAdmin` storage variable, `onlyDAOAdmin` modifier, and `NotDINDAOAdmin` error removed; all admin functions now use OZ `onlyOwner`. Backward-compat shims `daoAdmin()` (view → `owner()`) and `setDAOAdmin()` (→ `transferOwnership` + `DAOAdminUpdated`) preserve the old ABI surface for dincli.
- `initialize` gained a zero-address check on the stake address (the old constructor had none); default fees moved from inline initializers into `initialize` (values unchanged).
- `requestModelRegistration`: `require(..., "Invalid Coordinator"/"Invalid Auditor")` string reverts replaced with the custom errors `CoordinatorNoLongerSlasher` / `AuditorNoLongerSlasher` (now used at request time and approval time).
- `withdrawFees`: `to.transfer(balance)` replaced with low-level `call` + new `TransferFailed` error, removing the 2300 gas stipend limitation (see §12).
- Added `uint256[50] __gap` storage reserve.
- Unchanged: all structs, events, the request/approve/reject flows (including approval-time revalidation and the `modelId + 1` mapping trick), views, kill switch, and fee-setter logic.

---

## 19. Review Notes & Open Caveats

Observations from the PR 13 review worth tracking:

- **No. 1 — Event gap on direct ownership transfer:** `transferOwnership` / `renounceOwnership` bypass `setDAOAdmin`, so a handover through them emits no `DAOAdminUpdated`. Indexers must also watch `OwnershipTransferred` (see §14).
- **No. 2 — `renounceOwnership` bricks governance:** renouncing leaves the registry with no admin — approvals, kill switch, fee changes, and `withdrawFees` become permanently unusable. Funds already in the contract would be stranded.
- **No. 3 — Single-step ownership transfer:** `setDAOAdmin` uses OZ's one-step `transferOwnership`; a typoed address is unrecoverable. `Ownable2StepUpgradeable` would make handover safer.
- **No. 4 — Repurposed error names:** `CoordinatorNoLongerSlasher` / `AuditorNoLongerSlasher` now also fire on first-time request validation, where "no longer" is a misnomer. Selector-stable but slightly misleading in traces.
- **No. 5 — Admin revert selector changed:** unauthorized admin calls revert with `OwnableUnauthorizedAccount` instead of `NotDINDAOAdmin` — anything decoding revert reasons (tests, dincli error handling) must use the new selector.
