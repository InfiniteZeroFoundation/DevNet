# `DinToken.upgrade.test.ts` — Upgrade Safety for the DIN Token

4 tests. Verifies that upgrading the `DinToken` proxy to `DinTokenV2` preserves ERC-20 state, preserves the coordinator wiring, keeps both access-control gates intact, and that the raw implementation contract is initialization-locked.

## Test 1 — `preserves balances and coordinator wiring across upgrade`

The core state-persistence test, and the one that runs the storage-layout check.

**Setup:** full platform via `deployPlatform()`; `user` mints DIN through the real economic path (`mintDinViaDeposit`, 0.01 ETH → 10,000 DIN); balance recorded.

**Upgrade:**
```ts
await upgrades.validateUpgrade(proxyAddress, DinTokenV2, { kind: PROXY_KIND });
const upgraded = await upgradeTransparentProxy(proxyAddress, DinTokenV2);
```
`validateUpgrade` runs the OZ plugin's slot-by-slot storage diff between the live implementation and V2 *before* upgrading — a reordered, removed, or retyped variable fails here, not on-chain.

**Assertions:**
- `coordinator()` still returns the DinCoordinator proxy address — the one-shot wiring from deployment step 3 survived the implementation swap.
- `balanceOf(user)` is unchanged — ERC-20 balances live in proxy storage, untouched by the upgrade.
- `version() == 2` — proves the call is actually hitting the **new** implementation, not a stale one. Without this, the two assertions above could pass trivially on a no-op upgrade.
- A **second mint after the upgrade succeeds** and increases the balance — the upgraded token still accepts mints from the still-wired coordinator. This closes the loop: not just "old state readable" but "old wiring still functional".

## Test 2 — `keeps mint restricted to coordinator after upgrade`

Access control, negative path. After upgrading, `user` (not the coordinator) calls `mint()` directly and must get the custom error `Unauthorized`. Verifies the `onlyCoordinator` modifier still reads the correct `coordinator` slot from proxy storage post-upgrade.

## Test 3 — `keeps coordinator setup restricted to owner after upgrade`

Second access-control gate. After upgrading, `other` (a non-owner) calls `setCoordinator()` and must get `OwnableUnauthorizedAccount`. Verifies `OwnableUpgradeable`'s `_owner` slot survived the upgrade and still gates admin functions. (Note: even the owner couldn't re-point the coordinator — `CoordinatorAlreadySet` — but this test specifically checks the *ownership* gate fires first for a non-owner.)

## Test 4 — `implementation contract cannot be initialized directly`

Deploys `DinToken` **directly** — no proxy — and asserts `initialize()` reverts with `InvalidInitialization`.

This is the `_disableInitializers()` guard test. Without the guard, anyone could call `initialize()` on the naked implementation contract and become its owner. That wouldn't affect proxy state, but an attacker-owned implementation is a real hazard (phishing surface, and catastrophic in delegatecall-adjacent patterns). One of these tests exists per platform contract.

## What V2 is

`contracts/upgrade/DinTokenV2.sol` — `contract DinTokenV2 is DinToken` adding only `version() → 2`, annotated `@custom:oz-upgrades-from DinToken` (enables the layout diff) and `@custom:oz-upgrades-unsafe-allow missing-initializer` (intentional: no new state, so V1's initializer is reused; a `reinitializer` would only be needed if V2 added storage needing one-time setup).
