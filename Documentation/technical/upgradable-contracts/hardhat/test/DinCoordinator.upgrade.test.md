# `DinCoordinator.upgrade.test.ts` — Upgrade Safety for the DIN Coordinator

4 tests. Verifies that upgrading the `DinCoordinator` proxy to `DinCoordinatorV2` preserves the exchange rate and token wiring, keeps owner gating intact, keeps the coordinator↔stake slasher pipeline functional, and that the implementation is initialization-locked.

## Test 1 — `preserves exchange rate and token wiring across upgrade`

State-persistence test with the storage-layout check.

**Setup:** full platform; owner changes `dinPerEth` from the default 1M to **2,000,000 DIN/ETH** (a deliberately non-default value — asserting the default would not prove persistence, since a re-initialized contract would also show the default); `user` mints under the new rate; the token balance is recorded.

**Upgrade:** `validateUpgrade()` (storage diff) then `upgradeTransparentProxy()` to `DinCoordinatorV2`.

**Assertions:**
- `dinToken()` still returns the token proxy address — cross-contract wiring persisted.
- `dinPerEth()` still equals the *modified* rate — mutable config in proxy storage persisted.
- `version() == 2` — the implementation really changed.
- `user`'s token balance is untouched — upgrading the coordinator has no side effects on state held in the *other* proxy.

## Test 2 — `keeps owner-only functions restricted after upgrade`

After upgrading, `other` calls `updateDinPerEth(1)` and must revert with `OwnableUnauthorizedAccount`. Confirms the `_owner` slot (proxy storage) still gates admin functions through the new implementation.

## Test 3 — `keeps slasher management wired to stake contract after upgrade`

The most system-level of the four — it tests a **cross-proxy pipeline**, not a single contract:

1. Deploy a `MockSlasher` (bare `Ownable` standing in for a task contract).
2. Owner calls `dinCoordinator.addSlasherContract(slasher)` — the coordinator forwards to `DinValidatorStake` (which accepts only calls from the coordinator address).
3. Assert `dinValidatorStake.isSlasherContract(slasher) == true` *before* the upgrade.
4. Upgrade the coordinator proxy to V2.
5. Assert the registration is **still true after** the upgrade.

Why this matters: `DinValidatorStake` authorizes the coordinator by its **address** (`onlyDinCoordinator` checks `msg.sender == DIN_COORDINATOR`). A Transparent Proxy upgrade swaps the implementation but keeps the proxy address — so the authorization must survive. This test pins down exactly the property that makes the Transparent Proxy choice safe for cross-contract auth: **identity is the proxy address, not the implementation**.

## Test 4 — `implementation contract cannot be initialized directly`

Deploys the raw `DinCoordinator` implementation and asserts `initialize(signer.address)` reverts with `InvalidInitialization` — the `_disableInitializers()` constructor guard. (The argument here is the token address parameter; any address suffices since the call must revert before validation.)

## What V2 is

`contracts/upgrade/DinCoordinatorV2.sol` — `DinCoordinator` subclass adding only `version() → 2`, annotated `@custom:oz-upgrades-from DinCoordinator` + `missing-initializer` (intentional, no new state).
