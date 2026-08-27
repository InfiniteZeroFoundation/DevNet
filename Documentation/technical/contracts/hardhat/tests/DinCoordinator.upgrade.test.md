# DinCoordinator.upgrade.test.ts — Test Documentation

> **File:** `hardhat/test/DinCoordinator.upgrade.test.ts`
> **Subject under test:** `DinCoordinator` upgrade safety (Transparent Proxy)
> **Run:** `cd hardhat && npx hardhat test test/DinCoordinator.upgrade.test.ts`

---

## 1. Purpose

Verifies that upgrading the `DinCoordinator` proxy to a new implementation preserves state, wiring, and access control. The upgrade target is the [`DinCoordinatorV2`](../upgrades/DinCoordinatorV2.md) fixture — a V1 subclass whose only addition is `version() == 2`, used purely to prove the swap happened.

Every test deploys the full platform via [`test/helpers/platform.ts`](helpers/platform.md), then upgrades with `upgradeTransparentProxy` from [`deploy/helpers.ts`](../deploy/helpers.md).

---

## 2. Test Cases

| Test | Scenario | Asserts |
|------|----------|---------|
| preserves exchange rate and token wiring across upgrade | Sets a non-default `dinPerEth` (2M), mints DIN via `depositAndMint`, runs `upgrades.validateUpgrade` then upgrades | `dinToken` reference, custom `dinPerEth`, and user token balance all survive; `version() == 2` |
| keeps owner-only functions restricted after upgrade | Upgrade, then non-owner calls `updateDinPerEth` | Reverts `OwnableUnauthorizedAccount` |
| keeps slasher management wired to stake contract after upgrade | Registers a `MockSlasher` via the coordinator pre-upgrade, upgrades | `dinValidatorStake.isSlasherContract` still `true` — the coordinator→stake wiring survives |
| implementation contract cannot be initialized directly | Deploys the raw (unproxied) implementation and calls `initialize` | Reverts `InvalidInitialization` — proves `_disableInitializers()` in the constructor works |

---

## 3. What the Suite Establishes

- **Storage-layout compatibility** is machine-checked via `upgrades.validateUpgrade(proxy, V2, { kind: "transparent" })` before the first upgrade — a layout-shifting V2 would fail the test rather than silently corrupt state.
- **Cross-contract wiring is proxy-address-based**, so upgrading the coordinator does not disturb its registration with the stake contract or the token.
- **Implementation-hijack protection** is covered explicitly (last test), mirroring the same test in each of the other upgrade suites.

## 4. Coverage Gaps

- No test that `withdraw()` still works post-upgrade, and no test of upgrading *while* ETH is held in the proxy (the balance lives at the proxy address, so it should be unaffected — but it is asserted nowhere).
- The upgrade is always executed by the deployer/ProxyAdmin owner; there is no negative test that a non-admin cannot upgrade (that guarantee is delegated to OZ's ProxyAdmin).
