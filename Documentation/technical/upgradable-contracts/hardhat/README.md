# Upgradeable Platform Contracts — Design & Architecture

**Source tree:** `hardhat/contracts/` (branch `feature/platform-upgradeable`, PR #13)
**Toolchain:** Hardhat + `@openzeppelin/hardhat-upgrades`, solc 0.8.28, EVM `cancun`
**Proxy pattern:** OpenZeppelin **Transparent Proxy** (`PROXY_KIND = "transparent"`)

This document explains how and why the four DIN platform contracts were converted from plain constructor-initialized contracts to an upgradeable proxy architecture, contract by contract. The companion test documentation lives in [`test/`](./test/README.md).

---

## 1. Which contracts are upgradeable, and which deliberately are not

| Contract | Upgradeable | Rationale |
|---|---|---|
| `DinToken` | ✅ Transparent Proxy | Platform-level, deployed once per network. Token balances must survive logic upgrades. |
| `DinCoordinator` | ✅ Transparent Proxy | Platform-level hub for ETH↔DIN exchange and slasher administration. Its address is referenced by every other contract and by `dincli` — must be stable forever. |
| `DinValidatorStake` | ✅ Transparent Proxy | Holds all validator stake. Slashing logic will evolve; stake balances must persist. |
| `DINModelRegistry` | ✅ Transparent Proxy | Long-lived registry of models and fee state. |
| `DINTaskCoordinator` | ❌ Plain `Ownable` | Deployed **per model** by the model owner. Its lifecycle is bounded by the model's; a redeploy is the upgrade path. |
| `DINTaskAuditor` | ❌ Plain `Ownable` | Same per-model lifecycle as its paired task coordinator. |
| `DINShared.sol` | n/a | Types, cross-contract interfaces, and custom errors only — no deployed state. |

The dividing line is **lifecycle, not importance**: contracts deployed once per network and accumulating protocol-wide state get proxies; contracts deployed per model are disposable by design and stay plain.

## 2. Why Transparent Proxy over UUPS

- **A bad V2 cannot brick the proxy.** With UUPS, the upgrade function lives in the implementation — an implementation that omits or breaks `_authorizeUpgrade` permanently freezes the proxy. With Transparent Proxy, upgrade authority lives in a separate `ProxyAdmin` contract that no implementation bug can touch.
- **Fits the current governance model.** Upgrades are controlled by a single DIN-Representative EOA today. `ProxyAdmin` ownership can be transferred to a multisig or DAO later without touching any implementation.
- **Cost trade-off accepted.** Transparent proxies pay a small per-call gas overhead for the admin check; for an early-stage protocol this is a fair price for the safety property above.

Every deploy and upgrade flows through two shared helpers (`hardhat/deploy/helpers.ts`):

```ts
deployTransparentProxy(factory, initArgs)   // upgrades.deployProxy(..., { kind: "transparent" })
upgradeTransparentProxy(proxyAddr, factory) // upgrades.upgradeProxy(..., { kind: "transparent" })
```

`PROXY_KIND` is a single constant (`hardhat/deploy/constants.ts`) so the pattern cannot silently diverge between scripts and tests.

## 3. The conversion pattern (applied to all four contracts)

Each platform contract follows the same recipe:

1. **Inheritance switched to upgradeable variants.** `Ownable` → `OwnableUpgradeable`, `ERC20` → `ERC20Upgradeable`, plus `Initializable`.
2. **Constructor replaced by `initialize()`.** The constructor now does exactly one thing:
   ```solidity
   /// @custom:oz-upgrades-unsafe-allow constructor
   constructor() { _disableInitializers(); }
   ```
   `_disableInitializers()` permanently locks the *implementation* contract so an attacker can never call `initialize()` on it directly and claim ownership. All real initialization happens through the proxy via `initialize(...)` guarded by the `initializer` modifier (one-shot).
3. **`immutable` variables converted to storage.** Immutables are embedded in implementation bytecode, not proxy storage — they cannot exist in an upgradeable contract. `DinValidatorStake`'s `DIN_TOKEN` / `DIN_COORDINATOR` kept their ALL_CAPS names when converted to storage, deliberately, to avoid a silent ABI break for existing callers.
4. **Field defaults moved into `initialize()`.** Declaration-site initializers (e.g. fee defaults) run at implementation deployment, writing to implementation storage the proxy never reads. All defaults are assigned inside `initialize()` so they land in proxy storage.
5. **Storage gap appended.** Every contract ends its variable block with:
   ```solidity
   uint256[50] private __gap;
   ```
   reserving 50 slots for future variables without shifting anything below in the inheritance chain.
6. **Reentrancy protection via `ReentrancyGuardTransient`.** `DinCoordinator` and `DinValidatorStake` use the transient-storage variant (EIP-1153 `TSTORE`/`TLOAD`, hence the `cancun` EVM requirement). Because the lock lives in transient storage, it occupies **zero** persistent slots — no storage-layout impact and no `__ReentrancyGuard_init()` call needed.

Full slot-by-slot inventories and the append-only upgrade rules are in `Developer/Documentation/technical/storage_layout.md`.

## 4. Contract-by-contract design

### 4.1 DinToken (`DinToken.sol`, 61 lines)

ERC-20 (`"DIN Token"` / `DIN`) minted exclusively in exchange for ETH deposits.

- **State:** one contract-own variable — `address public coordinator` — plus the OZ ERC-20 storage inherited from `ERC20Upgradeable`.
- **`initialize()`** takes no arguments: registers name/symbol and makes the deployer owner.
- **`setCoordinator(address)` is one-shot** (`CoordinatorAlreadySet` guard). This replaces the old design where `DinCoordinator`'s constructor deployed the token inline. The one-shot constraint is intentional: the coordinator sits behind its own Transparent Proxy, so its address never changes across upgrades — allowing re-pointing would only add attack surface. Changing coordinators would require deploying a new token proxy, by design.
- **`mint(to, amount)`** is restricted to the wired coordinator (`onlyCoordinator` → `Unauthorized`).

**Key design consequence:** token and coordinator are now two separate proxies wired *after* deployment. Any tooling that assumed "deploy coordinator ⇒ token address available" (the old inline-`new DinToken()` pattern) must adopt the two-step wiring (see §5).

### 4.2 DinCoordinator (`DinCoordinator.sol`, 121 lines)

Central hub for the ETH→DIN exchange and slasher administration.

- **State:** `dinToken` (typed `DinToken` reference), `dinValidatorStakeContract` (via a minimal local `IDinValidatorStake` interface), `dinPerEth` exchange rate (1e18-scaled, default 1,000,000 DIN/ETH set in `initialize`).
- **`initialize(address dinToken_)`** — takes the token proxy address; rejects zero address.
- **`depositAndMint()`** (payable, `nonReentrant`) converts ETH to DIN at `dinPerEth` and mints via the token proxy.
- **`withdraw()`** sends the ETH balance to the owner using the `call{value:}` pattern with a `TransferFailed` revert (not `transfer()`, which forwards too little gas for some receivers).
- **Slasher administration:** `addSlasherContract` / `removeSlasherContract` (owner-only) forward to `DinValidatorStake`. This is the choke point the DIN-Representative uses to authorize per-model task contracts as slashers before model registration.
- **`updateValidatorStakeContract`** is *not* one-shot (unlike `DinToken.setCoordinator`) — documented in-code as an operational responsibility of the owner. It is called once during deployment wiring.

Known accepted trade-off: the concrete `import "./DinToken.sol"` coupling (rather than an interface) was reviewed and left as a low-priority open item.

### 4.3 DinValidatorStake (`DinValidatorStake.sol`, 340 lines)

Validator staking, unbonding, slashing, and blacklisting. The most behavior-rich platform contract.

- **State:** `DIN_TOKEN` (IERC20) and `DIN_COORDINATOR` (address) — former immutables, now storage set in `initialize(dinToken, dinCoordinator)`; `slasherContracts` mapping; `validators` mapping of `ValidatorInfo` structs.
- **`ValidatorInfo`:** `activeStake`, `pendingWithdrawals`, `withdrawAvailableAt` (uint64), `jailedUntil` (uint64), and a `ValidatorStatus` enum (`None / Active / Exiting / Jailed / Blacklisted`). Status is derived, not directly set: the private `_syncValidatorStatus` recomputes it after every state change (blacklist and unexpired jail take precedence; pending withdrawal ⇒ `Exiting`; stake ≥ `MIN_STAKE` ⇒ `Active`).
- **Constants:** `MIN_STAKE = 10 DIN`, `UNBONDING_PERIOD = 7 days`. `constant`s live in bytecode, not storage — they are proxy-safe and can even change across upgrades.
- **Staking flow:** `stake(amount)` (≥ `MIN_STAKE`, SafeERC20 pull) → `unstake(amount)` moves stake to a *single* pending withdrawal with a 7-day unbonding clock (`PendingWithdrawalExists` blocks a second one) → `claimUnstaked()` transfers after maturity.
- **Slashing:** `slash(validator, amount, reason)` is callable only by registered slasher contracts (the per-model task contracts, registered via the coordinator). Design points:
  - **Active stake is consumed first, then pending withdrawals** — unbonding funds remain slashable for the full 7-day window, closing the "unstake ahead of the slash" escape.
  - **Capped, not reverting:** if slashable stake < requested amount, the function slashes what exists and returns the actual amount, so a task contract's slashing round can't be bricked by one under-collateralized validator.
- **Blacklisting** (owner-only) blocks stake/unstake/claim; `unblacklistValidator` restores `Jailed` if a jail term is still running, otherwise recomputes status.

### 4.4 DINModelRegistry (`DINModelRegistry.sol`, 497 lines)

Model registration requests, manifest updates, fee tiers, and per-model disable switches.

- **State:** `dinValidatorStake` reference; four fee variables (defaults set in `initialize`, per rule §3.4); `models` / `modelRequests` / `manifestRequests` arrays; reverse-lookup mappings storing `modelId + 1` so `0` means "not registered"; `modelDisabled` mapping.
- **Registration is request/approve:** `requestModelRegistration` (fee-paying) validates that both task contracts are currently authorized slashers and owned by the requester; `approveModel` (owner-only) **re-validates all four conditions at approval time** — slasher status or task-contract ownership changing between request and approval causes a typed revert (`CoordinatorNoLongerSlasher`, `AuditorOwnershipChanged`, …). This closes the TOCTOU gap between submission and review.
- **Manifest updates** follow the same request/approve pattern with their own fee tier, gated by `onlyModelOwner` + `notDisabled`.
- **Fees:** individual setters plus an atomic `setFees(...)`; `withdrawFees` uses the `call{value:}` + `TransferFailed` pattern.
- **Access-model migration + compatibility shims.** The pre-upgrade contract used a bespoke `daoAdmin` field. The upgradeable version standardizes on `OwnableUpgradeable`, but preserves the old ABI surface with two read-through shims:
  ```solidity
  function daoAdmin() external view returns (address) { return owner(); }
  function setDAOAdmin(address newAdmin) external onlyOwner {
      transferOwnership(newAdmin);         // + emits DAOAdminUpdated
  }
  ```
  `dincli` and off-chain indexers keep working unchanged; the `DAOAdminUpdated` event is still emitted for listeners.

## 5. Deployment order and wiring

Proxies cannot use the old nested `new DinToken()` pattern, so bootstrap is an explicit 6-step sequence (implemented in `hardhat/scripts/deploy-platform.ts`, mirrored by the `deployPlatform()` test fixture):

```
1. Deploy DinToken proxy            → initialize()
2. Deploy DinCoordinator proxy      → initialize(dinTokenAddress)
3. DinToken.setCoordinator(dinCoordinatorAddress)          // one-shot
4. Deploy DinValidatorStake proxy   → initialize(dinTokenAddress, dinCoordinatorAddress)
5. DinCoordinator.updateValidatorStakeContract(stakeAddress)
6. Deploy DINModelRegistry proxy    → initialize(stakeAddress)
```

The order resolves the circular token↔coordinator dependency: the token must exist before the coordinator's `initialize` (step 2), and the coordinator must exist before the token will mint for it (step 3). The deploy script records all proxy addresses **plus the `ProxyAdmin` address** to `hardhat/deployments/<network>.json`.

**Upgrades** run through `hardhat/scripts/upgrade-platform.ts` (`CONTRACT=DinToken npx hardhat run ...`), which loads the proxy address from the deployments file, upgrades via the OZ plugin (which internally validates storage-layout compatibility), and appends the new implementation address to the deployments JSON for auditability.

## 6. Upgrade-safety machinery

- **`contracts/upgrade/*V2.sol`** — four minimal V2 contracts (`DinTokenV2`, `DinCoordinatorV2`, `DinValidatorStakeV2`, `DINModelRegistryV2`), each just `contract XV2 is X { function version() external pure returns (uint256) { return 2; } }` with two annotations:
  - `@custom:oz-upgrades-from X` — tells the OZ plugin which contract this upgrades, enabling the storage-layout diff;
  - `@custom:oz-upgrades-unsafe-allow missing-initializer` — intentional: V2 adds no new state so it reuses V1's initializer; a `reinitializer(2)` would only be needed if V2 introduced storage requiring one-time setup.

  These exist to *exercise the upgrade path in tests*, not as real planned upgrades.
- **`contracts/mocks/MockSlasher.sol`** — a bare `Ownable` contract used wherever tests need "a contract with an `owner()`" to stand in for task contracts in slasher/registry flows.
- **`upgrades.validateUpgrade()`** is invoked in every upgrade test suite before upgrading, so any storage-layout regression (reordered/removed variable, shrunk gap misuse) fails CI before it could ever reach a live proxy.

## 7. Operational invariants for future upgrades

1. Never reorder, remove, or retype existing state variables; append only, consuming `__gap` slots.
2. Keep `_disableInitializers()` in every implementation constructor.
3. New one-time setup in a V(n+1) requires `reinitializer(n+1)` — do not reuse `initializer`.
4. Run `validateUpgrade()` (tests do this automatically) before any live upgrade.
5. `ProxyAdmin` ownership is the real upgrade key — its custody (currently the DIN-Representative EOA, later a multisig) is a governance concern tracked outside this document.

## 8. Test coverage map

Each platform contract has a dedicated upgrade-safety suite covering the same three axes — **state persistence across upgrade**, **access control after upgrade**, **direct-implementation initialization blocked** — plus `validateUpgrade()` storage checks. `DinValidatorStake` additionally has a 16-test behavioral suite. Per-file walkthroughs:

| Test file | Doc |
|---|---|
| `test/helpers/platform.ts` (shared fixture) | [test/helpers-platform.md](./test/helpers-platform.md) |
| `test/DinToken.upgrade.test.ts` | [test/DinToken.upgrade.test.md](./test/DinToken.upgrade.test.md) |
| `test/DinCoordinator.upgrade.test.ts` | [test/DinCoordinator.upgrade.test.md](./test/DinCoordinator.upgrade.test.md) |
| `test/DinValidatorStake.upgrade.test.ts` | [test/DinValidatorStake.upgrade.test.md](./test/DinValidatorStake.upgrade.test.md) |
| `test/DINModelRegistry.upgrade.test.ts` | [test/DINModelRegistry.upgrade.test.md](./test/DINModelRegistry.upgrade.test.md) |
| `test/DinValidatorStake.test.ts` (behavioral) | [test/DinValidatorStake.test.md](./test/DinValidatorStake.test.md) |

Run everything with `cd hardhat && npm test` — expected: **32 passing**.
