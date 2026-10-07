# DinValidatorStake — Technical Documentation

> **File:** [`foundry/src/DinValidatorStake.sol`](../../../foundry/src/DinValidatorStake.sol)
> **SPDX-License-Identifier:** MIT
> **Solidity:** `^0.8.28`
> **Deployment:** once per network behind an OpenZeppelin Transparent Proxy

---

## 1. Overview

`DinValidatorStake` is the staking ledger and validator-lifecycle contract for DIN validators (auditors and aggregators). It:

- holds validators' DIN and tracks each validator's lifecycle status (`None` / `Active` / `Exiting` / `Jailed` / `Blacklisted`);
- enforces an unbonding delay during which unstaked DIN **stays slashable**;
- lets authorised slasher contracts (each model's `DINTaskCoordinator` / `DINTaskAuditor`) slash, with three flavours: full-severity `slash`, partial `slashPartial` with **S5 recidivism** escalation, and the **S6 no-participation** counter;
- splits every slashed amount **50% burned / 50% to `slashTreasury`** (`DinTreasury`), or burns that half too if no treasury is set;
- supports **jailing** (automatic on S5 escalation) and self-service `reactivate()` after the jail period;
- stores governable parameters (`MIN_STAKE`, `UNBONDING_PERIOD`, per-model stake floors, concurrent-registration cap, S5/S6 parameters) that the task contracts read at registration and slashing time;
- keeps validators' X25519 encryption keys for encrypted test-data delivery, and a per-validator active-registration counter.

Its central safety property: a validator cannot misbehave and then withdraw before the penalty lands, because exits are delayed and still slashable.

---

## 2. Inheritance & Dependencies

| Component | Source | Purpose |
|-----------|--------|---------|
| `Initializable` | OpenZeppelin (upgradeable) | Initializer guard |
| `OwnableUpgradeable` | OpenZeppelin (upgradeable) | Owner = DIN-Representative (parameters, blacklist, slash treasury) |
| `ReentrancyGuardTransient` | OpenZeppelin | Re-entrancy lock (transient storage, no slots used) |
| `IERC20` + `SafeERC20` | OpenZeppelin | Stake custody and transfers |
| `IBurnableToken` (local interface) | Local | `DinToken.burn` for the burned half of each slash |

---

## 3. State Variables

### 3.1 Platform references

| Variable | Type | Description |
|----------|------|-------------|
| `DIN_TOKEN` | `IERC20` | Stake token (`DinToken` proxy). Set once in `initialize`; SCREAMING_CASE kept from the pre-proxy `immutable` version. |
| `DIN_COORDINATOR` | `address` | Only address allowed to manage the slasher registry (`DinCoordinator` proxy). Set once in `initialize`. |
| `slashTreasury` | `address` | Receives 50% of every slash; if unset, that half is burned too. Set via `setSlashTreasury` (the deploy script wires `DinTreasury`). The task contracts read the same address for their own treasury flows: the reward-pool treasury share and the treasury half of forfeited dispute bonds and penalties. |

### 3.2 Governable parameters (owner-settable)

| Variable | Default (set in `initialize`) | Setter | Meaning |
|----------|------------------------------|--------|---------|
| `MIN_STAKE` | `10 × 10¹⁸` (10 DIN) | `setMinStake` (non-zero) | Minimum per `stake()` call; `Active` requires `activeStake ≥ MIN_STAKE`; unit for S5/S6 slash sizes |
| `UNBONDING_PERIOD` | `7 days` | `setUnbondingPeriod` (non-zero) | Delay between `unstake` and `claimUnstaked`; not retroactive |
| `modelMinStakeBounds[modelId]` | unset (`{0,0}`) | `setModelStakeBounds(modelId, min, max)` (`min ≤ max`) | Per-model stake floor; `min` is enforced by the task contracts at registration when non-zero (`max` is stored but unused) |
| `maxConcurrentRegistrationsPerStakeUnit` | `0` (off) | `setMaxConcurrentRegistrationsPerStakeUnit` | When non-zero, task contracts cap a validator's concurrent GI registrations at `(stake / MIN_STAKE) × value` |
| `s5RecidivismWindow` | `5` GIs | `setS5RecidivismParams` | Rolling window for counting partial slashes |
| `s5RecidivismThreshold` | `3` | `setS5RecidivismParams` (`0 < threshold ≤ window`) | Partial slashes within the window that trigger escalation |
| `s5JailDuration` | `7 days` | `setS5RecidivismParams` (non-zero) | Jail length applied on escalation |
| `s5GlobalWindow` | `7 days` | `setS5GlobalParams` (both 0 = off, or both > 0) | Time window over which partial slashes from **every** slasher contract are counted (issue No. 193) |
| `s5GlobalThreshold` | `6` | `setS5GlobalParams` | Partial slashes within `s5GlobalWindow`, from any slasher contract, that trigger escalation. `0` = global level off, which is also what a proxy upgraded from an earlier version reads until the setter is called |
| `s6NoParticipationThreshold` | `3` | `setS6NoParticipationThreshold` (non-zero) | No-participation count at which S6 slashing starts |

`MIN_STAKE` (10 DIN) is one of the testnet values still to be decided (issue #155). `DeployPlatform.s.sol` can override `MIN_STAKE` and the S5/S6 parameters at deploy time from environment variables (`MIN_STAKE`, `S5_RECIDIVISM_WINDOW`, `S5_RECIDIVISM_THRESHOLD`, `S5_JAIL_DURATION`, `S5_GLOBAL_WINDOW`, `S5_GLOBAL_THRESHOLD`, `S6_NO_PARTICIPATION_THRESHOLD`).

### 3.3 Per-validator state

| Variable | Type | Description |
|----------|------|-------------|
| `validators` | `mapping(address => ValidatorInfo)` | Lifecycle record (§4) |
| `slasherContracts` | `mapping(address => bool)` | Authorised slashers |
| `encryptionKeys` | `mapping(address => bytes)` | Registered 32-byte X25519 public keys |
| `activeRegistrationCount` | `mapping(address => uint256)` | Open GI registrations across all task contracts |
| `s6NoParticipationCount` | `mapping(address => uint256)` | Lifetime no-participation count (never decays) |
| `_partialSlashGIs` | `mapping(address => mapping(address => uint256[]))` (private) | Partial-slash GI indices per validator **per calling slasher contract** (S5 per-slasher ring) |
| `_partialSlashTimes` | `mapping(address => uint256[])` (private) | Partial-slash block timestamps per validator across **all** slasher contracts (S5 global ring, issue No. 193) |
| `__gap` | `uint256[50]` | Reserved slots |

Slot order is in [storage_layout.md](../storage_layout.md#dinvalidatorstake).

---

## 4. Validator Record & Status

```solidity
enum ValidatorStatus { None, Active, Exiting, Jailed, Blacklisted }

struct ValidatorInfo {
    uint256 activeStake;          // backing current activity
    uint256 pendingWithdrawals;   // unbonding, still slashable
    uint64  withdrawAvailableAt;  // earliest claimUnstaked time
    uint64  jailedUntil;          // jail deadline
    ValidatorStatus status;
}
```

| Status | Meaning |
|--------|---------|
| `None` | No active stake, no pending withdrawal |
| `Active` | No pending withdrawal and `activeStake ≥ MIN_STAKE` — the only status eligible for new work (`isValidatorActive`) |
| `Exiting` | Has a pending withdrawal, or `0 < activeStake < MIN_STAKE` |
| `Jailed` | Set by `_jailInternal` (S5 escalation or `jailValidator`); persists while `jailedUntil > now` |
| `Blacklisted` | Owner-imposed; blocks `stake`, `unstake`, `claimUnstaked` and jailing |

### Status synchronization (`_syncValidatorStatus`)

Run after every stake/unstake/claim/slash/unblacklist/reactivate:

1. `Blacklisted` → unchanged.
2. `Jailed` with `jailedUntil > now` → unchanged.
3. `pendingWithdrawals > 0` → `Exiting`.
4. else `activeStake ≥ MIN_STAKE` → `Active`.
5. else `activeStake > 0` → `Exiting`.
6. else → `None`.

Once a jail has expired, *any* call that syncs status (e.g. `stake`) recomputes the status from rules 3–6, so `reactivate()` is not the only way out of `Jailed` (see §14 No. 3).

---

## 5. Access Control

| Function group | Allowed caller |
|----------------|----------------|
| `stake`, `unstake`, `claimUnstaked`, `reactivate`, `registerEncryptionKey` | Any address, acting on its own record |
| `addSlasherContract`, `removeSlasherContract` | `DIN_COORDINATOR` only (`NotDINCoordinator`) |
| `slash`, `slashPartial`, `recordNoParticipation`, `jailValidator`, `incrementActiveRegistration`, `decrementActiveRegistration` | Registered slasher contracts only (`NotSlasherContract`) |
| `blacklistValidator`, `unblacklistValidator`, `setMinStake`, `setUnbondingPeriod`, `setModelStakeBounds`, `setMaxConcurrentRegistrationsPerStakeUnit`, `setSlashTreasury`, `setS5RecidivismParams`, `setS5GlobalParams`, `setS6NoParticipationThreshold` | `owner()` (DIN-Representative) |

---

## 6. Staking Lifecycle

### `stake(uint256 amount)`
Reverts `AmountLessThanMinStake` if `amount < MIN_STAKE` (per call, not on the total) and `ValidatorIsBlacklisted` if blacklisted. Adds to `activeStake`, syncs status, pulls DIN via `safeTransferFrom` (validator must `approve` first), emits `ValidatorStaked`.

### `unstake(uint256 amount)`
Reverts if blacklisted, `amount == 0` (`InvalidUnstakeAmount`), a withdrawal is already pending (`PendingWithdrawalExists` — only one at a time), or `activeStake < amount` (`NotEnoughStake`). Moves `amount` to `pendingWithdrawals`, sets `withdrawAvailableAt = now + UNBONDING_PERIOD`, syncs (→ `Exiting`), emits `ValidatorUnstakeRequested`.

### `claimUnstaked()`
Reverts if blacklisted, nothing pending (`NoPendingWithdrawal`), or before `withdrawAvailableAt` (`WithdrawalNotReady`). Pays out whatever remains pending (after any slashing), clears the withdrawal, syncs, emits `ValidatorWithdrawalClaimed`.

### `reactivate()`
For a `Jailed` validator: reverts `NotJailed`, `JailPeriodNotExpired`, or `StakeBelowFloor` (`activeStake < MIN_STAKE`). Clears `jailedUntil`, syncs status, emits `ValidatorReactivated`.

---

## 7. Slashing

### 7.1 Common mechanics (`_applySlash`)

- The slash is **capped** at `activeStake + pendingWithdrawals`; a zero result returns `0` without an event.
- Active stake is consumed first, then pending withdrawals (clearing `withdrawAvailableAt` if the withdrawal is wiped out).
- **Distribution:** `burn = amount / 2` is burned via `DinToken.burn`; the rest goes to `slashTreasury` via `safeTransfer`, or is also burned if `slashTreasury` is unset.
- Emits `ValidatorSlashed(validator, actualAmount, reason, slasher)` and returns the actual amount.

### 7.2 `slash(validator, amount, reason)` — full severity

For faults like bad consensus or S3 score deviation. Reverts on zero address / zero amount (`InvalidSlashAmount`); otherwise `_applySlash`.

### 7.3 `slashPartial(validator, amount, reason, giIndex)` — S1/S2 with S5 recidivism

Used by the task contracts for liveness faults (auditor didn't reveal a vote — S1; aggregator didn't reveal a CID — S2). `amount` is computed by the caller as a fraction of the global `MIN_STAKE`: `minStake() × s1SlashFractionBps / 10 000` (auditor) or `× s2SlashFractionBps` (aggregator), with the fractions set per model on the task contracts.

1. Appends `giIndex` to `_partialSlashGIs[validator][msg.sender]` and trims entries with `giIndex − entry ≥ s5RecidivismWindow` (**per-slasher level**).
2. If `s5GlobalThreshold ≠ 0`, also appends `block.timestamp` to `_partialSlashTimes[validator]` and trims entries with `now − entry ≥ s5GlobalWindow` (**global level**, issue No. 193).
3. If the per-slasher ring reaches `s5RecidivismThreshold`, **or** the global ring reaches `s5GlobalThreshold` → **S5 escalation**: slash a full `MIN_STAKE` (reason `S5_RECIDIVISM`), jail for `s5JailDuration`, and clear both this caller's ring and the global ring. It emits `ValidatorEscalatedS5` when the per-slasher level fired, otherwise `ValidatorEscalatedS5Global`.
4. Otherwise slash `amount` with the given reason.

The per-slasher ring is namespaced by the **calling task contract** because `giIndex` is a per-model counter: keying by validator alone would interleave different models' GI sequences and break the ascending-order trim. On its own that counts recidivism per task contract, so misses spread across models, or across one model's coordinator (S2) and auditor (S1), never add up. The global ring closes that gap: block timestamps never go backwards, so one ring per validator stays ascending across every slasher.

### 7.4 `recordNoParticipation(validator, reason)` — S6

Increments `s6NoParticipationCount[validator]` and emits `S6NoParticipationRecorded`. Below `s6NoParticipationThreshold` it returns `0`. At or above it, it slashes `MIN_STAKE × (count − threshold + 1) / 10`, capped at `MIN_STAKE` (10% more per breach), and emits `S6PartialSlashFired`. The count never resets.

> No contract in `foundry/src` currently calls `recordNoParticipation` — the task contracts deliberately skip it where `slashPartial` already applies ("No S6 recordNoParticipation here…"), so S6 is implemented but not wired (§14 No. 1).

### 7.5 Jailing — `jailValidator(validator, duration, reason)`

Slasher-only. Reverts on zero address or zero duration (`InvalidJailDuration`); jailing a blacklisted validator reverts `ValidatorIsBlacklisted`. Extends (never shortens) `jailedUntil`, sets `Jailed`, emits `ValidatorJailed`. No task contract calls it today; jails come from S5 escalation.

---

## 8. Registration Support for Task Contracts

- **Per-model floor:** at aggregator/auditor registration the task contracts revert `TC_/TA_StakeBelowModelFloor` if `getModelStakeMin(modelId) > 0` and `getStake(validator)` is below it.
- **Concurrency cap:** when `maxConcurrentRegistrationsPerStakeUnit > 0`, they revert `TC_/TA_ConcurrentRegistrationCapReached` if `activeRegistrationCount ≥ (getStake / minStake) × cap`.
- **Counter:** `incrementActiveRegistration` on registration, `decrementActiveRegistration` at GI end (saturates at zero); both emit an event.
- **Encryption keys:** `registerEncryptionKey(bytes pubkey)` stores a 32-byte X25519 key (`InvalidEncryptionKey` otherwise). `DINTaskAuditor` requires every auditor in a batch to have one before assigning encrypted test-data keys.

---

## 9. Blacklisting

- `blacklistValidator(v)` sets `Blacklisted` unconditionally (even for addresses with no record).
- `unblacklistValidator(v)` reverts `ValidatorNotBlacklisted` if not blacklisted; restores `Jailed` if the jail is still running, otherwise `None`, then syncs.
- While blacklisted, `stake` / `unstake` / `claimUnstaked` revert, so funds are frozen — but the validator can still be slashed.

---

## 10. Views

| Function | Returns |
|----------|---------|
| `minStake()` | `MIN_STAKE` |
| `isValidatorActive(v)` | `status == Active` |
| `getStake(v)` | `activeStake` |
| `slashableStakeOf(v)` | `activeStake + pendingWithdrawals` |
| `isSlasherContract(a)` | slasher flag |
| `getEncryptionKey(v)` | registered key or empty bytes |
| `getModelStakeMin(modelId)` | `modelMinStakeBounds[modelId].min` |
| `getPartialSlashGIs(v, slasher)` | the S5 per-slasher ring for that validator/caller pair |
| `getPartialSlashTimes(v)` | the S5 global ring (timestamps, all slashers) |

Plus the public getters for all state in §3.

---

## 11. Workflows & Scenarios

Worked examples with the defaults from §3.2 (`MIN_STAKE` = 10 DIN, `UNBONDING_PERIOD` = 7 days, S1/S2 fraction 30%, S5 window 5 / threshold 3 / jail 7 days). Every slashed amount is split as in §7.1: half burned, half to `slashTreasury` (or also burned if it is unset).

### 11.1 Onboarding

1. The validator obtains DIN (e.g. `DinCoordinator.depositAndMint()`) and approves `DinValidatorStake` to spend it.
2. `stake(amount)`: `amount` must be at least `MIN_STAKE` **per call**. The contract pulls the DIN and adds it to `activeStake`.
3. With `activeStake ≥ MIN_STAKE` and nothing pending, the status becomes `Active`.
4. The task contracts check `isValidatorActive()` (plus any per-model floor and concurrency cap, §8) before accepting a registration.

### 11.2 Exit

1. `unstake(amount)` moves `amount` from `activeStake` to `pendingWithdrawals` and sets `withdrawAvailableAt = now + UNBONDING_PERIOD`. Only one withdrawal can be pending at a time.
2. The status becomes `Exiting`, so the validator gets no new work. The pending amount **stays slashable**.
3. After `withdrawAvailableAt`, `claimUnstaked()` pays out whatever is still pending.
4. The status is then recomputed: `Active`, `Exiting` or `None`, depending on the remaining `activeStake`.

### Scenario 1: Normal entry

Stake `20 DIN` → `activeStake = 20`, `pendingWithdrawals = 0`, status `Active`. The validator is eligible for new work.

### Scenario 2: Partial exit with stake left over

Start with `30 DIN`, then `unstake(10)` → `activeStake = 20`, `pendingWithdrawals = 10`, status `Exiting`. The validator is **not** active even though `activeStake ≥ MIN_STAKE`, because an exit is in progress. After `claimUnstaked()` the pending 10 DIN is paid out and the status returns to `Active`.

### Scenario 3: Full exit

Start with `20 DIN`, then `unstake(20)` → `activeStake = 0`, `pendingWithdrawals = 20`, status `Exiting`. After `UNBONDING_PERIOD`, `claimUnstaked()` pays out 20 DIN and the status becomes `None`.

### Scenario 4: Slashed during unbonding

Start with `20 DIN`, then `unstake(10)` → `activeStake = 10`, `pendingWithdrawals = 10`. A slasher then calls `slash(v, 15 DIN, reason)`:
- 10 DIN comes from `activeStake`, then 5 DIN from `pendingWithdrawals`;
- 7.5 DIN is burned and 7.5 DIN goes to `slashTreasury`;
- final state: `activeStake = 0`, `pendingWithdrawals = 5`, status `Exiting`.

Exiting first does not escape the penalty. If the slash had exceeded the 20 DIN slashable balance, it would have been capped at 20 rather than reverting.

### Scenario 5: Claim after a partial slash

Continuing Scenario 4: once `withdrawAvailableAt` passes, `claimUnstaked()` pays out only the remaining **5 DIN**, not the 10 DIN originally requested.

### Scenario 6: Blacklisted validator

After the owner calls `blacklistValidator(v)`, `stake`, `unstake` and `claimUnstaked` all revert with `ValidatorIsBlacklisted`, so the funds are frozen. The validator **can still be slashed**. An S5 escalation against them reverts the whole slash, though (§14 No. 2). The only way out is `unblacklistValidator(v)`, which restores `Jailed` if a jail is still running and otherwise recomputes the status.

### Scenario 7: Slashed below the minimum

Start with `12 DIN`; a 3 DIN slash leaves `activeStake = 9`, so the status becomes `Exiting` (below `MIN_STAKE`) and the validator gets no new work. The minimum applies per call, so `stake(1)` reverts with `AmountLessThanMinStake`. Getting back to `Active` takes `stake(10)` or more.

### Scenario 8: S5 escalation and jail

A validator with `20 DIN` misses a reveal on the same model in three consecutive GIs (1, 2, 3). Each miss arrives as `slashPartial` from that model's task contract:
- **GIs 1 and 2:** each slashes `10 × 30% = 3 DIN` (1.5 burned, 1.5 to the treasury), leaving `activeStake = 14`. That contract's ring for the validator is now `[1, 2]`.
- **GI 3:** the ring becomes `[1, 2, 3]`, reaching the threshold of 3 within the window of 5, so the call **escalates**. It slashes a full `MIN_STAKE` (10 DIN, reason `S5_RECIDIVISM`) instead of 3 DIN, jails the validator for 7 days, emits `ValidatorEscalatedS5` and clears the ring. The result is `activeStake = 4`, status `Jailed`.
- **After the jail:** `reactivate()` reverts with `StakeBelowFloor` (4 < 10). The validator has to `stake(10)` first. Once the jail has expired, that `stake` call already recomputes the status to `Active`, so `reactivate()` is never needed (§14 No. 3).

The ring is kept per calling task contract, so the same three misses spread across three different models would not escalate (§14 No. 5).

---

## 12. Events & Errors

**Events:** `ValidatorStaked`, `ValidatorUnstakeRequested`, `ValidatorWithdrawalClaimed`, `ValidatorSlashed`, `ValidatorJailed`, `ValidatorReactivated`, `ValidatorEscalatedS5`, `ValidatorEscalatedS5Global`, `S6NoParticipationRecorded`, `S6PartialSlashFired`, `ValidatorBlacklisted`, `ValidatorUnblacklisted`, `SlasherContractAdded`, `SlasherContractRemoved`, `ActiveRegistrationIncremented`, `ActiveRegistrationDecremented`, `EncryptionKeyRegistered`, `MinStakeUpdated`, `UnbondingPeriodUpdated`, `ModelStakeBoundsUpdated`, `MaxConcurrentRegistrationsPerStakeUnitUpdated`, `SlashTreasuryUpdated`, `S5RecidivismParamsUpdated`, `S5GlobalParamsUpdated`, `S6ParamsUpdated`.

**Errors:** `NotDINCoordinator`, `NotSlasherContract`, `InvalidAddress`, `ValidatorIsBlacklisted`, `ValidatorNotBlacklisted`, `AmountLessThanMinStake`, `NotEnoughStake`, `InvalidUnstakeAmount`, `PendingWithdrawalExists`, `NoPendingWithdrawal`, `WithdrawalNotReady`, `InvalidSlashAmount`, `SlasherContractAlreadyAdded`, `SlasherContractNotAdded`, `InvalidJailDuration`, `NotJailed`, `JailPeriodNotExpired`, `StakeBelowFloor`, `InvalidMinStake`, `InvalidUnbondingPeriod`, `InvalidStakeBounds`, `InvalidEncryptionKey`, `InvalidS5Params`, `InvalidS6Params`.

---

## 13. Deployment, Ownership & Upgradeability

From `foundry/script/DeployPlatform.s.sol` (see [DeployPlatform](foundry/script/DeployPlatform.md)):

```
7.  DinValidatorStake proxy   initialize(dinToken, dinCoordinator)   ← this contract
8.  dinCoordinator.updateValidatorStakeContract(dinValidatorStake)
9.  dinValidatorStake.setSlashTreasury(dinTreasury)
10. DINModelRegistry proxy    initialize(dinValidatorStake)
```

Until step 8, slasher management through the coordinator reverts `ValidatorStakeContractNotSet`. Until step 9, both halves of every slash are burned.

| Plane | Who | Controls |
|-------|-----|----------|
| `owner()` | DIN-Representative (`initialize` caller) | Parameters, blacklist, slash treasury |
| `DIN_COORDINATOR` | `DinCoordinator` proxy | Slasher registry |
| Slasher contracts | Each model's task contracts | Slashing, jailing, S6, registration counters |
| ProxyAdmin | One per proxy, owned by the deployer | Implementation upgrades |

- **Upgrade path:** `cd foundry && CONTRACT=DinValidatorStake forge script script/UpgradePlatform.s.sol ...` (see [UpgradePlatform](foundry/script/UpgradePlatform.md)); `foundry/test/UpgradeValidation.t.sol` runs `Upgrades.validateImplementation` on the implementation, and `DinValidatorStakeUpgradeTest` in `foundry/test/DeployPlatform.t.sol` upgrades to `foundry/src/upgrade/DinValidatorStakeV2.sol` and checks stakes and access control survive.
- **Storage:** the S5 global level appends three slots (`s5GlobalWindow`, `s5GlobalThreshold`, `_partialSlashTimes`) after the S6 block and shrinks `__gap` from 50 to 47, so the layout stays upgrade-compatible.
- **Trust implication:** this contract custodies all staked DIN; the ProxyAdmin owner can replace every rule here without moving the balance.

---

## 14. Review Notes & Open Caveats

- **No. 1 — S6 is not wired:** `recordNoParticipation` exists and is tested, but no task contract calls it, so the S6 counter never moves in practice.
- **No. 2 — S5 escalation on a blacklisted validator reverts the whole slash:** escalation calls `_jailInternal`, which reverts `ValidatorIsBlacklisted`. A task contract's slashing loop hitting a blacklisted repeat offender would revert, not just skip that validator.
- **No. 3 — Jail exit does not require `reactivate()`:** after `jailedUntil` passes, any status-syncing call (e.g. `stake`) recomputes the status, bypassing `reactivate()`'s `StakeBelowFloor` check (the later sync still requires `≥ MIN_STAKE` for `Active`).
- **No. 4 — Stale NatSpec:** `setModelStakeBounds` / `setMaxConcurrentRegistrationsPerStakeUnit` say "not yet enforced", but the task contracts enforce both (§8). `getModelStakeMin` says "set by the model owner", but the setter is `onlyOwner` (DIN-Representative). `modelMinStakeBounds[].max` is never read.
- **No. 5 — Recidivism is per model (fixed, issue No. 193):** the per-slasher ring is keyed by calling contract, so on its own a validator faulting across many models never escalates. The global ring (`s5GlobalWindow` / `s5GlobalThreshold`, defaults 7 days / 6) now counts every slasher's partial slashes together. Defaults are placeholders until issue No. 155. A proxy upgraded from an earlier version reads `0` for both, so the global level stays off until the owner calls `setS5GlobalParams`.
- **No. 6 — Blacklisted funds are frozen:** blacklisted validators cannot unstake or claim; there is no recovery path other than unblacklisting.
- **No. 7 — Custody meets upgradeability:** see §13.

---

## 15. Change Log

### Cross-model S5 (issue No. 193)

- `slashPartial` keeps the per-slasher GI ring and adds a per-validator timestamp ring shared by every slasher contract (`_partialSlashTimes`). Either level reaching its threshold escalates (full `MIN_STAKE` + jail) and clears both rings.
- New owner-settable `s5GlobalWindow` (7 days) / `s5GlobalThreshold` (6), set in `initialize`; `setS5GlobalParams(window, threshold)` with (0, 0) as the off switch. On an upgraded proxy both read 0 (off); no reinitializer.
- New events `ValidatorEscalatedS5Global` (emitted when only the global level fired; `ValidatorEscalatedS5` keeps its signature) and `S5GlobalParamsUpdated`; new view `getPartialSlashTimes`. `__gap` 50 → 47.

### P3 — slashing, jailing, parameters (foundry)

- Slashed DIN is now disposed of: 50% burned, 50% to `slashTreasury` (`setSlashTreasury`), or also burned if no treasury is set.
- Added `slashPartial` with S5 recidivism escalation (per-caller ring), `recordNoParticipation` (S6), `jailValidator` / `reactivate`.
- `MIN_STAKE` and `UNBONDING_PERIOD` became owner-settable storage; added per-model stake bounds, the concurrent-registration cap, the active-registration counter, and X25519 encryption-key registration.

### 2026-07 — Upgradeable conversion (PR 13)

- Converted to a Transparent Proxy (`Initializable` + `OwnableUpgradeable`, `_disableInitializers()` constructor, `initialize(dinToken, dinCoordinator)`); `DIN_TOKEN` / `DIN_COORDINATOR` lost `immutable`; added `__gap`.
