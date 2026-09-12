# DinToken.upgrade.test.ts — Test Documentation

> **File:** `hardhat/test/DinToken.upgrade.test.ts`
> **Subject under test:** `DinToken` upgrade safety (Transparent Proxy)
> **Run:** `cd hardhat && npx hardhat test test/DinToken.upgrade.test.ts`

---

## 1. Purpose

Verifies that upgrading the `DinToken` proxy preserves ERC-20 balances, the one-shot `coordinator` wiring, and both access-control paths (`onlyCoordinator` for minting, OZ `onlyOwner` for wiring). Upgrade target: [`DinTokenV2`](../upgrades/DinTokenV2.md) (adds only `version() == 2`).

Deploys the full platform via [`test/helpers/platform.ts`](helpers/platform.md); balances are created with a real `depositAndMint` round-trip (`mintDinViaDeposit`), so the minting path through the coordinator is exercised before and after the upgrade.

---

## 2. Test Cases

| Test | Scenario | Asserts |
|------|----------|---------|
| preserves balances and coordinator wiring across upgrade | Mint via deposit, `validateUpgrade`, upgrade, mint again | `coordinator()` still points at the coordinator proxy; pre-upgrade balance intact; `version() == 2`; post-upgrade minting still works and increases the balance |
| keeps mint restricted to coordinator after upgrade | Upgrade, then an EOA calls `mint` | Reverts with the custom `Unauthorized` error (`onlyCoordinator`) |
| keeps coordinator setup restricted to owner after upgrade | Upgrade, then a non-owner calls `setCoordinator` | Reverts `OwnableUnauthorizedAccount` (OZ owner gate) |
| implementation contract cannot be initialized directly | Deploys the raw implementation, calls `initialize()` | Reverts `InvalidInitialization` |

---

## 3. What the Suite Establishes

- **Balances live in the proxy**, not the implementation — the strongest user-facing guarantee of the upgradeable conversion is asserted directly.
- **Both roles survive an upgrade unchanged**: the minter (`coordinator`) and the admin (`owner()`) keep their gates, confirming the two-role split documented in `DinToken.md` §6.
- The second `setCoordinator` path (one-shot `CoordinatorAlreadySet` guard) is *implicitly* locked in by the first test's wiring assertion.

## 4. Coverage Gaps

- No explicit test that `setCoordinator` reverts `CoordinatorAlreadySet` after upgrade (the one-shot guard itself is untested in this suite — and in the functional suite, since none exists for `DinToken`).
- No test of `transfer`/`approve` behavior across the upgrade (only `balanceOf` is checked); acceptable given OZ's ERC-20 is not modified.
