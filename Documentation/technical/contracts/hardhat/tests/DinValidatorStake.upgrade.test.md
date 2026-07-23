# DinValidatorStake.upgrade.test.ts — Test Documentation

> **File:** `hardhat/test/DinValidatorStake.upgrade.test.ts`
> **Subject under test:** `DinValidatorStake` upgrade safety (Transparent Proxy)
> **Run:** `cd hardhat && npx hardhat test test/DinValidatorStake.upgrade.test.ts`

---

## 1. Purpose

Verifies that upgrading the `DinValidatorStake` proxy — the contract holding **all staked DIN** — preserves stake balances, validator status, and both privileged gates (`DIN_COORDINATOR` for the slasher registry, OZ owner for blacklisting). Upgrade target: [`DinValidatorStakeV2`](../upgrades/DinValidatorStakeV2.md) (adds only `version() == 2`).

Uses the same suite constants as the functional suite (`MIN_STAKE`, `STAKE_DEPOSIT_ETH`) and the [`test/helpers/platform.ts`](helpers/platform.md) fixture; DIN is acquired via a real `depositAndMint`.

---

## 2. Test Cases

| Test | Scenario | Asserts |
|------|----------|---------|
| preserves stake balances across upgrade | Mint DIN, approve, `stake(MIN_STAKE)`, `validateUpgrade`, upgrade | `getStake` unchanged; `isValidatorActive` still `true`; `version() == 2` |
| keeps slasher registration restricted to coordinator after upgrade | Upgrade, then an EOA calls `addSlasherContract` directly | Reverts `NotDINCoordinator` — the `DIN_COORDINATOR` storage value survived |
| keeps blacklist control with owner after upgrade | Stake, upgrade, owner blacklists; non-owner tries to unblacklist | Blacklist works post-upgrade (`isValidatorActive` false); non-owner reverts `OwnableUnauthorizedAccount` |
| implementation contract cannot be initialized directly | Deploys raw implementation, calls `initialize(addr1, addr2)` | Reverts `InvalidInitialization` |

---

## 3. What the Suite Establishes

- **Custody survives upgrades:** the staked-token balance and the `validators` mapping live at the proxy address, and an implementation swap does not disturb an in-flight validator position.
- The formerly-immutable `DIN_TOKEN` / `DIN_COORDINATOR` values, now storage variables set in `initialize`, are shown to persist through the upgrade (the `NotDINCoordinator` test would fail if `DIN_COORDINATOR` were lost).

## 4. Coverage Gaps

- No upgrade test with a **pending withdrawal in flight** (unstake → upgrade → `claimUnstaked` after the window) — the most custody-sensitive path across an upgrade.
- The slasher registry's contents (an already-registered slasher surviving the upgrade) are covered in the *coordinator* upgrade suite rather than here.
