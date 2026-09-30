# DINModelRegistry — Technical Documentation

> **File:** [`foundry/src/DINModelRegistry.sol`](../../../foundry/src/DINModelRegistry.sol)
> **Version:** v2 — Request / Approval Based (upgradeable)
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.28`
> **Deployment:** once per network behind an OpenZeppelin Transparent Proxy

---

## 1. Overview

`DINModelRegistry` is the **governed admission gateway** for AI models in the Decentralised Intelligence Network. It evolved from a simple storage contract into a registry controlled by the DIN-Representative (the contract owner) where every model and every manifest change must pass an explicit approval step before taking effect.

The admin role is the OpenZeppelin `OwnableUpgradeable` owner (the DIN-Representative), set to the deployer in `initialize`. Admin transfer is plain `transferOwnership` — see [§14](#14-admin-transfer).

Core capabilities:

- **Two-phase model registration** — submit a request, the DIN-Representative approves or rejects.
- **Two-phase manifest updates** — same request/approval flow.
- **Kill switch** — the DIN-Representative can instantly disable any model.
- **Dynamic fee governance** — all four fee parameters are adjustable by the DIN-Representative. Requests keep exactly the required fee; any overpayment is refunded to the caller.
- **Fee routing** — accumulated ETH fees are swept to `DinFeeRouter` (`sweepFeesToRouter`), which splits them across validator pool / treasury / storage / public goods.
- **Transferable admin** — the owner role can be handed to a multisig or timelock (`transferOwnership`).
- **Upgradeable** — logic can be replaced behind the proxy while all requests, models, and fees persist (see [§8](#8-initialization-ownership--upgradeability)).

---

## 2. Inheritance & Inline Interfaces

```solidity
import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuardTransient.sol";

contract DINModelRegistry is Initializable, OwnableUpgradeable, ReentrancyGuardTransient { ... }
```

`ReentrancyGuardTransient` provides the `nonReentrant` modifier used on the two fee-refunding request functions (§9.1, §10.1). It keeps its lock in transient storage (EIP-1153, `TSTORE`/`TLOAD`), so it adds no storage slots to the proxy layout.

```solidity
interface IDinValidatorStake {
    function isSlasherContract(address slasherContract) external view returns (bool);
}

interface IOwnable {
    function owner() external view returns (address);
}

interface IDinFeeRouter {
    function routeFeeETH(address payer) external payable;
}
```

`IDinValidatorStake` and `IOwnable` are used during registration request validation and approval-time revalidation; `IDinFeeRouter` by `sweepFeesToRouter`.

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
| `feeRouter` | `IDinFeeRouter` | `public` | Destination for `sweepFeesToRouter`. Set via `setFeeRouter` (the deploy script wires it). |
| `__gap` | `uint256[50]` | `private` | Reserved storage slots for future state variables (proxy layout safety). |

> The pre-proxy `daoAdmin` storage variable is gone; the admin is now the `OwnableUpgradeable` owner (stored in OZ's namespaced ERC-7201 storage).

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
    uint256 feePaid;  // the required fee at request time, not msg.value (overpayment is refunded)
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
    uint256 feePaid;  // the required fee at request time, not msg.value (overpayment is refunded)
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
| `RefundFailed()` | Refunding the overpayment (`msg.value - requiredFee`) to `msg.sender` failed — e.g. a contract caller that rejects ETH |
| `TaskCoordinatorEqualsTaskAuditor()` | `taskCoordinator == taskAuditor` |
| `NotOwnerOfTaskCoordinator()` | Requester does not own the coordinator contract |
| `NotOwnerOfTaskAuditor()` | Requester does not own the auditor contract |
| `ModelIsDisabled(uint256 modelId)` | Model is currently disabled |
| `TaskCoordinatorAlreadyRegistered()` | Coordinator is already linked to another approved model |
| `TaskAuditorAlreadyRegistered()` | Auditor is already linked to another approved model |
| `ZeroAddress()` | `address(0)` passed to `initialize` or `setFeeRouter` |
| `CoordinatorNoLongerSlasher()` | Coordinator is not a registered slasher — checked at request time **and** re-checked at approval |
| `AuditorNoLongerSlasher()` | Auditor is not a registered slasher — checked at request time **and** re-checked at approval |
| `CoordinatorOwnershipChanged()` | Coordinator ownership changed between request and approval |
| `AuditorOwnershipChanged()` | Auditor ownership changed between request and approval |
| `FeeRouterNotSet()` | `sweepFeesToRouter()` called before `setFeeRouter()` |

Admin-gating reverts surface as OpenZeppelin's `OwnableUnauthorizedAccount(address)` (the pre-proxy `NotDINDAOAdmin()` error is gone).

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
| `FeeRouterUpdated` | `address indexed feeRouter` | `setFeeRouter()` |
| `FeesSweptToRouter` | `uint256 amount` | `sweepFeesToRouter()` forwarded a non-zero balance |

Ownership changes emit only OpenZeppelin's `OwnershipTransferred(previousOwner, newOwner)`.

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
  ├── setFeeRouter()
  ├── sweepFeesToRouter()
  └── transferOwnership()    ← inherited from OwnableUpgradeable

Model Owner (per-model — onlyModelOwner + notDisabled modifiers)
  └── requestManifestUpdate()   ← blocked if model is disabled; nonReentrant

Any address (permissionless, fee-gated)
  └── requestModelRegistration()   ← nonReentrant

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

From [`foundry/script/DeployPlatform.s.sol`](../../../foundry/script/DeployPlatform.s.sol) (see [DeployPlatform](foundry/script/DeployPlatform.md)), the registry comes after `DinValidatorStake`, because `initialize` needs the stake proxy address, and is then wired into the fee router:

```
7.  DinValidatorStake proxy   initialize(dinToken, dinCoordinator)
8.  dinCoordinator.updateValidatorStakeContract(dinValidatorStake)
10. DINModelRegistry proxy    initialize(dinValidatorStake)       ← this contract
11. dinFeeRouter.addFeeSource(dinModelRegistry)                   ← lets sweepFeesToRouter through
12. dinModelRegistry.setFeeRouter(dinFeeRouter)
```

A model registration can only succeed after its task contracts have been authorised as slashers (`DinCoordinator.addSlasherContract`), which requires steps 7–8.

### 8.3 Ownership planes and upgrade mechanics

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | `initialize` caller (DIN-Representative) | All approval, kill-switch, fee, and fee-routing functions |
| Proxy admin (`ProxyAdmin` contract) | One per proxy (OZ v5), created at proxy deployment and owned by the deployer | Swapping the implementation |

- **Upgrade path:** `cd foundry && CONTRACT=DINModelRegistry forge script script/UpgradePlatform.s.sol --rpc-url <rpc> --broadcast ...` (reads the proxy address from `foundry/deployments/<network>.json`; see [`foundry/script/UpgradePlatform.s.sol`](../../../foundry/script/UpgradePlatform.s.sol) and [UpgradePlatform](foundry/script/UpgradePlatform.md)).
- **Storage-layout safety:** state may only be appended; the `__gap` array reserves 50 slots. [`foundry/test/UpgradeValidation.t.sol`](../../../foundry/test/UpgradeValidation.t.sol) runs `Upgrades.validateImplementation`, and `DINModelRegistryUpgradeTest` in [`foundry/test/DeployPlatform.t.sol`](../../../foundry/test/DeployPlatform.t.sol) upgrades to [`foundry/src/upgrade/DINModelRegistryV2.sol`](../../../foundry/src/upgrade/DINModelRegistryV2.sol) and checks fees, models and pending requests survive.
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
) external payable nonReentrant returns (uint256 requestId)
```

**Validation (sequential):**

1. **Fee check:** `msg.value >= openSourceFee` (open-source) or `>= proprietaryFee` (proprietary) — revert `InsufficientFee`.
2. **Slasher check — Coordinator:** `dinValidatorStake.isSlasherContract(taskCoordinator)` must be `true` — revert `CoordinatorNoLongerSlasher` (custom error; previously a `require` string `"Invalid Coordinator"`).
3. **Slasher check — Auditor:** same for `taskAuditor` — revert `AuditorNoLongerSlasher`.
4. **Distinctness:** `taskCoordinator != taskAuditor` — revert `TaskCoordinatorEqualsTaskAuditor`.
5. **Ownership — Coordinator:** `IOwnable(taskCoordinator).owner() == msg.sender` — revert `NotOwnerOfTaskCoordinator`.
6. **Ownership — Auditor:** same for `taskAuditor` — revert `NotOwnerOfTaskAuditor`.
7. **Write:** Push `ModelRequest` to `modelRequests[]` with `feePaid = requiredFee`. `requestId = modelRequests.length` (before push).
8. **Emit** `ModelRegistrationRequested`.
9. **Refund:** if `msg.value > requiredFee`, send the overpayment back to `msg.sender` with a low-level `call` — revert `RefundFailed` if it fails. This runs last (checks-effects-interactions) and the function is `nonReentrant`.

> **Note:** The required fee is held in the contract regardless of whether the request is approved or rejected.

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
) external payable nonReentrant onlyModelOwner(modelId) notDisabled(modelId) returns (uint256 requestId)
```

- **`onlyModelOwner`** — caller must be the model's registered owner.
- **`notDisabled`** — reverts `ModelIsDisabled(modelId)` if the model is currently disabled.
- Fee: `openSourceUpdateFee` or `proprietaryUpdateFee` based on `models[modelId].isOpenSource` — revert `InsufficientFee` if `msg.value` is below it.
- Pushes a `ManifestUpdateRequest` with `feePaid = requiredFee`. Emits `ManifestUpdateRequested`.
- Refunds any overpayment to `msg.sender` last, exactly as in §9.1 (`RefundFailed` on failure; `nonReentrant`).

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
- `modelDisabled` is `public`, so downstream contracts *could* read it (`modelRegistry.modelDisabled(modelId)`), but today neither `DINTaskCoordinator` nor `DINTaskAuditor` does.
- Emits `ModelDisabled` / `ModelEnabled`.
- **Disabled ≠ Deleted.** History, ownership, and manifest are preserved for auditability.

What disabling actually does today:

| Effect | Enforced? |
|--------|-----------|
| Blocks `requestManifestUpdate` (`notDisabled` modifier) | ✅ |
| Blocks `approveManifestUpdate` for that model | ✅ |
| Stops GIs, LM submissions, aggregation, audits or slashing in the task contracts | ❌ — not checked by `DINTaskCoordinator` / `DINTaskAuditor` (§19 No. 6) |

---

## 12. Fee Mechanism

| Parameter | Default | Applies To |
|-----------|---------|-----------|
| `openSourceFee` | `0.000001 ETH` | Open-source model registration |
| `proprietaryFee` | `0.00001 ETH` | Proprietary model registration |
| `openSourceUpdateFee` | `0.0000001 ETH` | Open-source manifest update requests |
| `proprietaryUpdateFee` | `0.000001 ETH` | Proprietary manifest update requests |

Each request keeps exactly its required fee (any overpayment is refunded — §9.1, §10.1). Fees accumulate in the contract balance and leave only through `sweepFeesToRouter()`.

**Individual setters** — for single-fee adjustments:
`setOpenSourceFee`, `setProprietaryFee`, `setOpenSourceUpdateFee`, `setProprietaryUpdateFee`

**Combined setter** — for atomic updates:
```solidity
function setFees(
    uint256 _openSourceFee,
    uint256 _proprietaryFee,
    uint256 _openSourceUpdateFee,
    uint256 _proprietaryUpdateFee
) external onlyOwner
```
Emits `FeesUpdated` with all four values as a state snapshot.

### `setFeeRouter` / `sweepFeesToRouter`

```solidity
function setFeeRouter(address feeRouter_) external onlyOwner   // ZeroAddress on 0; emits FeeRouterUpdated

function sweepFeesToRouter() external onlyOwner {
    if (address(feeRouter) == address(0)) revert FeeRouterNotSet();
    uint256 balance = address(this).balance;
    if (balance == 0) return;
    feeRouter.routeFeeETH{value: balance}(address(this));
    emit FeesSweptToRouter(balance);
}
```

- Fees accrue per request with no router call, and are batched through the sweep so the router's external-call cost is paid once for many registrations/updates.
- `DinFeeRouter.routeFeeETH` is `onlyFeeSource`, so the registry must be on the router's allowlist (`addFeeSource`, done by the deploy script). The router splits ETH by its `ethSplit` (default 95% validator pool / 5% treasury; ETH is never burned).
- There is no direct withdrawal to an arbitrary address. dincli: `dinrep registry sweep-fees`, which checks ownership, that the router is set, and that the registry is a router fee source, then previews the split and asks before sending. The router is wired only by the deploy script; dincli has no command to change it.
- No re-entrancy guard on the sweep: the function is `onlyOwner`, sends to the owner-configured router, and keeps no accounting that re-entry could corrupt (the balance is read fresh).

---

## 13. Lookup Functions

| Function | Parameters | Returns | Description |
|----------|-----------|---------|-------------|
| `getModel` | `uint256 modelId` | `owner, isOpenSource, manifestCID, createdAt, taskCoordinator, taskAuditor` | Full approved model record |
| `totalModels` | — | `uint256` | Total number of approved models |
| `totalModelRequests` | — | `uint256` | Length of `modelRequests` (all registration requests) |
| `totalManifestRequests` | — | `uint256` | Length of `manifestRequests` |
| `getModelIdByTaskCoordinator` | `address taskCoordinator` | `(bool exists, uint256 modelId)` | Reverse lookup: coordinator → model |
| `getModelIdByTaskAuditor` | `address taskAuditor` | `(bool exists, uint256 modelId)` | Reverse lookup: auditor → model |

**Offset decoding:** Stored value is `modelId + 1`. View functions subtract 1 before returning the 0-indexed model ID.

---

## 14. Admin Transfer

The auth model is plain `OwnableUpgradeable`: admin transfer goes through the inherited `transferOwnership(newOwner)` (single-step; zero address rejected with `OwnableInvalidOwner`), which emits `OwnershipTransferred`. `renounceOwnership()` is also inherited and callable — see §19 No. 2. There are no `daoAdmin()` / `setDAOAdmin()` compatibility shims.

---

## 15. Interactions with Other Contracts

```
DINModelRegistry
  ├── reads → DinValidatorStake.isSlasherContract()   [at request and approval]
  ├── reads → taskCoordinator.owner()                  [IOwnable, at request and approval]
  ├── reads → taskAuditor.owner()                      [IOwnable, at request and approval]
  └── calls → DinFeeRouter.routeFeeETH{value}(this)    [sweepFeesToRouter]
```

No contract currently reads `modelDisabled`: `DINTaskCoordinator` and `DINTaskAuditor` do not check it, so the kill switch only blocks manifest updates in the registry itself (see §19 No. 6).

---

## 16. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Arbitrary contracts registered as coordinators/auditors | `isSlasherContract()` checked at request time and revalidated at approval |
| Ownership transferred between request and approval | `IOwnable.owner()` revalidated inside `approveModel()` |
| Slasher status revoked between request and approval | `isSlasherContract()` revalidated inside `approveModel()` |
| Coordinator / auditor reused across models | `_modelIdByTaskCoordinator` / `_modelIdByTaskAuditor` uniqueness enforced at approval |
| Silent manifest change by model owner | Manifest updates require DIN-Representative approval |
| Malicious approved model | Kill switch (`disableModel`) provides instant remediation |
| Disabled model manifest still approved | `approveManifestUpdate` checks `modelDisabled` before writing |
| Fee spam on registration | Fee required at request time; retained on rejection |
| Overpayment kept by the registry | Anything above the required fee is refunded in the same call; `feePaid` records only the required fee |
| Re-entrancy through the refund call | The refund is the last step (checks-effects-interactions) and both request functions are `nonReentrant` (`ReentrancyGuardTransient`) |
| Admin key compromise | `transferOwnership` enables migration to multisig / timelock |
| Fees diverted | ETH leaves only via `sweepFeesToRouter` to the owner-configured router; no arbitrary-recipient withdrawal |
| Re-initialization / implementation hijack | `initializer` modifier + `_disableInitializers()` in the constructor |
| Malicious upgrade | Governed by ProxyAdmin ownership; no timelock — see §8.3 |

---

## 17. Known Limitations & Future Work

- `taskCoordinator` and `taskAuditor` addresses are permanent after approval — no mechanism to update them.
- Pending requests never expire — a stale request remains approvable indefinitely (a `uint256 expiresAt` field could address this).
- Single admin key (the DIN-Representative) — no multi-sig quorum or on-chain voting yet (migrate via `transferOwnership`).
- The kill switch (`modelDisabled`) is not enforced by the task contracts (see §19 No. 6).

---

## 18. Change Log

### PR No. 176 L-3 — overpayment refund (foundry)

- `requestModelRegistration` and `requestManifestUpdate` refund any `msg.value` above the required fee to the caller, and `feePaid` now records the required fee instead of `msg.value` (`354bd9a`, `9bc63c5`).
- New `RefundFailed()` error for a failed refund.
- Now also inherits `ReentrancyGuardTransient`; both request functions are `nonReentrant`. The guard uses transient storage, so the proxy storage layout is unchanged.

### P3 — fee routing (foundry)

- **Removed** `withdrawFees(address)`, `FeesWithdrawn` and `TransferFailed`; added `feeRouter`, `setFeeRouter`, `sweepFeesToRouter`, `FeeRouterNotSet`, `FeeRouterUpdated`, `FeesSweptToRouter`.
- The `daoAdmin()` / `setDAOAdmin()` compatibility shims and `DAOAdminUpdated` are gone; admin transfer is `transferOwnership` only.

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy: now inherits `Initializable` + `OwnableUpgradeable`; `constructor(_dinValidatorStake)` replaced by `_disableInitializers()` constructor plus `initialize(dinValidatorStake_)`.
- Pragma bumped `^0.8.20` → `^0.8.28`.
- **Admin model:** `daoAdmin` storage variable, `onlyDAOAdmin` modifier, and `NotDINDAOAdmin` error removed; all admin functions now use OZ `onlyOwner`. Backward-compat shims `daoAdmin()` (view → `owner()`) and `setDAOAdmin()` (→ `transferOwnership` + `DAOAdminUpdated`) preserve the old ABI surface (used by dincli's `set-dao-admin` until PR No. 183 removed that command).
- `initialize` gained a zero-address check on the stake address (the old constructor had none); default fees moved from inline initializers into `initialize` (values unchanged).
- `requestModelRegistration`: `require(..., "Invalid Coordinator"/"Invalid Auditor")` string reverts replaced with the custom errors `CoordinatorNoLongerSlasher` / `AuditorNoLongerSlasher` (now used at request time and approval time).
- `withdrawFees`: `to.transfer(balance)` replaced with low-level `call` + new `TransferFailed` error, removing the 2300 gas stipend limitation (later superseded by `sweepFeesToRouter`, see the P3 entry above).
- Added `uint256[50] __gap` storage reserve.
- Unchanged: all structs, events, the request/approve/reject flows (including approval-time revalidation and the `modelId + 1` mapping trick), views, kill switch, and fee-setter logic.

---

## 19. Review Notes & Open Caveats

Observations from the PR 13 review worth tracking:

- **No. 2 — `renounceOwnership` bricks governance:** renouncing leaves the registry with no admin — approvals, kill switch, fee changes, and `sweepFeesToRouter` become permanently unusable. Fees already in the contract would be stranded.
- **No. 3 — Single-step ownership transfer:** `transferOwnership` is one-step; a typoed address is unrecoverable. `Ownable2StepUpgradeable` would make handover safer.
- **No. 4 — Repurposed error names:** `CoordinatorNoLongerSlasher` / `AuditorNoLongerSlasher` now also fire on first-time request validation, where "no longer" is a misnomer. Selector-stable but slightly misleading in traces.
- **No. 5 — Admin revert selector changed:** unauthorized admin calls revert with `OwnableUnauthorizedAccount` instead of `NotDINDAOAdmin` — anything decoding revert reasons (tests, dincli error handling) must use the new selector.
- **No. 6 — Kill switch is not enforced downstream:** neither `DINTaskCoordinator` nor `DINTaskAuditor` reads `modelDisabled`, so disabling a model does not stop its GIs, submissions, or slashing — it only blocks manifest-update requests/approvals in the registry.
