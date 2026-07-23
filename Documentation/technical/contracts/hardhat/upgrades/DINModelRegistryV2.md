# DINModelRegistryV2.sol — Upgrade Fixture Documentation

> **File:** `hardhat/contracts/upgrade/DINModelRegistryV2.sol`
> **Role:** minimal V2 implementation used to test upgrading the `DINModelRegistry` proxy
> **Test-only** — not intended for production deployment

---

## 1. Contents

```solidity
/// @custom:oz-upgrades-from DINModelRegistry
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DINModelRegistryV2 is DINModelRegistry {
    function version() external pure returns (uint256) {
        return 2;
    }
}
```

Inherits all of `DINModelRegistry` unchanged; `version() == 2` through the proxy proves the swap.

---

## 2. Why the Annotations

- **`@custom:oz-upgrades-from DINModelRegistry`** — anchors OZ storage-layout validation to V1 for `upgrades.validateUpgrade`.
- **`@custom:oz-upgrades-unsafe-allow missing-initializer`** — intentional: no new state, so V1's consumed `initialize(dinValidatorStake_)` suffices; a state-adding V2 needs `reinitializer(2)`.

---

## 3. What It Demonstrates for Real Upgrades

Template for a real registry V2 — likely candidates from the known-limitations list include request expiry (`expiresAt`) or task-contract replacement, both of which would append fields/state consuming `__gap` headroom. `test/DINModelRegistry.upgrade.test.ts` proves that models and **pending requests** survive the swap and remain approvable.

## 4. Used By

- `test/DINModelRegistry.upgrade.test.ts` — all upgrade scenarios target this fixture.
