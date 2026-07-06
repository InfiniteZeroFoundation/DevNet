# `DinValidatorStake.test.ts` — Behavioral Suite for the Validator Stake Contract

16 tests across 5 describe blocks. This is the platform's only dedicated *behavioral* (non-upgrade) suite — appropriate, since `DinValidatorStake` carries the protocol's economic security: stake custody, the unbonding window, slashing, and blacklisting.

History note: the original version of this file predated the upgradeable conversion and deployed contracts via raw constructors — it broke when constructors became `_disableInitializers()` stubs. It was rewritten on this branch against the `deployPlatform()` proxy fixture, so every behavioral test now also implicitly exercises the proxy path.

## Shared `setup()`

Extends `deployPlatform()` with:
- A `MockSlasher` deployed and **registered as an authorized slasher via the real path** (`dinCoordinator.addSlasherContract` → stake contract), not by storage manipulation.
- `user` funded with 10,000 DIN via `mintDinViaDeposit` (0.01 ETH at the default rate) and an unlimited ERC-20 approval to the stake contract.

Constants mirror the contract: `MIN_STAKE = 10 DIN`, `UNBONDING_PERIOD = 7 days`.

## `staking` (3 tests)

| Test | What it proves |
|---|---|
| accepts `MIN_STAKE` and marks validator Active | Happy path: tokens pulled via `safeTransferFrom`, `getStake` reflects the amount, and the derived status machine (`_syncValidatorStatus`) lands on `Active` at exactly the threshold. |
| reverts below `MIN_STAKE` | `MIN_STAKE - 1` → custom error `AmountLessThanMinStake`. Boundary is inclusive: ≥ passes, < reverts. |
| reverts when blacklisted | Owner blacklists first; the stake attempt → `ValidatorIsBlacklisted`. Blacklist is checked *before* any token movement. |

## `unstake and unbonding window` (4 tests)

| Test | What it proves |
|---|---|
| moves stake to pending and sets `withdrawAvailableAt` | `unstake` zeroes `activeStake`, credits `pendingWithdrawals`, stamps a future `withdrawAvailableAt`. Funds leave "active" but do **not** leave the contract. |
| reverts `claimUnstaked` before the window elapses | Immediate claim → `WithdrawalNotReady`. The 7-day unbonding delay is enforced. |
| allows claim after the window, returns tokens | Uses Hardhat's `time.increase(UNBONDING_PERIOD + 1)`; claim transfers exactly the pending amount back (balance-delta asserted) and stake reads zero. |
| reverts second unstake while one is pending | Stakes `2 × MIN_STAKE`, unstakes half, second unstake → `PendingWithdrawalExists`. The contract allows **one pending withdrawal at a time** — a deliberate simplification that keeps the slashing math over pending funds unambiguous. |

## `slashing` (3 tests)

These use Hardhat's `getImpersonatedSigner` on the registered `MockSlasher` address (with `setBalance` for gas) so `slash()` genuinely arrives with `msg.sender == slasherContract` — the modifier is tested, not bypassed.

| Test | What it proves |
|---|---|
| slashes active stake via an authorized slasher | Half the stake is slashed; `getStake` shows the exact remainder. |
| slashes pending withdrawals when active stake is exhausted | The critical economic property: `user` unstakes fully (all funds now pending), then is slashed for the full amount — both `activeStake` **and** `pendingWithdrawals` end at zero. **Unbonding is not an escape hatch:** funds remain slashable throughout the 7-day window, so a validator cannot front-run a slash by unstaking. |
| reverts slash from an unauthorized address | `other` → `NotSlasherContract`. Only contracts registered through the coordinator may slash. |

Not covered (accepted gap): the cap-not-revert behavior when requested slash exceeds slashable stake, and the active-first/pending-second split within a single partial slash — the exhaustion test covers the boundary case that matters most economically.

## `blacklisting` (4 tests)

| Test | What it proves |
|---|---|
| owner can blacklist; blocks further activity | Post-blacklist: `isValidatorActive` false and `unstake` reverts `ValidatorIsBlacklisted` — the funds of a misbehaving validator are frozen (and remain slashable). |
| owner can unblacklist; restores Active | Status machine recomputes from stake (≥ `MIN_STAKE` ⇒ back to `Active`), rather than blindly resetting. |
| non-owner cannot blacklist | `OwnableUnauthorizedAccount`. |
| unblacklist on a non-blacklisted validator reverts | `ValidatorNotBlacklisted` — guards against state-machine no-ops masking operator mistakes. |

## `slasher contract management` (2 tests)

| Test | What it proves |
|---|---|
| only `DIN_COORDINATOR` can register slashers | Direct `addSlasherContract` from an EOA → `NotDINCoordinator`. Slasher authority can only be granted through the coordinator (which itself gates on its owner) — a two-hop privilege chain. |
| registering the same slasher twice reverts | Second registration via the coordinator → `SlasherContractAlreadyAdded` (note: asserted with the *stake contract's* error interface, since the coordinator call reverts with the downstream contract's error). |

## Coverage summary

The suite covers every externally-reachable state transition of the validator lifecycle — stake → active → (unstake → pending → claim | slash | blacklist) — with both positive and negative paths, using only public entry points and the real cross-contract authorization chain. Upgrade-safety for the same contract is covered separately in [DinValidatorStake.upgrade.test.md](./DinValidatorStake.upgrade.test.md).
