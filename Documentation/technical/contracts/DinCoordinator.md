# DinCoordinator — Technical Documentation

> **File:** `hardhat/contracts/DinCoordinator.sol`
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`

---

## 1. Overview

`DinCoordinator` is the **entry-point and treasury contract** for the DIN Protocol. Its two core responsibilities are:

1. **Token issuance** — Accept ETH deposits from users and mint an equivalent amount of DIN tokens into their wallets.
2. **Slasher management** — Act as the privileged caller that can register or de-register slasher contracts on `DinValidatorStake` on behalf of the DAO representative.

The contract is deployed **once per network behind an OpenZeppelin Transparent Proxy** and configured through `initialize(address dinToken_)` instead of a constructor. It does **not** deploy `DinToken` itself: the token is deployed first (as its own proxy) and its address is passed to `initialize`. Minting rights are granted in a separate post-deploy step by calling `DinToken.setCoordinator(coordinatorProxy)` — see [§10 Deployment & Initialization Sequence](#10-deployment--initialization-sequence).



---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Initializable` | OpenZeppelin (upgradeable) | Initializer guard for the proxy pattern |
| `OwnableUpgradeable` | OpenZeppelin (upgradeable) | DAO admin access control; owner set in `initialize` |
| `ReentrancyGuardTransient` | OpenZeppelin (L2-optimized) | Prevents re-entrancy on ETH flows |
| `DinToken` | Local | Token proxy reference, wired in `initialize` |
| `IDinValidatorStake` (local interface) | Local | Typed calls to `DinValidatorStake` |

`ReentrancyGuardTransient` is the L2-optimised variant that uses transient storage (EIP-1153), reducing gas cost for the re-entrancy lock on L2 networks. It is the non-upgradeable OpenZeppelin contract, which is safe behind a proxy because it is stateless — the lock lives in transient storage and occupies no storage slots.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinToken` | `DinToken` | `public` | Reference to the `DinToken` proxy. Set once in `initialize` (a regular storage variable — `immutable` is not usable behind a proxy). |
| `dinValidatorStakeContract` | `IDinValidatorStake` | `public` | Mutable reference to the validator staking contract. Set after deployment via `updateValidatorStakeContract`. |
| `dinPerEth` | `uint256` | `public` | Exchange rate: how many raw DIN tokens (18-decimal units) are minted per 1 ETH wei. Default (set in `initialize`): `1,000,000 × 10¹⁸` (i.e., 1M DIN per ETH). |
| `__gap` | `uint256[50]` | `private` | Reserved storage slots so future versions can append state variables without shifting the layout of child storage. |

---

## 4. Custom Errors

| Error | Condition |
|-------|-----------|
| `InvalidAddress()` | Zero-address provided to an address parameter |
| `ValidatorStakeContractNotSet()` | Slasher management called before `dinValidatorStakeContract` is configured |
| `ZeroValue()` | ETH deposit of zero value, or exchange rate update to zero |
| `TransferFailed()` | Low-level ETH transfer from `withdraw()` reverted |

---

## 5. Events

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `EthDepositAndDINminted` | `address indexed user`, `uint256 ethAmount`, `uint256 mintAmount` | Successful `depositAndMint()` |
| `SlasherContractAdded` | `address indexed slasher` | Slasher registered on validator stake contract |
| `SlasherContractRemoved` | `address indexed slasher` | Slasher de-registered |
| `ValidatorStakeContractUpdated` | `address indexed validatorStakeContract` | Stake contract reference updated |
| `DinPerEthUpdated` | `uint256 newRate` | Exchange rate changed |

---

## 6. Access Control

```
owner() — OwnableUpgradeable; set to the account that ran initialize (DAO representative / deployer)
  ├── withdraw()
  ├── addSlasherContract()
  ├── removeSlasherContract()
  ├── updateValidatorStakeContract()
  └── updateDinPerEth()

Any address (permissionless)
  └── depositAndMint()   ← payable, guarded by nonReentrant
```

A second, independent control plane exists at the proxy level: the **ProxyAdmin** contract that can upgrade the implementation. See [§9 Ownership & Upgradeability](#9-ownership--upgradeability).

---

## 7. Functions

### 7.1 Constructor & `initialize`

```solidity
constructor()
```

- Runs only on the raw implementation contract, never through the proxy.
- Calls `_disableInitializers()`, permanently locking the implementation: calling `initialize` directly on it reverts with `InvalidInitialization`. This prevents anyone from "adopting" the unproxied implementation.

```solidity
function initialize(address dinToken_) external initializer
```

- Runs exactly once, atomically with proxy deployment (the deploy script encodes the call into the proxy's constructor data, so there is no front-running window).
- Reverts with `InvalidAddress()` if `dinToken_ == address(0)`.
- `__Ownable_init(msg.sender)` — the deployer account becomes `owner()`.
- Stores the externally deployed `DinToken` proxy address in `dinToken`.
- Sets `dinPerEth` to the default `1_000_000 * 1e18`.

> **Note:** Unlike the pre-proxy version, the coordinator does **not** deploy `DinToken` and is not automatically its minter. Minting rights are granted afterwards via `DinToken.setCoordinator(coordinatorProxy)`; until that step, `depositAndMint()` reverts with `DinToken.Unauthorized()`.

---

### 7.2 `depositAndMint` — Token Issuance Mechanism

```solidity
function depositAndMint() external payable nonReentrant
```

**Purpose:** Converts ETH to DIN tokens at the current exchange rate.

**Algorithm:**
1. Revert with `ZeroValue()` if `msg.value == 0`.
2. Compute `mintAmount`:
   ```
   mintAmount = (msg.value × dinPerEth) / 10¹⁸
   ```
   - This performs safe decimal math: `dinPerEth` is stored as a 10¹⁸-scaled value, so dividing by 10¹⁸ correctly normalises the result.
   - Example: `msg.value = 1 ETH (10¹⁸ wei)` → `mintAmount = (10¹⁸ × 1_000_000 × 10¹⁸) / 10¹⁸ = 1_000_000 × 10¹⁸ raw DIN units`.
3. Call `dinToken.mint(msg.sender, mintAmount)`.
4. Emit `EthDepositAndDINminted`.

**Re-entrancy protection:** `nonReentrant` using transient storage. The ETH remains in the contract's balance until `withdraw()` is called.

---

### 7.3 `withdraw`

```solidity
function withdraw() external onlyOwner nonReentrant
```

Transfers the full ETH balance to the `owner()`. Silent no-op if balance is zero. Uses a low-level `.call` for ETH transfer; reverts with `TransferFailed()` if the call fails.

---

### 7.4 `addSlasherContract`

```solidity
function addSlasherContract(address slasherContract) external onlyOwner
```

Delegates to `dinValidatorStakeContract.addSlasherContract(slasherContract)`. Enforces:
- `slasherContract != address(0)`.
- `dinValidatorStakeContract` is set.

Used by the DAO representative to authorise `DINTaskCoordinator` and `DINTaskAuditor` contracts to call `slash()` on validators.

---

### 7.5 `removeSlasherContract`

```solidity
function removeSlasherContract(address slasherContract) external onlyOwner
```

Symmetric reverse of `addSlasherContract`. Delegates to `dinValidatorStakeContract.removeSlasherContract(slasherContract)`.

---

### 7.6 `updateValidatorStakeContract`

```solidity
function updateValidatorStakeContract(address validatorStakeContract) external onlyOwner
```

Updates the mutable `dinValidatorStakeContract` reference. Intended to be called once after `DinValidatorStake` is deployed. Reverts on zero address.

---

### 7.7 `updateDinPerEth`

```solidity
function updateDinPerEth(uint256 newRate) external onlyOwner
```

Updates the ETH→DIN exchange rate. Reverts on zero. Emits `DinPerEthUpdated`.

---

## 8. Token Issuance Economics

| Parameter | Default Value | Description |
|-----------|--------------|-------------|
| `dinPerEth` | `1,000,000 × 10¹⁸` | Raw DIN units minted per 1 ETH wei |
| Effective rate | 1 ETH → 1,000,000 DIN | Adjustable by DAO admin |

The ETH collected accumulates in this contract and is withdrawable by `owner()` at any time.

---

## 9. Ownership & Upgradeability

The contract has **two independent control planes** that must not be confused:

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | Account that ran `initialize` (deployer / DAO representative) | `withdraw`, slasher management, `updateValidatorStakeContract`, `updateDinPerEth`; transferable via `transferOwnership` |
| Proxy admin (`ProxyAdmin` contract) | Deployed by the OpenZeppelin upgrades plugin at proxy deployment; owned by the deployer | Swapping the implementation contract (i.e., changing *all* code and rules) |

Upgrade mechanics:

- **Proxy kind:** OpenZeppelin **Transparent Proxy** (`upgrades.deployProxy(..., { kind: "transparent" })`). The proxy address is permanent; only the implementation behind it changes.
- **Upgrade path:** `CONTRACT=DinCoordinator npx hardhat run scripts/upgrade-platform.ts --network <network>`. The script loads the proxy address from `hardhat/deployments/<network>.json`, runs `upgrades.upgradeProxy`, and records the new implementation address back into the file.
- **Storage-layout safety:** state variables must only ever be appended. The trailing `uint256[50] __gap` reserves room for future variables. Upgrade tests (`hardhat/test/DinCoordinator.upgrade.test.ts`) call `upgrades.validateUpgrade` against a V2 fixture (`hardhat/contracts/upgrade/DinCoordinatorV2.sol`) and assert that `dinToken`, `dinPerEth`, balances, and owner-only restrictions survive the upgrade.
- **Implementation lock:** the constructor's `_disableInitializers()` means the raw implementation can never be initialized or owned — only the proxy has state.
- **Trust implication:** every guarantee in this document holds only as long as the ProxyAdmin owner is honest; an upgrade can replace any rule, including `onlyOwner` checks.

---

## 10. Deployment & Initialization Sequence

Automated by `hardhat/scripts/deploy-platform.ts` (mirrored by the test fixture `hardhat/test/helpers/platform.ts`). Each contract is a Transparent Proxy whose `initialize` runs atomically at deployment:

```
1. Deploy DinToken proxy             → initialize()
2. Deploy DinCoordinator proxy       → initialize(dinTokenAddress)
3. dinToken.setCoordinator(dinCoordinatorAddress)          ← one-shot; grants minting rights
4. Deploy DinValidatorStake proxy    → initialize(dinTokenAddress, dinCoordinatorAddress)
5. dinCoordinator.updateValidatorStakeContract(dinValidatorStakeAddress)
6. Deploy DINModelRegistry proxy     → initialize(dinValidatorStakeAddress)
7. Addresses (proxies + shared proxyAdmin) saved to hardhat/deployments/<network>.json

Later, per model:
   dinCoordinator.addSlasherContract(taskCoordinatorAddress)
   dinCoordinator.addSlasherContract(taskAuditorAddress)
```

**Partially wired states** (between steps, or if a wiring step is skipped):

| Missing step | Symptom |
|--------------|---------|
| Step 3 (`setCoordinator`) not done | `depositAndMint()` reverts with `DinToken.Unauthorized()` — the token has no minter yet |
| Step 5 (`updateValidatorStakeContract`) not done | `addSlasherContract` / `removeSlasherContract` revert with `ValidatorStakeContractNotSet()` |

---

## 11. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Re-entrancy via ETH deposit | `ReentrancyGuardTransient` on `depositAndMint` and `withdraw` |
| Rogue slasher registration | `onlyOwner` on add/remove slasher functions |
| Exchange rate manipulation | Only `owner` can update `dinPerEth` |
| ETH locked | `withdraw()` allows owner to drain contract at any time |
| Re-initialization | `initializer` modifier — `initialize` can run exactly once per proxy |
| Implementation hijack | Constructor calls `_disableInitializers()` on the implementation |
| Malicious upgrade | Governed by ProxyAdmin ownership (deployer); no on-chain timelock — operational key security is the only safeguard |

---

## 12. Interactions with Other Contracts

```
DinCoordinator (proxy)
  ├── calls → DinToken.mint(user, amount)       [on depositAndMint]
  ├── calls → DinValidatorStake.addSlasherContract()
  └── calls → DinValidatorStake.removeSlasherContract()

DinToken (proxy)
  └── setCoordinator(dinCoordinator) authorises this contract as sole minter [post-deploy wiring]
```

---

## 13. Change Log

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy: `Ownable` → `Initializable` + `OwnableUpgradeable`; constructor replaced by `_disableInitializers()` plus `initialize(address dinToken_)`.
- No longer deploys `DinToken` in its constructor — the token proxy is deployed separately and injected via `initialize`; minting rights are granted afterwards through `DinToken.setCoordinator` (see §10).
- `dinToken` lost `immutable` (regular storage, set once in `initialize`); the `dinPerEth` default moved from an inline initializer into `initialize` (value unchanged).
- Added `uint256[50] __gap` storage reserve.
- Unchanged: `depositAndMint`, `withdraw`, slasher management, `updateValidatorStakeContract`, `updateDinPerEth`, and all events/errors.

---

## 14. Review Notes & Open Caveats

- **No. 1 — Ownership is claimed at initialization, not implementation deployment:** whoever runs the deploy script becomes `owner()`; transfer to the DAO multisig should be part of the deployment runbook.
- **No. 2 — Wiring is a two-transaction trust window:** between proxy deployment and `DinToken.setCoordinator`, `depositAndMint` reverts. The deploy script performs the wiring immediately, but a manual deployment that skips it leaves the exchange non-functional (fails closed, not open).
- **No. 3 — `updateValidatorStakeContract` has no one-shot guard:** the owner can re-point the stake contract at any time (pre-existing behavior; the NatSpec now documents it as an operational responsibility).
- **No. 4 — Upgrade power is absolute:** the ProxyAdmin owner can replace all logic, including the exchange rate and withdrawal rules, with no timelock (see §9).
