# DinCoordinator — Technical Documentation

> **File:** [`foundry/src/DinCoordinator.sol`](../../../foundry/src/DinCoordinator.sol)
> **SPDX-License-Identifier:** UNLICENSED
> **Solidity:** `^0.8.28`
> **Deployment:** once per network behind an OpenZeppelin Transparent Proxy

---

## 1. Overview

`DinCoordinator` is the **DIN issuance hub and slasher administrator** of the DIN Protocol. Its responsibilities are:

1. **Faucet issuance** — accept ETH deposits and mint DIN at the `dinPerEth` rate (`depositAndMint`). The faucet can be capped (`mintCap`) and permanently retired (`retireFaucet`).
2. **Emission issuance** — mint the per-GI DIN emission subsidy on behalf of the wired `DinEmission` contract (`mintEmission`), under the same cap/retirement rules.
3. **Fee routing** — forward the ETH collected by the faucet to `DinFeeRouter` (`sweepFeesToRouter`), which splits it across validator pool / treasury / storage / public goods.
4. **Slasher management** — the privileged caller that registers or de-registers slasher contracts on `DinValidatorStake`, on behalf of the DIN-Representative.

The contract is configured through `initialize(address dinToken_)`. It does **not** deploy `DinToken`: the token proxy is deployed first and its address passed to `initialize`. Minting rights are granted separately by `DinToken.setCoordinator(coordinatorProxy)` — see [§10](#10-deployment--initialization-sequence).

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Initializable` | OpenZeppelin (upgradeable) | Initializer guard for the proxy pattern |
| `OwnableUpgradeable` | OpenZeppelin (upgradeable) | Admin access control (the DIN-Representative); owner set in `initialize` |
| `ReentrancyGuardTransient` | OpenZeppelin | Re-entrancy lock on the mint and ETH-forwarding paths |
| `DinToken` | Local | Token proxy reference, wired in `initialize` |
| `IDinValidatorStake` (local interface) | Local | `addSlasherContract` / `removeSlasherContract` calls |
| `IDinFeeRouter` (local interface) | Local | `routeFeeETH(payer)` call used by `sweepFeesToRouter` |

`ReentrancyGuardTransient` keeps its lock in EIP-1153 transient storage, so it occupies no persistent storage slots and is safe behind a proxy.

---

## 3. State Variables

| Variable | Type | Visibility | Description |
|----------|------|-----------|-------------|
| `dinToken` | `DinToken` | `public` | `DinToken` proxy. Set once in `initialize`. |
| `dinValidatorStakeContract` | `IDinValidatorStake` | `public` | Validator stake proxy. Set via `updateValidatorStakeContract`. |
| `dinPerEth` | `uint256` | `public` | Faucet rate: raw DIN units minted per 1 ETH, 1e18-scaled. Default `1,000,000 × 10¹⁸` (1M DIN per ETH). |
| `faucetRetired` | `bool` | `public` | One-way flag. Once `true`, `depositAndMint`, `mintEmission` and `setMintCap` all revert. |
| `mintCap` | `uint256` | `public` | Cap on `totalMinted`. `0` = uncapped (DevNet default). |
| `totalMinted` | `uint256` | `public` | DIN minted through this contract (faucet + emission combined). |
| `feeRouter` | `IDinFeeRouter` | `public` | Destination for `sweepFeesToRouter`. |
| `emissionContract` | `address` | `public` | The only address allowed to call `mintEmission` (the `DinEmission` proxy). |
| `__gap` | `uint256[50]` | `private` | Reserved storage slots for future variables. |

Slot order is recorded in [storage_layout.md](../storage_layout.md#dincoordinator).

---

## 4. Custom Errors

| Error | Condition |
|-------|-----------|
| `InvalidAddress()` | Zero address passed to `initialize`, `setFeeRouter`, slasher management, `updateValidatorStakeContract`, or `setEmissionContract` |
| `ValidatorStakeContractNotSet()` | Slasher management called before `dinValidatorStakeContract` is set |
| `ZeroValue()` | `depositAndMint` with `msg.value == 0`, `mintEmission` with `amount == 0`, or `updateDinPerEth(0)` |
| `FaucetRetired()` | `depositAndMint`, `mintEmission`, `setMintCap` or `retireFaucet` after the faucet was retired |
| `ZeroMintAmount()` | `depositAndMint` with a deposit so small that the computed DIN amount rounds to zero |
| `MintCapExceeded()` | A mint would push `totalMinted` above a non-zero `mintCap` |
| `FeeRouterNotSet()` | `sweepFeesToRouter` before `setFeeRouter` |
| `UnauthorizedEmissionCaller()` | `mintEmission` called by anything other than `emissionContract` |

---

## 5. Events

| Event | Parameters | Emitted When |
|-------|-----------|--------------|
| `EthDepositAndDINminted` | `address indexed user`, `uint256 ethAmount`, `uint256 mintAmount` | Successful `depositAndMint()` |
| `EmissionMinted` | `address indexed to`, `uint256 amount` | Successful `mintEmission()` |
| `FeesSweptToRouter` | `uint256 amount` | `sweepFeesToRouter()` forwarded a non-zero balance |
| `FeeRouterUpdated` | `address indexed feeRouter` | `setFeeRouter()` |
| `MintCapUpdated` | `uint256 newCap` | `setMintCap()` |
| `FaucetRetiredEvent` | — | `retireFaucet()` |
| `EmissionContractUpdated` | `address indexed emissionContract` | `setEmissionContract()` |
| `SlasherContractAdded` | `address indexed slasher` | Slasher registered on the stake contract |
| `SlasherContractRemoved` | `address indexed slasher` | Slasher de-registered |
| `ValidatorStakeContractUpdated` | `address indexed validatorStakeContract` | Stake contract reference updated |
| `DinPerEthUpdated` | `uint256 newRate` | Faucet rate changed |

---

## 6. Access Control

```
owner() — OwnableUpgradeable; the account that ran initialize (DIN-Representative)
  ├── sweepFeesToRouter()
  ├── setFeeRouter()
  ├── setMintCap()
  ├── retireFaucet()
  ├── setEmissionContract()
  ├── addSlasherContract()
  ├── removeSlasherContract()
  ├── updateValidatorStakeContract()
  └── updateDinPerEth()

emissionContract (the DinEmission proxy)
  └── mintEmission()

Any address (permissionless)
  └── depositAndMint()   ← payable, nonReentrant
```

A second control plane sits at the proxy level: the per-proxy **ProxyAdmin** that can upgrade the implementation. See [§9](#9-ownership--upgradeability).

---

## 7. Functions

### 7.1 Constructor & `initialize`

```solidity
constructor()
function initialize(address dinToken_) external initializer
```

- The constructor only calls `_disableInitializers()`, so the raw implementation can never be initialized or owned.
- `initialize` runs once, atomically with proxy deployment: reverts with `InvalidAddress()` on a zero token, sets `owner()` to the deployer, stores `dinToken`, and sets `dinPerEth = 1_000_000 * 1e18`.
- The coordinator is not a minter until `DinToken.setCoordinator(coordinatorProxy)` runs; before that, every mint reverts with `DinToken.Unauthorized()`.

---

### 7.2 `depositAndMint` — Faucet

```solidity
function depositAndMint() external payable nonReentrant
```

1. Revert `FaucetRetired()` if the faucet is retired; revert `ZeroValue()` if `msg.value == 0`.
2. `mintAmount = (msg.value × dinPerEth) / 10¹⁸` — e.g. 1 ETH → `1_000_000 × 10¹⁸` raw DIN units at the default rate. Revert `ZeroMintAmount()` if this rounds to zero.
3. Revert `MintCapExceeded()` if `mintCap > 0 && totalMinted + mintAmount > mintCap`.
4. `totalMinted += mintAmount`, `dinToken.mint(msg.sender, mintAmount)`, emit `EthDepositAndDINminted`.

The ETH stays in the coordinator until `sweepFeesToRouter()` forwards it.

---

### 7.3 `mintEmission` — Emission Subsidy

```solidity
function mintEmission(address to, uint256 amount) external nonReentrant
```

1. Revert `UnauthorizedEmissionCaller()` unless `msg.sender == emissionContract`.
2. Revert `FaucetRetired()` if the faucet is retired; revert `ZeroValue()` if `amount == 0`.
3. Revert `MintCapExceeded()` under the same cap rule as the faucet.
4. `totalMinted += amount`, `dinToken.mint(to, amount)`, emit `EmissionMinted`.

`to` is the `DinEmission` contract itself: `DinEmission.fundGI(gi, taskAuditor)` mints to itself, approves, and calls `DINTaskAuditor.depositRewards(gi, amount)` to fund that GI's reward pool. Emission deliberately shares the faucet's supply controls: `mintCap` bounds faucet + emission together, and **retiring the faucet also stops emission**.

---

### 7.4 `sweepFeesToRouter`

```solidity
function sweepFeesToRouter() external onlyOwner nonReentrant
```

Reverts `FeeRouterNotSet()` if no router is wired; returns silently on a zero balance. Otherwise forwards the whole ETH balance via `feeRouter.routeFeeETH{value: balance}(address(this))` and emits `FeesSweptToRouter`. The router only accepts the call if the coordinator is on its fee-source allowlist (`DinFeeRouter.addFeeSource`, done by the deploy script). There is no direct ETH withdrawal to an address.

---

### 7.5 Supply controls: `setMintCap`, `retireFaucet`

```solidity
function setMintCap(uint256 newCap) external onlyOwner
function retireFaucet() external onlyOwner
```

- `setMintCap` sets the cap on `totalMinted` (`0` = uncapped); reverts `FaucetRetired()` after retirement. Setting a cap below the current `totalMinted` is allowed and simply blocks all further mints.
- `retireFaucet` flips `faucetRetired` to `true` permanently (reverts `FaucetRetired()` if already retired) and emits `FaucetRetiredEvent`.

---

### 7.6 Wiring setters

```solidity
function setFeeRouter(address feeRouter_) external onlyOwner
function setEmissionContract(address emissionContract_) external onlyOwner
function updateValidatorStakeContract(address validatorStakeContract) external onlyOwner
function updateDinPerEth(uint256 newRate) external onlyOwner
```

All reject the zero address (`updateDinPerEth` rejects a zero rate with `ZeroValue()`) and emit their matching event. None is one-shot: the owner can re-point any of them at any time.

---

### 7.7 Slasher management

```solidity
function addSlasherContract(address slasherContract) external onlyOwner
function removeSlasherContract(address slasherContract) external onlyOwner
```

Delegate to `dinValidatorStakeContract.addSlasherContract` / `removeSlasherContract` after checking `slasherContract != address(0)` and that the stake contract is set. Used by the DIN-Representative to authorise each model's `DINTaskCoordinator` and `DINTaskAuditor` (`dincli dinrep add-slasher`).

---

## 8. Issuance Economics

| Parameter | Default | Description |
|-----------|---------|-------------|
| `dinPerEth` | `1,000,000 × 10¹⁸` | Faucet rate (1 ETH → 1M DIN); owner-adjustable |
| `mintCap` | `0` (uncapped) | Cap on faucet + emission mints combined |
| `faucetRetired` | `false` | One-way switch that ends faucet **and** emission minting |
| Faucet ETH | forwarded by `sweepFeesToRouter` | Split by `DinFeeRouter`'s ETH split (default 95% validator pool / 5% treasury) |

The testnet values for `mintCap`, `dinPerEth` and the emission schedule are open decisions (issue #155).

---

## 9. Ownership & Upgradeability

| Plane | Who | Controls |
|-------|-----|----------|
| Contract owner (`owner()`) | Account that ran `initialize` (DIN-Representative) | Everything in §6 except `depositAndMint` / `mintEmission`; transferable via `transferOwnership` |
| Proxy admin (`ProxyAdmin`) | One ProxyAdmin per proxy (OZ v5), created at proxy deployment and owned by the deployer | Swapping the implementation |

- **Upgrade path:** `cd foundry && CONTRACT=DinCoordinator forge script script/UpgradePlatform.s.sol --rpc-url <rpc> --broadcast ...` — reads the proxy address from `foundry/deployments/<network>.json` (see [UpgradePlatform](foundry/script/UpgradePlatform.md)).
- **Storage-layout safety:** variables are append-only above `__gap`; `foundry/test/UpgradeValidation.t.sol` runs `Upgrades.validateImplementation`, and `DinCoordinatorUpgradeTest` in `foundry/test/DeployPlatform.t.sol` upgrades to `foundry/src/upgrade/DinCoordinatorV2.sol` and checks rate, wiring and access control survive.
- **Trust implication:** every rule here holds only while the ProxyAdmin owner is honest — an upgrade can replace any of it. There is no timelock.

---

## 10. Deployment & Initialization Sequence

Automated by `foundry/script/DeployPlatform.s.sol` (see [DeployPlatform](foundry/script/DeployPlatform.md)). The steps that touch the coordinator:

```
2.  Deploy DinToken proxy          → initialize()
3.  Deploy DinFeeRouter proxy      → initialize(dinToken, dinTreasury)
4.  Deploy DinCoordinator proxy    → initialize(dinToken)
5.  dinToken.setCoordinator(dinCoordinator)            ← grants minting rights (one-shot)
6.  dinCoordinator.setFeeRouter(dinFeeRouter)
    dinFeeRouter.addFeeSource(dinCoordinator)          ← lets sweepFeesToRouter through
7.  Deploy DinValidatorStake proxy → initialize(dinToken, dinCoordinator)
8.  dinCoordinator.updateValidatorStakeContract(dinValidatorStake)
13. Deploy DinEmission proxy       → initialize(dinCoordinator, dinToken, schedule…)
14. dinCoordinator.setEmissionContract(dinEmission)
15. dinCoordinator.updateDinPerEth / setMintCap       ← only when DIN_PER_ETH / MINT_CAP are set to non-default values

Later, per model (dincli dinrep add-slasher):
    dinCoordinator.addSlasherContract(taskCoordinator)
    dinCoordinator.addSlasherContract(taskAuditor)
```

| Missing step | Symptom |
|--------------|---------|
| 5 (`setCoordinator`) | Every mint reverts with `DinToken.Unauthorized()` |
| 6 (router wiring) | `sweepFeesToRouter` reverts `FeeRouterNotSet()` (or `NotFeeSource` on the router) |
| 8 (`updateValidatorStakeContract`) | Slasher management reverts `ValidatorStakeContractNotSet()` |
| 14 (`setEmissionContract`) | `mintEmission` reverts `UnauthorizedEmissionCaller()` |

---

## 11. Security Considerations

| Risk | Mitigation |
|------|-----------|
| Re-entrancy on mint / ETH forwarding | `nonReentrant` on `depositAndMint`, `mintEmission`, `sweepFeesToRouter` |
| Unbounded supply | Optional `mintCap` over faucet + emission; `retireFaucet` ends issuance permanently |
| Rogue emission mints | Only `emissionContract` can call `mintEmission`; setting it is `onlyOwner` |
| Rogue slasher registration | `onlyOwner` on add/remove slasher |
| Rate manipulation | Only `owner` can call `updateDinPerEth` |
| ETH diverted | ETH leaves only through `sweepFeesToRouter` to the configured router; no arbitrary-recipient withdrawal |
| Re-initialization / implementation hijack | `initializer` + `_disableInitializers()` |
| Malicious upgrade | Bounded only by ProxyAdmin key security; no timelock |

---

## 12. Interactions with Other Contracts

```
DinCoordinator (proxy)
  ├── → DinToken.mint(user, amount)                 [depositAndMint]
  ├── → DinToken.mint(to, amount)                   [mintEmission, from DinEmission]
  ├── → DinFeeRouter.routeFeeETH{value}(this)       [sweepFeesToRouter]
  ├── → DinValidatorStake.addSlasherContract()
  └── → DinValidatorStake.removeSlasherContract()

DinEmission → DinCoordinator.mintEmission()         [per-GI emission]
DinToken.setCoordinator(dinCoordinator)             [one-shot minter wiring]
```

---

## 13. Change Log

### P3 — supply controls, emission, fee routing (foundry)

- **Removed** `withdraw()` and its `TransferFailed` error; faucet ETH now leaves only via `sweepFeesToRouter()` to `DinFeeRouter` (new `feeRouter`, `setFeeRouter`, `FeeRouterNotSet`, `FeeRouterUpdated`, `FeesSweptToRouter`).
- Added supply controls: `mintCap` / `setMintCap` / `MintCapExceeded` / `MintCapUpdated`, `totalMinted`, and the one-way `faucetRetired` / `retireFaucet` / `FaucetRetired` / `FaucetRetiredEvent`.
- Added emission minting: `emissionContract` / `setEmissionContract` / `mintEmission` with `UnauthorizedEmissionCaller`, `EmissionContractUpdated`, `EmissionMinted`.

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy (`Initializable` + `OwnableUpgradeable`, `_disableInitializers()` constructor, `initialize(address dinToken_)`).
- No longer deploys `DinToken`; minting rights granted via `DinToken.setCoordinator`.
- `dinToken` lost `immutable`; `dinPerEth` default moved into `initialize`; added `uint256[50] __gap`.

---

## 14. Review Notes & Open Caveats

- **No. 1 — Retiring the faucet also stops emission:** `mintEmission` checks `faucetRetired`, so `retireFaucet()` ends *all* issuance through this contract, not only the ETH faucet. Intended per the NatSpec ("emission cannot bypass the supply cap machinery"), but easy to miss operationally.
- **No. 2 — Swept ETH mostly stays in the router:** `dincli dinrep coordinator sweep-fees` calls `sweepFeesToRouter()`. With the default split only the treasury share is paid out; the validator-pool share accrues in `DinFeeRouter`, which has no withdrawal path yet.
- **No. 3 — Ownership is claimed at initialization:** whoever runs the deploy script becomes `owner()`; transfer is a deliberate runbook step.
- **No. 4 — Wiring setters have no one-shot guard:** `setFeeRouter`, `setEmissionContract`, `updateValidatorStakeContract` can be re-pointed at any time.
- **No. 5 — Upgrade power is absolute:** the ProxyAdmin owner can replace all logic, with no timelock.
