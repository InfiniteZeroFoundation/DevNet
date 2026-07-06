# `DinValidatorStake.upgrade.test.ts` — Upgrade Safety for the Validator Stake Contract

4 tests. The highest-stakes upgrade suite in the platform — this contract custodies all validator collateral, so "state persists across upgrade" here literally means "no one's stake disappears."

Constants used: `MIN_STAKE = 10 DIN` (matching the contract), `STAKE_DEPOSIT_ETH = 0.01 ETH` (→ 10,000 DIN at the default rate — ample headroom over min stake).

## Test 1 — `preserves stake balances across upgrade`

State persistence + storage-layout check.

**Setup:** full platform; `user` acquires DIN through the real path (`mintDinViaDeposit`), grants an ERC-20 approval to the stake proxy, and stakes exactly `MIN_STAKE`. Stake recorded via `getStake()`.

**Upgrade:** `validateUpgrade()` then `upgradeTransparentProxy()` to `DinValidatorStakeV2`.

**Assertions:**
- `getStake(user)` unchanged — the `validators` mapping (a mapping of `ValidatorInfo` structs: active stake, pending withdrawals, timestamps, status enum) survived intact.
- `isValidatorActive(user) == true` — not just the raw number but the *derived status machine* state persisted; the user staked exactly `MIN_STAKE`, so any stake loss or status corruption would flip this to false.
- `version() == 2` — the implementation genuinely changed.

## Test 2 — `keeps slasher registration restricted to coordinator after upgrade`

Access control for the protocol's most sensitive privilege — the ability to mint slashing authority.

After upgrading, `other` calls `addSlasherContract()` directly on the stake contract and must revert with the custom error `NotDINCoordinator`. The `onlyDinCoordinator` modifier compares `msg.sender` to the `DIN_COORDINATOR` storage variable (a former immutable, converted to storage for upgradeability) — this test proves that slot survived the upgrade and still holds the coordinator proxy address. A `MockSlasher` is deployed as the candidate address, but the call must fail regardless.

## Test 3 — `keeps blacklist control with owner after upgrade`

Two-sided owner-power check after upgrade:

1. `user` stakes `MIN_STAKE` (active validator).
2. Upgrade the proxy to V2.
3. **Positive:** `deployer` (owner) blacklists `user` — succeeds, and `isValidatorActive(user)` flips to `false`. The owner's authority works *through the new implementation*.
4. **Negative:** `other` attempts `unblacklistValidator(user)` — reverts with `OwnableUnauthorizedAccount`.

Together: the `_owner` slot persisted, owner-gated state transitions still function, and non-owners still can't reverse them.

## Test 4 — `implementation contract cannot be initialized directly`

Deploys the raw implementation and asserts `initialize(s1.address, s2.address)` (token + coordinator params — arbitrary here) reverts with `InvalidInitialization`, proving the `_disableInitializers()` constructor guard.

## Relationship to the behavioral suite

This file only covers *upgrade* safety. The full staking/unbonding/slashing/blacklist behavior matrix (16 tests) lives in `DinValidatorStake.test.ts` — see [DinValidatorStake.test.md](./DinValidatorStake.test.md). Both suites share the `deployPlatform()` fixture, so behavioral tests also implicitly exercise the proxy path.

## What V2 is

`contracts/upgrade/DinValidatorStakeV2.sol` — subclass adding only `version() → 2`, annotated `@custom:oz-upgrades-from DinValidatorStake` + `missing-initializer` (intentional, no new state).
