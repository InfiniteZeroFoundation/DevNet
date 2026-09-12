# DinCoordinatorV2.sol — Upgrade Fixture Documentation

> **File:** `hardhat/contracts/upgrade/DinCoordinatorV2.sol`
> **Role:** minimal V2 implementation used to test upgrading the `DinCoordinator` proxy
> **Test-only** — not intended for production deployment
> **SPDX:** UNLICENSED (matches `DinCoordinator.sol`, unlike the other three fixtures which are MIT)

---

## 1. Contents

```solidity
/// @custom:oz-upgrades-from DinCoordinator
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinCoordinatorV2 is DinCoordinator {
    function version() external pure returns (uint256) {
        return 2;
    }
}
```

Inherits all of `DinCoordinator` unchanged; the added `version()` (absent in V1) proves through the proxy that the implementation swap took effect.

---

## 2. Why the Annotations

- **`@custom:oz-upgrades-from DinCoordinator`** — anchors the OZ plugin's storage-layout validation to V1's layout for `upgrades.validateUpgrade`.
- **`@custom:oz-upgrades-unsafe-allow missing-initializer`** — intentional: V2 adds no state, so V1's already-consumed `initialize(dinToken_)` suffices. A state-adding V2 would need a `reinitializer(2)` instead.

---

## 3. What It Demonstrates for Real Upgrades

Template for a real coordinator V2 — e.g. a future fee-on-deposit or rate-oracle change would extend V1, append state into the `__gap` headroom, and be validated by `test/DinCoordinator.upgrade.test.ts` before an on-chain upgrade via `scripts/upgrade-platform.ts`.

## 4. Used By

- `test/DinCoordinator.upgrade.test.ts` — all upgrade scenarios target this fixture.
