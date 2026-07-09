# Hardhat Test Suite — Documentation Index

Documentation for the test files in `hardhat/test/` on the `feature/platform-upgradeable` branch (PR #13). Run with `cd hardhat && npm test` — expected **32 passing** (16 upgrade-safety + 16 behavioral).

| Doc | Source file | Tests | Focus |
|---|---|---|---|
| [helpers-platform.md](./helpers-platform.md) | `test/helpers/platform.ts` | (fixture) | Shared 6-step proxy deployment fixture + DIN minting helper |
| [DinToken.upgrade.test.md](./DinToken.upgrade.test.md) | `test/DinToken.upgrade.test.ts` | 4 | Token balance/wiring persistence, mint auth, init lock |
| [DinCoordinator.upgrade.test.md](./DinCoordinator.upgrade.test.md) | `test/DinCoordinator.upgrade.test.ts` | 4 | Exchange-rate/wiring persistence, owner auth, slasher wiring |
| [DinValidatorStake.upgrade.test.md](./DinValidatorStake.upgrade.test.md) | `test/DinValidatorStake.upgrade.test.ts` | 4 | Stake persistence, coordinator/owner auth, init lock |
| [DINModelRegistry.upgrade.test.md](./DINModelRegistry.upgrade.test.md) | `test/DINModelRegistry.upgrade.test.ts` | 4 | Model/fee/request persistence, governance auth, init lock |
| [DinValidatorStake.test.md](./DinValidatorStake.test.md) | `test/DinValidatorStake.test.ts` | 16 | Behavioral: staking, unbonding, slashing, blacklist, slasher mgmt |

## The common upgrade-test template

Every `*.upgrade.test.ts` suite covers the same three safety axes plus a storage check:

1. **State persistence** — populate real state through the public API, upgrade the proxy to its `*V2` mock, assert the state reads back identically *and* the new `version()` function proves the implementation actually changed.
2. **Access control after upgrade** — assert that restricted functions still revert for unauthorized callers post-upgrade (proxy storage, including `_owner`, is what carries authority — the upgrade must not disturb it).
3. **Implementation lock** — deploy the *implementation* directly (no proxy) and assert `initialize()` reverts with `InvalidInitialization`, proving `_disableInitializers()` in the constructor works.
4. **Storage-layout validation** — the state-persistence test calls `upgrades.validateUpgrade(proxy, V2, { kind: "transparent" })` before upgrading, so the OZ plugin's slot-diff runs as part of the suite.

Supporting contracts: `contracts/upgrade/*V2.sol` (one-line version-bump subclasses annotated `@custom:oz-upgrades-from`) and `contracts/mocks/MockSlasher.sol` (bare `Ownable`, stands in for task contracts anywhere a slasher/owned contract is needed).
