# DinValidatorStake — Technical Documentation

Technical documentation for [`hardhat/contracts/DinValidatorStake.sol`](hardhat/contracts/DinValidatorStake.sol).

## Overview

`DinValidatorStake` is the staking ledger for DIN validators. It holds DIN tokens inside the contract, tracks each validator's staking lifecycle, exposes whether a validator is currently active, and lets authorized slasher contracts reduce stake.

It is responsible for:

- accepting validator stake in DIN tokens;
- tracking validator lifecycle status;
- enforcing delayed withdrawals through an unbonding period;
- keeping unbonding funds slashable until they are actually claimed;
- allowing authorized slasher contracts to penalize validators;
- allowing the contract owner to blacklist and unblacklist validators;
- exposing validator eligibility to other protocol contracts.

The contract manages two balances per validator:

- `activeStake`: stake currently counted toward validator participation.
- `pendingWithdrawals`: stake that has been unstaked but is still locked until the unbonding period ends.

Pending withdrawals remain slashable until they are claimed.

## Inheritance and dependencies

### Inheritance

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | DAO admin ownership |
| `ReentrancyGuardTransient` | OpenZeppelin (L2-optimised) | Re-entrancy protection on ERC-20 flows |

### Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `IERC20` | OpenZeppelin | Token interface |
| `SafeERC20` | OpenZeppelin | Safe ERC-20 transfers (handles non-standard return values) |


## Core Design

### Main Rules

- A validator is only eligible for new work when its status is `Active`.
- A validator with a pending withdrawal is `Exiting`, even if its remaining active stake is still large.
- `pendingWithdrawals` remain slashable until claimed.
- Blacklisted validators cannot stake, start exits, or claim exits.
- Slashing is capped by the validator’s total slashable funds inside the contract.



### Constructor

```solidity
constructor(address dinToken, address dinCoordinator)
```

Constructor rules:

- `dinToken` must not be `address(0)`.
- `dinCoordinator` must not be `address(0)`.
- `DIN_TOKEN` is stored as an immutable ERC-20 reference.
- `DIN_COORDINATOR` is stored as an immutable access-control address.

### Constants and storage

#### Constants

| Name | Value | Meaning |
|---|---:|---|
| `MIN_STAKE` | `10 * 1e18` | Minimum amount accepted by each `stake()` call |
| `UNBONDING_PERIOD` | `7 days` | Delay between `unstake()` and `claimUnstaked()` |

`MIN_STAKE` is enforced per `stake(amount)` call, not on the validator's total post-stake balance.

#### Immutable addresses

| Name | Meaning |
|---|---|
| `DIN_TOKEN` | ERC-20 token accepted as stake |
| `DIN_COORDINATOR` | Only address allowed to manage slasher contracts |

### Slasher registry

```solidity
mapping(address => bool) public slasherContracts;
```

Only addresses marked `true` can call `slash()`.

### Validator status

```solidity
enum ValidatorStatus {
    None,
    Active,
    Exiting,
    Jailed,
    Blacklisted
}
```

| Status | Meaning in the current contract |
|---|---|
| `None` | No active stake and no pending withdrawal |
| `Active` | Validator has no pending withdrawal and `activeStake >= MIN_STAKE` |
| `Exiting` | Validator has a pending withdrawal, or has some active stake but less than `MIN_STAKE` |
| `Jailed` | Reserved in storage and sync logic, but no public function currently places a validator into jail |
| `Blacklisted` | Owner-blocked state that disables stake, unstake, and withdrawal claim |

### Validator record

```solidity
struct ValidatorInfo {
    uint256 activeStake;
    uint256 pendingWithdrawals;
    uint64 withdrawAvailableAt;
    uint64 jailedUntil;
    ValidatorStatus status;
}
```

| Field | Meaning |
|---|---|
| `activeStake` | Stake currently backing validator activity |
| `pendingWithdrawals` | Unbonding stake still held by the contract |
| `withdrawAvailableAt` | Earliest timestamp when `claimUnstaked()` can succeed |
| `jailedUntil` | Timestamp checked by `_syncValidatorStatus()` if status is `Jailed` |
| `status` | Current lifecycle state |

### Public mapping

```solidity
mapping(address => ValidatorInfo) public validators;
```

Each validator address maps to its full staking record.

## Access control

| Function group | Allowed caller |
|---|---|
| `stake`, `unstake`, `claimUnstaked` | Any address acting on its own validator record |
| `blacklistValidator`, `unblacklistValidator` | `owner()` |
| `addSlasherContract`, `removeSlasherContract` | `DIN_COORDINATOR` only |
| `slash` | Registered slasher contracts only |

The contract uses two modifiers:

- `onlyDinCoordinator`: reverts with `NotDINCoordinator()` unless `msg.sender == DIN_COORDINATOR`.
- `onlySlasherContract`: reverts with `NotSlasherContract()` unless `slasherContracts[msg.sender]` is `true`.

## Events

| Event | Emitted when |
|---|---|
| `ValidatorStaked` | stake is added |
| `ValidatorSlashed` | a slash succeeds for a non-zero amount |
| `ValidatorUnstakeRequested` | an unstake request starts the unbonding period |
| `ValidatorWithdrawalClaimed` | pending stake is claimed after unbonding |
| `ValidatorBlacklisted` | owner blacklists a validator |
| `ValidatorUnblacklisted` | owner unblacklists a validator |
| `SlasherContractAdded` | coordinator authorizes a slasher |
| `SlasherContractRemoved` | coordinator removes a slasher |

## Custom errors

The contract uses custom errors instead of revert strings:

- `NotDINCoordinator`
- `ValidatorIsBlacklisted`
- `ValidatorNotBlacklisted`
- `InvalidAddress`
- `NotSlasherContract`
- `AmountLessThanMinStake`
- `NotEnoughStake`
- `SlasherContractAlreadyAdded`
- `SlasherContractNotAdded`
- `InvalidSlashAmount`
- `InvalidUnstakeAmount`
- `PendingWithdrawalExists`
- `NoPendingWithdrawal`
- `WithdrawalNotReady`

## Functional behavior

### `stake(uint256 amount)`

Adds DIN stake for `msg.sender`.

Behavior:

- Reverts with `AmountLessThanMinStake()` if `amount < MIN_STAKE`.
- Reverts with `ValidatorIsBlacklisted()` if the validator is blacklisted.
- Transfers `amount` DIN from the caller to the contract.
- Increases `validators[msg.sender].activeStake`.
- Calls `_syncValidatorStatus(...)`.
- Emits `ValidatorStaked(msg.sender, amount)`.

Notes:

- Every deposit must be at least `MIN_STAKE`, even if the validator already has stake.
- A validator with enough active stake and no pending withdrawal becomes `Active`.

### `unstake(uint256 amount)`

Starts an unbonding withdrawal for `msg.sender`.

Behavior:

- Reverts with `ValidatorIsBlacklisted()` if blacklisted.
- Reverts with `InvalidUnstakeAmount()` if `amount == 0`.
- Reverts with `PendingWithdrawalExists()` if there is already a pending withdrawal.
- Reverts with `NotEnoughStake()` if `activeStake < amount`.
- Decreases `activeStake` by `amount`.
- Sets `pendingWithdrawals = amount`.
- Sets `withdrawAvailableAt = uint64(block.timestamp + UNBONDING_PERIOD)`.
- Calls `_syncValidatorStatus(...)`.
- Emits `ValidatorUnstakeRequested`.

Notes:

- Only one pending withdrawal can exist per validator at a time.
- No tokens leave the contract during `unstake()`.
- If the remaining `activeStake` falls below `MIN_STAKE`, the validator becomes `Exiting`.

### `claimUnstaked()`

Claims matured pending withdrawals for `msg.sender`.

Behavior:

- Reverts with `ValidatorIsBlacklisted()` if blacklisted.
- Reverts with `NoPendingWithdrawal()` if `pendingWithdrawals == 0`.
- Reverts with `WithdrawalNotReady()` if `block.timestamp < withdrawAvailableAt`.
- Copies the pending amount to a local variable.
- Clears `pendingWithdrawals` and `withdrawAvailableAt`.
- Calls `_syncValidatorStatus(...)`.
- Transfers the pending DIN amount to the caller.
- Emits `ValidatorWithdrawalClaimed`.

Notes:

- This is the only function that releases unstaked funds from the contract.
- Once claimed, those tokens are no longer slashable by this contract.

### `slash(address validator, uint256 amount, bytes32 reason)`

Reduces a validator's slashable stake. Callable only by an authorized slasher contract.

Behavior:

- Reverts with `InvalidAddress()` if `validator == address(0)`.
- Reverts with `InvalidSlashAmount()` if `amount == 0`.
- Reads the validator's total slashable stake as `activeStake + pendingWithdrawals`.
- Caps the slash to the validator's available slashable amount.
- Returns `0` immediately if nothing is slashable.
- Deducts from `activeStake` first.
- If needed, deducts the remainder from `pendingWithdrawals`.
- Sets `withdrawAvailableAt = 0` if pending withdrawals are fully consumed.
- Calls `_syncValidatorStatus(...)`.
- Emits `ValidatorSlashed`.
- Returns the actual slashed amount.

Notes:

- Slashing does not transfer, burn, or redistribute tokens in this contract.
- Slashed value remains held by the contract unless another mechanism is added elsewhere.

### `addSlasherContract(address slasherContract)`

Authorizes a slasher contract. Callable only by `DIN_COORDINATOR`.

Behavior:

- Reverts with `InvalidAddress()` if `slasherContract == address(0)`.
- Reverts with `SlasherContractAlreadyAdded()` if already authorized.
- Sets `slasherContracts[slasherContract] = true`.
- Emits `SlasherContractAdded`.

### `removeSlasherContract(address slasherContract)`

Removes slasher authorization. Callable only by `DIN_COORDINATOR`.

Behavior:

- Reverts with `InvalidAddress()` if `slasherContract == address(0)`.
- Reverts with `SlasherContractNotAdded()` if not currently authorized.
- Sets `slasherContracts[slasherContract] = false`.
- Emits `SlasherContractRemoved`.

### `blacklistValidator(address validator)`

Owner-only emergency block on a validator.

Behavior:

- Reverts with `InvalidAddress()` if `validator == address(0)`.
- Sets `validators[validator].status = ValidatorStatus.Blacklisted`.
- Emits `ValidatorBlacklisted`.

Effects:

- The validator cannot call `stake()`, `unstake()`, or `claimUnstaked()`.
- Existing funds remain in the contract.
- Slashing still works because `slash()` does not check the validator's status.

### `unblacklistValidator(address validator)`

Removes blacklist status and restores the validator to the state implied by current balances and jail timing.

Behavior:

- Reverts with `InvalidAddress()` if `validator == address(0)`.
- Reverts with `ValidatorNotBlacklisted()` if current status is not `Blacklisted`.
- If `jailedUntil > block.timestamp`, sets status to `Jailed`.
- Otherwise sets status to `None`.
- Calls `_syncValidatorStatus(...)`.
- Emits `ValidatorUnblacklisted`.

Result:

- If jail is still active, the validator stays `Jailed`.
- Otherwise status recalculates to `Active`, `Exiting`, or `None` based on stake and pending withdrawals.

## View functions

### `minStake()`

Returns `MIN_STAKE`.

### `isValidatorActive(address validator)`

- Returns `true` only if `validators[validator].status == ValidatorStatus.Active`.

- Other contracts should treat `isValidatorActive(address)` as the canonical eligibility check.

### `getStake(address validator)`

Returns `validators[validator].activeStake`.

This does not include `pendingWithdrawals`.

### `slashableStakeOf(address validator)`

Returns:

```solidity
validators[validator].activeStake + validators[validator].pendingWithdrawals
```

### `isSlasherContract(address slasherContract)`

Returns whether the address is currently authorized to call `slash()`.

## Status synchronization

The contract derives validator state through the internal function:

```solidity
function _syncValidatorStatus(ValidatorInfo storage validator) internal
```

Priority order:

1. If status is `Blacklisted`, leave it unchanged.
2. If status is `Jailed` and `jailedUntil > block.timestamp`, leave it unchanged.
3. If `pendingWithdrawals > 0`, set status to `Exiting`.
4. Else if `activeStake >= MIN_STAKE`, set status to `Active`.
5. Else if `activeStake > 0`, set status to `Exiting`.
6. Else set status to `None`.

This means:

- A validator with any pending withdrawal is never `Active`.
- A validator with positive stake below `MIN_STAKE` is `Exiting`, not `None`.
- `Jailed` currently persists only if some external path has already set that status and the jail time is still active.

## Practical implications

- Validators must approve the DIN token before calling `stake()`.
- Partial exits are supported, but only one unbonding withdrawal can be pending at once.
- A validator can remain funded while no longer active if it falls below `MIN_STAKE`.
- Slashing applies to both active stake and unclaimed pending withdrawals.
- The contract currently has no public jail entrypoint and no mechanism that disposes of slashed tokens.

## Workflow

This section shows the normal validator workflow from staking to exit.

### Validator Onboarding Workflow

1. Validator obtains DIN.
2. Validator approves `DinValidatorStake` to spend DIN.
3. Validator calls `stake(amount)`.
4. Contract transfers DIN in and updates `activeStake`.
5. If stake is at least `MIN_STAKE`, status becomes `Active`.
6. Other DIN contracts query `isValidatorActive()` before allowing validator participation.

### Validator Exit Workflow

1. Validator calls `unstake(amount)`.
2. Contract moves `amount` from `activeStake` to `pendingWithdrawals`.
3. Contract sets `withdrawAvailableAt`.
4. Validator status becomes `Exiting`.
5. Validator is no longer eligible for new work.
6. During the unbonding period, slasher contracts may still slash the pending amount.
7. After the unbonding period, validator calls `claimUnstaked()`.
8. Contract transfers the remaining pending amount to the validator.
9. Status becomes `Active`, `Exiting`, or `None` depending on remaining stake.



## Scenarios

These examples show how the lifecycle behaves in practice.

### Scenario 1: Normal Validator Entry

- Validator stakes `20 DIN`.
- `activeStake = 20 DIN`
- `pendingWithdrawals = 0`
- status becomes `Active`

Result: validator is eligible for new work.

### Scenario 2: Partial Exit with Remaining Active Stake

- Validator starts with `30 DIN`.
- Validator calls `unstake(10 DIN)`.
- `activeStake = 20 DIN`
- `pendingWithdrawals = 10 DIN`
- status becomes `Exiting`

Result: even though `activeStake` is still above `MIN_STAKE`, the validator is not active because an exit is in progress.

### Scenario 3: Full Exit

- Validator starts with `20 DIN`.
- Validator calls `unstake(20 DIN)`.
- `activeStake = 0`
- `pendingWithdrawals = 20 DIN`
- status becomes `Exiting`
- after 7 days, validator calls `claimUnstaked()`
- pending amount is transferred out
- status becomes `None`

Result: validator fully exits only after the unbonding period.

### Scenario 4: Slashed During Unbonding

- Validator starts with `20 DIN`.
- Validator calls `unstake(10 DIN)`.
- now `activeStake = 10 DIN`, `pendingWithdrawals = 10 DIN`
- slasher contract later calls `slash(..., 15 DIN, reason)`

Slash behavior:
- first `10 DIN` is removed from `activeStake`
- remaining `5 DIN` is removed from `pendingWithdrawals`

Final state:
- `activeStake = 0`
- `pendingWithdrawals = 5 DIN`
- status remains `Exiting`

Result: validator cannot escape penalties by exiting first.

### Scenario 5: Claim After Partial Slash

- Continuing Scenario 4
- validator waits until `withdrawAvailableAt`
- validator calls `claimUnstaked()`
- only the remaining `5 DIN` is paid out

Result: the validator receives whatever remains after slashing, not the original requested exit amount.

### Scenario 6: Blacklisted Validator

- Stake contract owner blacklists validator
- validator attempts `stake()`
- validator attempts `unstake()`
- validator attempts `claimUnstaked()`

Result: those actions revert. Funds remain trapped unless governance introduces a separate recovery path in future logic.

### Scenario 7: Validator Falls Below Minimum Stake Due to Slashing

- Validator starts with `12 DIN`
- Slasher removes `3 DIN`
- `activeStake = 9 DIN`
- status becomes `Exiting`

Result: validator is no longer eligible for new work because active stake fell below `MIN_STAKE`.


---

## Contract Interactions

### With `DINTaskCoordinator` and `DINTaskAuditor`

These contracts should:
- check `isValidatorActive()` before assigning or accepting validator work;
- use `minStake()` as the single source of stake threshold truth;
- call `slash()` only if they are registered as slasher contracts.

### With `DINCoordinator`

`DINCoordinator` is the administrative control point for:
- adding slashers;
- removing slashers.

### With Frontends and Off-Chain Services

Off-chain systems should distinguish:
- active stake: `getStake()`;
- total slashable stake: `slashableStakeOf()`;
- validator eligibility: `isValidatorActive()`;
- exit maturity: `validators[addr].withdrawAvailableAt`.

### With Governance

DinValidatorStake owner
  ├── calls   → DinValidatorStake.blacklistValidator()
  └── calls   → DinValidatorStake.unblacklistValidator()

  ---

## Summary

`DinValidatorStake` is not just a token vault. It is a validator lifecycle contract.

Its main production-grade property is that exits are delayed and still slashable. That design closes the most dangerous staking failure mode: a validator doing work, misbehaving, and withdrawing before penalties can be enforced.
