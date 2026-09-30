# Upgradeable Platform Contracts — Foundry (Reference)

**Source tree:** `foundry/src/` — the reference implementation
**Toolchain:** Foundry (`forge`), solc 0.8.28 with `via_ir = true`, `openzeppelin-foundry-upgrades` (runs `@openzeppelin/upgrades-core` through `npx`, so run `npm ci` in `foundry/` first)
**Proxy pattern:** OpenZeppelin **Transparent Proxy**, one ProxyAdmin per proxy (OZ v5)

This document covers how the DIN platform contracts are made upgradeable, and the tooling that deploys, upgrades and validates them. For the older Hardhat version of the same material (four contracts, PR #13 era) see [`../hardhat/README.md`](../hardhat/README.md). The design decision for how `dincli` should eventually deploy proxies is recorded in [proxy-deployment-architecture.md](../proxy-deployment-architecture.md).

---

## 1. Which contracts are upgradeable

| Contract | Upgradeable | Rationale |
|---|---|---|
| `DinTreasury` | ✅ Transparent Proxy | Holds protocol ETH/DIN; its address is wired into the fee router and stake contract |
| `DinToken` | ✅ | Balances must survive logic upgrades |
| `DinCoordinator` | ✅ | Faucet/emission minting hub and slasher administrator; referenced everywhere |
| `DinFeeRouter` | ✅ | Fee split logic will evolve; accrued balances must persist |
| `DinValidatorStake` | ✅ | Custodies all validator stake; slashing logic will evolve |
| `DINModelRegistry` | ✅ | Long-lived model and fee state |
| `DinEmission` | ✅ | Emission schedule state per task auditor |
| `DinFairLaunchDistributor` | ✅ (separate script) | Vesting state; deployed by [DeployFairLaunchDistributor](../../contracts/foundry/script/DeployFairLaunchDistributor.md) |
| `DINTaskCoordinator`, `DINTaskAuditor` | ❌ plain `Ownable` | Deployed per model by the model owner; a redeploy is the upgrade path |
| `DINShared.sol` | n/a | Types, interfaces, errors only |

The dividing line is lifecycle: contracts deployed once per network and holding protocol-wide state get proxies; per-model contracts stay plain.

## 2. Why Transparent Proxy (not UUPS)

- **A bad implementation cannot brick the proxy.** Upgrade authority lives in a separate ProxyAdmin, not in implementation code that a buggy V2 could break.
- **Governance fits.** ProxyAdmins are owned by the DIN-Representative today and can be transferred to a multisig or timelock without touching implementations.
- **Cost accepted.** There is a small per-call admin-check overhead.

## 3. Conversion recipe (all platform contracts)

1. Upgradeable bases: `Initializable`, `OwnableUpgradeable` (+ `ERC20Upgradeable` for the token). OZ v5 stores their state in namespaced ERC-7201 slots.
2. Constructor only calls `_disableInitializers()` (annotated `@custom:oz-upgrades-unsafe-allow constructor`); all setup is in a one-shot `initialize(...)`.
3. No `immutable`s: `DinValidatorStake`'s `DIN_TOKEN` / `DIN_COORDINATOR` are storage with their old ALL_CAPS names kept.
4. Defaults (fees, rates, parameters) are assigned in `initialize`, not at declaration.
5. A trailing `uint256[50] __gap` in every platform contract.
6. `ReentrancyGuardTransient` (EIP-1153 transient storage — no slots, no init call) where re-entrancy guards are needed.

Slot-by-slot inventories: [storage_layout.md](../../storage_layout.md).

## 4. Deploy, upgrade, validate

| Task | Tool | Doc |
|------|------|-----|
| Deploy + wire all seven proxies | [`foundry/script/DeployPlatform.s.sol`](../../../../foundry/script/DeployPlatform.s.sol) | [DeployPlatform](../../contracts/foundry/script/DeployPlatform.md) |
| Import addresses into dincli | `dincli system import-deployments` (reads `foundry/deployments/<network>.json`) | [DeployPlatform — Usage](../../contracts/foundry/script/DeployPlatform.md#usage) |
| Upgrade one proxy (to its `<Name>V2`) | [`foundry/script/UpgradePlatform.s.sol`](../../../../foundry/script/UpgradePlatform.s.sol) | [UpgradePlatform](../../contracts/foundry/script/UpgradePlatform.md) |
| Per-network deployments file | [`foundry/script/DeploymentsPath.sol`](../../../../foundry/script/DeploymentsPath.sol) | [DeploymentsPath](../../contracts/foundry/script/DeploymentsPath.md) |
| V2 upgrade fixtures | `foundry/src/upgrade/*V2.sol` | [V2 fixtures](../../contracts/foundry/upgrades/V2-fixtures.md) |

The contract-by-contract behavior (initializers, wiring, access control, ownership planes) is documented in each contract's page under [`contracts/`](../../contracts/): [DinToken](../../contracts/DinToken.md), [DinCoordinator](../../contracts/DinCoordinator.md), [DinValidatorStake](../../contracts/DinValidatorStake.md), [DINModelRegistry](../../contracts/DINModelRegistry.md).

## 5. Upgrade-safety tests

| Test | What it checks |
|------|----------------|
| [`foundry/test/UpgradeValidation.t.sol`](../../../../foundry/test/UpgradeValidation.t.sol) | `Upgrades.validateImplementation` on all seven platform implementations (initializer, storage and unsafe-pattern rules) |
| [`foundry/test/DeployPlatform.t.sol`](../../../../foundry/test/DeployPlatform.t.sol) — `ProxyWiringTest` | Every wiring edge from the deploy sequence; all ProxyAdmins owned by the deployer; faucet mint through the proxy |
| [`foundry/test/DeployPlatformScript.t.sol`](../../../../foundry/test/DeployPlatformScript.t.sol) — `DeployPlatformScriptTest` | Runs the script's own `deploy()` with default and overridden tokenomics; every contract and ProxyAdmin owned by the deployer; invalid overrides revert the deploy |
| `DeployPlatform.t.sol` — `ReInitializerProtectionTest` | A second `initialize` on each proxy, and a direct `initialize` on each implementation, both revert |
| `DeployPlatform.t.sol` — `DinTokenUpgradeTest`, `DinCoordinatorUpgradeTest`, `DinValidatorStakeUpgradeTest`, `DINModelRegistryUpgradeTest` | Upgrade to the V2 fixture with `Upgrades.upgradeProxy` (validation included); state and access control survive |

```bash
cd foundry && npm ci
forge test --match-contract 'UpgradeValidationTest|ProxyWiringTest|ReInitializerProtectionTest|UpgradeTest'
```

`npm ci` must come first: the upgrade validations shell out to `npx @openzeppelin/upgrades-core`. Without a populated `node_modules`, parallel tests race each other fetching it.

## 6. Operational invariants for future upgrades

1. Append only; never reorder, remove or retype state. Consume `__gap` slots once a proxy holds live state (see [storage_layout.md](../../storage_layout.md) for the current pre-deployment practice).
2. Keep `_disableInitializers()` in every implementation constructor.
3. New one-time setup needs `reinitializer(n)`, not `initializer`.
4. Diff `forge inspect <Contract> storage-layout` old vs new, and run `Upgrades.validateUpgrade` against the live proxy before upgrading.
5. The ProxyAdmin owner is the real upgrade key. Custody is currently the DIN-Representative's single key; on-chain governance is deferred to post-mainnet.

## 7. Gaps

- `UpgradePlatform.s.sol` and the V2 fixtures cover only `DinToken`, `DinCoordinator`, `DinValidatorStake` and `DINModelRegistry`. `DinTreasury`, `DinFeeRouter` and `DinEmission` have implementation validation but no upgrade round-trip test or upgrade script mapping.
- dincli cannot deploy proxies itself yet (planned: [dincli-native-proxy-deployment.md](../../../../Developer/issues/dincli-native-proxy-deployment.md)).
