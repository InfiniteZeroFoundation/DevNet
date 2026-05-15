# DinValidatorStake — Technical Documentation

> **File:** `hardhat/contracts/DinValidatorStake.sol`  
> **Purpose:** Validator staking, exit, slashing, and status management for DIN validators.

---

## 1. Overview

`DinValidatorStake` is the contract that holds validator stake and defines when a validator is economically eligible to participate in DIN.

It is responsible for:
- accepting validator stake in DIN tokens;
- tracking validator lifecycle status;
- enforcing delayed withdrawals through an unbonding period;
- keeping unbonding funds slashable until they are actually claimed;
- allowing authorized slasher contracts to penalize validators;
- allowing the contract owner to blacklist and unblacklist validators;
- exposing validator eligibility to other protocol contracts.

This contract is the source of truth for validator activity. Other contracts should treat `isValidatorActive(address)` as the canonical eligibility check.

### 1.1. Inheritance

| Component | Source | Purpose |
|-----------|--------|---------|
| `Ownable` | OpenZeppelin | DAO admin ownership |
| `ReentrancyGuardTransient` | OpenZeppelin (L2-optimised) | Re-entrancy protection on ERC-20 flows |

## 1.2. Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `IERC20` | OpenZeppelin | Token interface |
| `SafeERC20` | OpenZeppelin | Safe ERC-20 transfers (handles non-standard return values) |

---

## 2. Why This Contract Exists

In a production staking system, validators must not be able to perform work and immediately withdraw before faults are detected.

`DinValidatorStake` addresses that by splitting exit into two phases:

1. `unstake(amount)` starts exit and moves funds into `pendingWithdrawals`.
2. `claimUnstaked()` releases funds only after the unbonding period ends.

During that unbonding window, the pending funds are still slashable.

That means a validator cannot avoid penalties simply by exiting right after work is assigned or completed.

---

## 3. Core Design

### 3.1 Main Rules

- A validator is only eligible for new work when its status is `Active`.
- A validator with a pending withdrawal is `Exiting`, even if its remaining active stake is still large.
- `pendingWithdrawals` remain slashable until claimed.
- Blacklisted validators cannot stake, start exits, or claim exits.
- Slashing is capped by the validator’s total slashable funds inside the contract.

### 3.2 Economic Intent

The contract is designed so that:
- stake backs validator behavior;
- exit is delayed;
- penalties can still be applied after work was performed;
- validator eligibility is determined by lifecycle state, not just token balance.

---

## 4. State and Parameters

### 4.1 Constants

| Name | Value | Meaning |
|------|-------|---------|
| `MIN_STAKE` | `10 * 1e18` | Minimum active DIN stake required for `Active` status |
| `UNBONDING_PERIOD` | `7 days` | Delay between exit request and withdrawal claim |

### 4.2 Validator Status

```solidity
enum ValidatorStatus {
    None,
    Active,
    Exiting,
    Jailed,
    Blacklisted
}
```

| Status | Meaning |
|--------|---------|
| `None` | No active stake and no pending withdrawal |
| `Active` | Eligible for new validator work |
| `Exiting` | Stake is below active threshold or an unbonding withdrawal is pending |
| `Jailed` | Temporarily ineligible; reserved for future lifecycle enforcement |
| `Blacklisted` | Blocked by owner action until explicitly restored |

### 4.3 ValidatorInfo

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
|-------|---------|
| `activeStake` | Stake currently backing validator participation |
| `pendingWithdrawals` | Stake queued for withdrawal but still slashable |
| `withdrawAvailableAt` | Earliest timestamp when `claimUnstaked()` is allowed |
| `jailedUntil` | Reserved timestamp for temporary suspension |
| `status` | Current lifecycle state |

### 4.4 Slashable Stake

The validator’s slashable base is:

```solidity
activeStake + pendingWithdrawals
```

This is exposed by:

```solidity
slashableStakeOf(address validator)
```

---

## 5. Access Control

### 5.1 Permissionless

Any address can:
- `stake(uint256 amount)`
- `unstake(uint256 amount)`
- `claimUnstaked()`

### 5.2 Owner

Only `owner()` can:
- blacklist validators;
- unblacklist validators.

In the current deployment model this owner is the DIN admin / DIN-Representative. Later, ownership can be transferred to a DAO governance executor or timelocked admin.

### 5.3 DIN Coordinator

Only `DIN_COORDINATOR` can:
- add slasher contracts;
- remove slasher contracts.

### 5.4 Authorized Slasher Contracts

Only registered slasher contracts can:
- call `slash(address validator, uint256 amount, bytes32 reason)`.

---

## 6. Lifecycle

### 6.1 Status Flow

```text
None
  -> stake >= MIN_STAKE
Active
  -> unstake requested
Exiting
  -> claim completed and no stake left
None

Active
  -> slash below MIN_STAKE
Exiting

Any non-blacklisted status
  -> blacklist
Blacklisted
  -> owner unblacklist
Active / Exiting / None / Jailed
```

### 6.2 Status Semantics

- `Active` means the validator is currently eligible for new work.
- `Exiting` means the validator is leaving or already below active threshold.
- `Blacklisted` blocks stake, unstake, and withdrawal claims until the owner explicitly clears it.
- `Jailed` exists in the storage model and sync logic but is not yet set by a public function.

### 6.3 Status Synchronization

The contract uses `_syncValidatorStatus()` internally after stake-changing operations.

Effective logic:

1. If blacklisted, keep `Blacklisted`.
2. If jailed and jail time has not expired, keep `Jailed`.
3. If `pendingWithdrawals > 0`, set `Exiting`.
4. Else if `activeStake >= MIN_STAKE`, set `Active`.
5. Else if `activeStake > 0`, set `Exiting`.
6. Else set `None`.

This makes exit state explicit and prevents validators with pending exits from appearing active.

---

## 7. Functions

### 7.1 `stake(uint256 amount)`

Locks DIN into the contract as validator collateral.

Behavior:
- reverts if `amount < MIN_STAKE`;
- reverts if validator is blacklisted;
- transfers DIN from the validator into the contract;
- increases `activeStake`;
- updates validator status.

Effects:
- first stake usually moves validator from `None` to `Active`;
- additional stake increases collateral and keeps status synchronized.

---

### 7.2 `unstake(uint256 amount)`

Starts the validator exit process.

Behavior:
- reverts if validator is blacklisted;
- reverts if `amount == 0`;
- reverts if there is already a pending withdrawal;
- reverts if `activeStake < amount`;
- subtracts from `activeStake`;
- moves the amount into `pendingWithdrawals`;
- sets `withdrawAvailableAt = block.timestamp + UNBONDING_PERIOD`;
- sets status through `_syncValidatorStatus()`.

Important:
- no tokens are transferred out during `unstake()`;
- the validator becomes `Exiting` while a withdrawal is pending;
- pending withdrawal remains slashable.

---

### 7.3 `claimUnstaked()`

Finalizes a matured exit.

Behavior:
- reverts if validator is blacklisted;
- reverts if no pending withdrawal exists;
- reverts if `block.timestamp < withdrawAvailableAt`;
- clears pending withdrawal state;
- updates validator status;
- transfers DIN to the validator.

Important:
- this is the only step that actually releases exited funds;
- once claimed, those funds are no longer slashable because they have left the contract.

---

### 7.4 `slash(address validator, uint256 amount, bytes32 reason)`

Penalizes a validator through an authorized slasher contract.

Behavior:
- only callable by a registered slasher;
- reverts on zero validator address;
- reverts on zero slash amount;
- caps actual slash by the validator’s slashable stake;
- slashes `activeStake` first;
- if needed, continues slashing `pendingWithdrawals`;
- clears `withdrawAvailableAt` if pending withdrawal is fully consumed;
- updates status;
- emits a slash event;
- returns actual slashed amount.

Important:
- slashing does not currently burn or redistribute tokens;
- slashed value remains locked in the contract in the current architecture.

---

### 7.5 `blacklistValidator(address validator)`

Marks a validator as blocked.

Behavior:
- only callable by `owner()`;
- sets status to `Blacklisted`.

Effects:
- validator can no longer stake;
- validator can no longer request withdrawal;
- validator can no longer claim withdrawal;
- funds remain in the contract and can still be slashed.

---

### 7.6 `unblacklistValidator(address validator)`

Restores a previously blacklisted validator to its normal lifecycle state.

Behavior:
- only callable by `owner()`;
- reverts on zero address;
- reverts if the validator is not currently blacklisted;
- clears `Blacklisted` status;
- preserves `Jailed` if `jailedUntil` is still active, otherwise falls back to normal status sync;
- emits `ValidatorUnblacklisted`.

Effects:
- validator returns to `Active`, `Exiting`, `None`, or `Jailed` depending on remaining stake, pending withdrawals, and jail timing;
- validator does not bypass `MIN_STAKE` or exit state checks.

---

### 7.7 View Functions

| Function | Meaning |
|----------|---------|
| `minStake()` | Returns `MIN_STAKE` |
| `isValidatorActive(address)` | `true` only when status is exactly `Active` |
| `getStake(address)` | Returns current `activeStake` only |
| `slashableStakeOf(address)` | Returns `activeStake + pendingWithdrawals` |
| `isSlasherContract(address)` | Returns whether the address is an authorized slasher |

### 7.8 Internal Function: `_syncValidatorStatus(ValidatorInfo storage validator)`

This is the internal lifecycle reconciliation function used by the contract to keep validator status aligned with stake state.

It is not externally callable. It is invoked after stake-affecting operations such as:
- `stake()`
- `unstake()`
- `claimUnstaked()`
- `slash()`

Its job is to derive the correct `ValidatorStatus` from the validator's current balances and lock conditions.

#### Why It Matters

Without `_syncValidatorStatus()`, the contract could easily drift into inconsistent states, for example:
- a validator with enough stake but a pending exit still appearing `Active`;
- a validator with no remaining stake still appearing `Exiting`;
- a slashed validator remaining eligible after falling below `MIN_STAKE`.

This function prevents that by recalculating status whenever balances change.

#### Flow Order

The function follows a strict priority order:

1. Preserve `Blacklisted`
2. Preserve active `Jailed`
3. If `pendingWithdrawals > 0`, set `Exiting`
4. Else if `activeStake >= MIN_STAKE`, set `Active`
5. Else if `activeStake > 0`, set `Exiting`
6. Else set `None`

This order is important because lifecycle state is not decided by stake size alone.

#### Effective Logic

```solidity
function _syncValidatorStatus(ValidatorInfo storage validator) internal {
    if (validator.status == ValidatorStatus.Blacklisted) {
        return;
    }

    if (
        validator.status == ValidatorStatus.Jailed &&
        validator.jailedUntil > block.timestamp
    ) {
        return;
    }

    if (validator.pendingWithdrawals > 0) {
        validator.status = ValidatorStatus.Exiting;
    } else if (validator.activeStake >= MIN_STAKE) {
        validator.status = ValidatorStatus.Active;
    } else if (validator.activeStake > 0) {
        validator.status = ValidatorStatus.Exiting;
    } else {
        validator.status = ValidatorStatus.None;
    }
}
```

#### Decision Tree

```text
Start
  -> Is status Blacklisted?
     -> Yes: keep Blacklisted and stop
     -> No:
        -> Is status Jailed and jailedUntil still in future?
           -> Yes: keep Jailed and stop
           -> No:
              -> pendingWithdrawals > 0 ?
                 -> Yes: Exiting
                 -> No:
                    -> activeStake >= MIN_STAKE ?
                       -> Yes: Active
                       -> No:
                          -> activeStake > 0 ?
                             -> Yes: Exiting
                             -> No: None
```

#### Key Behavior

- `Blacklisted` is sticky. Normal stake changes cannot restore another status.
- `unblacklistValidator()` is the only path that can clear `Blacklisted`.
- `Jailed` is time-protected. The contract will not override it early while the jail window is still active.
- A pending withdrawal always forces `Exiting`.
- A validator cannot remain `Active` while unbonding.
- Zero active and zero pending stake resolves to `None`.

#### Example Outcomes

| State Before Sync | Result After Sync |
|-------------------|------------------|
| `activeStake = 20`, `pendingWithdrawals = 0` | `Active` |
| `activeStake = 20`, `pendingWithdrawals = 5` | `Exiting` |
| `activeStake = 8`, `pendingWithdrawals = 0` | `Exiting` |
| `activeStake = 0`, `pendingWithdrawals = 0` | `None` |
| `status = Blacklisted` | `Blacklisted` |
| `status = Jailed`, `jailedUntil > now` | `Jailed` |

---

## 8. Workflow

This section shows the normal validator workflow from staking to exit.

### 8.1 Validator Onboarding Workflow

1. Validator obtains DIN.
2. Validator approves `DinValidatorStake` to spend DIN.
3. Validator calls `stake(amount)`.
4. Contract transfers DIN in and updates `activeStake`.
5. If stake is at least `MIN_STAKE`, status becomes `Active`.
6. Other DIN contracts query `isValidatorActive()` before allowing validator participation.

### 8.2 Validator Exit Workflow

1. Validator calls `unstake(amount)`.
2. Contract moves `amount` from `activeStake` to `pendingWithdrawals`.
3. Contract sets `withdrawAvailableAt`.
4. Validator status becomes `Exiting`.
5. Validator is no longer eligible for new work.
6. During the unbonding period, slasher contracts may still slash the pending amount.
7. After the unbonding period, validator calls `claimUnstaked()`.
8. Contract transfers the remaining pending amount to the validator.
9. Status becomes `Active`, `Exiting`, or `None` depending on remaining stake.

### 8.3 Slashing Workflow

1. Coordinator registers a slasher contract.
2. Validator performs work or fails work.
3. Slasher contract determines a slashable offense.
4. Slasher contract calls `slash(validator, amount, reason)`.
5. Contract deducts from slashable stake.
6. Validator status is re-evaluated.
7. If remaining active stake is below threshold, validator becomes `Exiting`.

---

## 9. Scenarios

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

## 10. Contract Interactions

### 10.1 With `DINTaskCoordinator` and `DINTaskAuditor`

These contracts should:
- check `isValidatorActive()` before assigning or accepting validator work;
- use `minStake()` as the single source of stake threshold truth;
- call `slash()` only if they are registered as slasher contracts.

### 10.2 With `DINCoordinator`

`DINCoordinator` is the administrative control point for:
- adding slashers;
- removing slashers.

Blacklist and unblacklist actions are not routed through `DINCoordinator` in the current architecture. They are direct `owner()` actions on `DinValidatorStake`.

### 10.3 With Frontends and Off-Chain Services

Off-chain systems should distinguish:
- active stake: `getStake()`;
- total slashable stake: `slashableStakeOf()`;
- validator eligibility: `isValidatorActive()`;
- exit maturity: `validators[addr].withdrawAvailableAt`.

### 10.4 With Governance

DinValidatorStake owner
  ├── calls   → DinValidatorStake.blacklistValidator()
  └── calls   → DinValidatorStake.unblacklistValidator()

---

## 11. Events

| Event | When Emitted |
|-------|--------------|
| `ValidatorStaked` | Stake is successfully added |
| `ValidatorUnstakeRequested` | Exit is started |
| `ValidatorWithdrawalClaimed` | Matured pending withdrawal is paid out |
| `ValidatorSlashed` | A slash succeeds |
| `ValidatorBlacklisted` | Validator is blacklisted |
| `ValidatorUnblacklisted` | Validator blacklist is removed |
| `SlasherContractAdded` | Slasher is authorized |
| `SlasherContractRemoved` | Slasher is de-authorized |

---

## 12. Errors

| Error | Meaning |
|-------|---------|
| `NotDINCoordinator()` | Caller is not the configured coordinator |
| `ValidatorIsBlacklisted()` | Validator is blacklisted and action is blocked |
| `ValidatorNotBlacklisted()` | Unblacklist was requested for a validator that is not blacklisted |
| `InvalidAddress()` | Zero address provided |
| `NotSlasherContract()` | Caller is not an authorized slasher |
| `AmountLessThanMinStake()` | Stake amount is below minimum |
| `NotEnoughStake()` | Validator tried to remove more than active stake |
| `SlasherContractAlreadyAdded()` | Slasher already registered |
| `SlasherContractNotAdded()` | Slasher not registered |
| `InvalidSlashAmount()` | Slash amount is zero |
| `InvalidUnstakeAmount()` | Unstake amount is zero |
| `PendingWithdrawalExists()` | Validator already has an open unbonding request |
| `NoPendingWithdrawal()` | Nothing is available to claim |
| `WithdrawalNotReady()` | Unbonding period has not ended |
| `OwnableUnauthorizedAccount(address)` | Caller is not the stake contract owner for owner-gated actions |

---

## 13. Security Notes

- Immediate validator exits are intentionally prevented.
- Pending withdrawals remain slashable until final claim.
- Eligibility is based on lifecycle status, not raw balance only.
- Re-entrancy protection is applied to token-moving functions.
- Slashed funds are currently not burned or redistributed.

---

## 14. Current Limitations

- `Jailed` exists in the model but is not yet exposed through a public enforcement flow.
- Only one pending withdrawal bucket exists per validator.
- `MIN_STAKE` and `UNBONDING_PERIOD` are compile-time constants.
- Slashed tokens remain in the contract instead of being burned or reallocated.
- Blacklisted funds currently have no separate governance-managed withdrawal path.

---

## 15. Summary

`DinValidatorStake` is not just a token vault. It is a validator lifecycle contract.

Its main production-grade property is that exits are delayed and still slashable. That design closes the most dangerous staking failure mode: a validator doing work, misbehaving, and withdrawing before penalties can be enforced.
