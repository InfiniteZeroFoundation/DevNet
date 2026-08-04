# DinValidatorStake.test.ts — Test Documentation

> **File:** `hardhat/test/DinValidatorStake.test.ts`
> **Subject under test:** `DinValidatorStake` (behavioral / functional suite)
> **Run:** `cd hardhat && npx hardhat test test/DinValidatorStake.test.ts`

---

## 1. Purpose

Behavioral test suite for the validator staking lifecycle: staking, the unbonding window, slashing, blacklisting, and slasher-contract management. This is the only *functional* (non-upgrade) suite in `hardhat/test/`; the upgrade suites (`*.upgrade.test.ts`) cover state-preservation across implementation swaps.

All tests run against the **full proxied platform** deployed by [`test/helpers/platform.ts`](helpers/platform.md), not an isolated contract — so every assertion also implicitly exercises the proxy wiring (token minting through the coordinator, slasher registration through the coordinator, etc.).

---

## 2. Suite Constants & Fixture

```ts
const MIN_STAKE = 10n * 10n ** 18n;              // mirrors the contract constant
const UNBONDING_PERIOD = 7 * 24 * 60 * 60;       // 7 days, mirrors the contract constant
const STAKE_DEPOSIT_ETH = 10_000_000_000_000_000n; // 0.01 ETH → ~10,000 DIN at the default rate
```

The local `setup()` helper extends `deployPlatform()` with:

1. A `MockSlasher` deployment ([`contracts/mocks/MockSlasher.sol`](../mocks/MockSlasher.md)) registered via `dinCoordinator.addSlasherContract` — giving the suite an authorized slasher address.
2. DIN minted to `user` via `mintDinViaDeposit` (a real `depositAndMint` call).
3. An unlimited `approve` from `user` to the stake contract.

> These constants are duplicated from the contract rather than read from it; if `MIN_STAKE` or `UNBONDING_PERIOD` change in `DinValidatorStake.sol`, this file must be updated in step.

---

## 3. Test Cases

### `staking`

| Test | Asserts |
|------|---------|
| accepts MIN_STAKE and marks validator Active | `getStake` equals the staked amount; `isValidatorActive` is `true` |
| reverts when stake is below MIN_STAKE | Custom error `AmountLessThanMinStake` |
| reverts when validator is blacklisted | Owner blacklists first; `stake` reverts `ValidatorIsBlacklisted` |

### `unstake and unbonding window`

| Test | Asserts |
|------|---------|
| moves stake to pending and sets withdrawAvailableAt | `activeStake == 0`, `pendingWithdrawals == MIN_STAKE`, `withdrawAvailableAt > 0` |
| reverts claimUnstaked before unbonding period elapses | `WithdrawalNotReady` |
| allows claimUnstaked after unbonding period and returns tokens | Uses `time.increase(UNBONDING_PERIOD + 1)`; token balance restored, stake zeroed |
| reverts second unstake when a pending withdrawal exists | `PendingWithdrawalExists` (single pending-withdrawal invariant) |

### `slashing`

| Test | Asserts |
|------|---------|
| slashes active stake via an authorized slasher | Half of `MIN_STAKE` slashed; `getStake` reduced accordingly |
| slashes pending withdrawals when active stake is exhausted | After a full unstake, a slash consumes the pending amount (`activeStake == 0`, `pendingWithdrawals == 0`) |
| reverts slash from an unauthorized address | `NotSlasherContract` |

The slasher tests **impersonate the MockSlasher contract address** as a signer (`ethers.getImpersonatedSigner`) after funding it with `setBalance` — the mock has no `slash`-calling logic of its own; only its *address* is registered as a slasher (see [MockSlasher.md](../mocks/MockSlasher.md)).

### `blacklisting`

| Test | Asserts |
|------|---------|
| owner can blacklist a validator and block further activity | `isValidatorActive` false; `unstake` reverts `ValidatorIsBlacklisted` |
| owner can unblacklist and restore Active status | Status recomputed to `Active` from balances |
| non-owner cannot blacklist | OZ `OwnableUnauthorizedAccount` (post-conversion selector) |
| reverts unblacklist on a validator that is not blacklisted | `ValidatorNotBlacklisted` |

### `slasher contract management`

| Test | Asserts |
|------|---------|
| only DIN_COORDINATOR can register slasher contracts | Direct `addSlasherContract` from an EOA reverts `NotDINCoordinator` |
| reverts registering the same slasher twice | Second `dinCoordinator.addSlasherContract` bubbles up `SlasherContractAlreadyAdded` from the stake contract |

---

## 4. Techniques Worth Noting

- **Contract-address impersonation:** `setBalance` + `getImpersonatedSigner` lets a *contract address* send transactions without contract code performing the call — the standard Hardhat pattern for testing `onlySlasherContract` gates without writing a slasher that calls back.
- **Time travel:** `@nomicfoundation/hardhat-network-helpers` `time.increase` drives the unbonding window.
- **Cross-contract revert matching:** the duplicate-slasher test calls the *coordinator* but matches the custom error against the *stake* contract's ABI — errors are matched by selector, not by emitting contract.

---

## 5. Coverage Gaps (candidates for future tests)

- No test for slash amounts larger than total slashable stake (capping/return value) or for the `slash` return value at all.
- No partial-exit scenario (unstake less than active stake, validator becomes `Exiting` while still funded).
- `claimUnstaked` while blacklisted, `jailedUntil` interactions, and `slashableStakeOf`/`minStake` views are untested.
- Events (`ValidatorStaked`, `ValidatorSlashed`, …) are never asserted.

---

## 6. Change Log

- **2026-07 (PR 13):** rewritten to deploy the platform through the Transparent Proxy fixture (`deployPlatform`) instead of standalone contract deployments; owner-gating assertions updated to OZ `OwnableUnauthorizedAccount`.
