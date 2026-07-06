# `DINModelRegistry.upgrade.test.ts` — Upgrade Safety for the Model Registry

4 tests. Verifies that upgrading the `DINModelRegistry` proxy to `DINModelRegistryV2` preserves approved models, fee configuration, and **in-flight** (unprocessed) requests; that governance stays owner-gated; and that the implementation is initialization-locked.

This suite has the most elaborate setup of the four, because creating a legitimate registry entry requires satisfying the registry's full validation chain: both task contracts must be registered slashers *and* owned by the requester.

## Test 1 — `preserves fee settings and model state across upgrade`

State persistence + storage-layout check, exercising the full registration happy path first.

**Setup:**
1. Owner sets `proprietaryFee` to `42` wei — a deliberately non-default value, so the post-upgrade assertion can't be satisfied by accidental re-initialization (the initializer's default is `0.00001 ether`).
2. Two `MockSlasher` contracts are deployed **owned by `user`** — they stand in for a model's `DINTaskCoordinator` and `DINTaskAuditor` (the registry only checks `isSlasherContract()` and `owner()`, which the mock satisfies).
3. Owner authorizes both as slashers via `dinCoordinator.addSlasherContract()` — the real cross-contract path (coordinator → stake contract).
4. `user` submits `requestModelRegistration(manifestCID, coord, auditor, isOpenSource=false)` paying the proprietary fee; owner calls `approveModel(0)`.

**Upgrade:** `validateUpgrade()` then `upgradeTransparentProxy()` to `DINModelRegistryV2`.

**Assertions:**
- `proprietaryFee() == 42` — modified fee config persisted.
- `totalModels() == 1` and `version() == 2`.
- `getModel(0)` returns the full intact record: owner = `user`, the original `manifestCID`, and both task-contract addresses. This covers the `models` array **and** the struct field layout — a storage-layout mistake inside the `Model` struct would scramble these reads.

## Test 2 — `keeps owner-only governance restricted after upgrade`

After upgrading, `other` calls `setProprietaryFee(1)` and must revert with `OwnableUnauthorizedAccount`. Representative of the whole owner-gated surface (fee setters, approve/reject, disable/enable, withdraw).

## Test 3 — `keeps pending requests readable after upgrade`

The subtlest persistence test: an **unprocessed** request must survive an upgrade and still be *actionable* afterwards.

1. Same slasher/mock setup; `user` submits an open-source registration request. No approval yet.
2. Upgrade the proxy to V2.
3. Assert `totalModelRequests() == 1` and the raw `modelRequests(0)` struct reads back correctly (`requester == user`, `processed == false`).
4. **Owner approves the request after the upgrade** — `approveModel(0)` succeeds and `totalModels() == 1`.

Step 4 is the important one: it proves the approval path's *entire* re-validation chain (slasher status via the stake proxy, task-contract ownership via `IOwnable`, duplicate checks against the reverse-lookup mappings) still functions against pre-upgrade data. An upgrade landing mid-review cannot strand pending requests.

## Test 4 — `implementation contract cannot be initialized directly`

Raw implementation deploy; `initialize(signer.address)` must revert with `InvalidInitialization` (`_disableInitializers()` guard).

## Not covered here (by design)

The `daoAdmin()` / `setDAOAdmin()` backward-compat shims and the manifest-update request flow have no dedicated upgrade tests — they are thin wrappers over `OwnableUpgradeable` and the same request-array pattern proven in Test 3. Their functional correctness is exercised at the CLI integration layer (`tests/dincli/`).

## What V2 is

`contracts/upgrade/DINModelRegistryV2.sol` — subclass adding only `version() → 2`, annotated `@custom:oz-upgrades-from DINModelRegistry` + `missing-initializer` (intentional, no new state).
