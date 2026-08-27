# DinTokenV2.sol — Upgrade Fixture Documentation

> **File:** `hardhat/contracts/upgrade/DinTokenV2.sol`
> **Role:** minimal V2 implementation used to test upgrading the `DinToken` proxy
> **Test-only** — not intended for production deployment

---

## 1. Contents

```solidity
/// @custom:oz-upgrades-from DinToken
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinTokenV2 is DinToken {
    function version() external pure returns (uint256) {
        return 2;
    }
}
```

`DinTokenV2` inherits everything from `DinToken` and adds a single pure function, `version()`, returning `2`. Since V1 has no `version()`, a successful `version() == 2` call through the proxy is unambiguous proof the implementation was swapped.

---

## 2. Why the Annotations

- **`@custom:oz-upgrades-from DinToken`** tells the OZ upgrades plugin which contract's storage layout to validate against, letting `upgrades.validateUpgrade(proxy, DinTokenV2)` machine-check that V2 appends nothing that would shift V1's storage (it appends nothing at all).
- **`@custom:oz-upgrades-unsafe-allow missing-initializer`** suppresses the plugin's warning that V2 declares no initializer. This is intentional: V2 adds **no new state**, so V1's `initialize` (already consumed on the live proxy) is sufficient. A real future V2 that adds state needing setup must instead provide a `reinitializer(2)` function.

---

## 3. What It Demonstrates for Real Upgrades

This fixture is the template for an actual `DinToken` V2: inherit or copy V1, append new state only after the existing variables (consuming `__gap` slots), keep the annotations, and let `test/DinToken.upgrade.test.ts` + `upgrades.validateUpgrade` prove layout safety before touching the live proxy.

## 4. Used By

- `test/DinToken.upgrade.test.ts` — all upgrade scenarios target this fixture.
