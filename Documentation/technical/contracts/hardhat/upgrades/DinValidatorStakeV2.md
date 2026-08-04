# DinValidatorStakeV2.sol — Upgrade Fixture Documentation

> **File:** `hardhat/contracts/upgrade/DinValidatorStakeV2.sol`
> **Role:** minimal V2 implementation used to test upgrading the `DinValidatorStake` proxy
> **Test-only** — not intended for production deployment

---

## 1. Contents

```solidity
/// @custom:oz-upgrades-from DinValidatorStake
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinValidatorStakeV2 is DinValidatorStake {
    function version() external pure returns (uint256) {
        return 2;
    }
}
```

Inherits all of `DinValidatorStake` unchanged; `version() == 2` through the proxy proves the swap.

---

## 2. Why the Annotations

- **`@custom:oz-upgrades-from DinValidatorStake`** — anchors OZ storage-layout validation to V1 for `upgrades.validateUpgrade`.
- **`@custom:oz-upgrades-unsafe-allow missing-initializer`** — intentional: no new state, so V1's consumed `initialize(dinToken, dinCoordinator)` suffices; a state-adding V2 needs `reinitializer(2)`.

---

## 3. What It Demonstrates for Real Upgrades

The highest-stakes upgrade template of the four — this proxy holds all staked DIN. A real V2 (e.g. the planned jail entrypoint, or slash-fund disposal from the mechanism design work) must append state only into `__gap` headroom, and prove balance/status survival through `test/DinValidatorStake.upgrade.test.ts` before an on-chain upgrade.

## 4. Used By

- `test/DinValidatorStake.upgrade.test.ts` — all upgrade scenarios target this fixture.
