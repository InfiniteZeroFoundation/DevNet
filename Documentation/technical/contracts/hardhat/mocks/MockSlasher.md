# MockSlasher.sol — Mock Documentation

> **File:** `hardhat/contracts/mocks/MockSlasher.sol`
> **Role:** minimal ownable stand-in for a task (slasher) contract in tests
> **Test-only** — never deployed to a live network

---

## 1. Contents

```solidity
contract MockSlasher is Ownable {
    constructor(address initialOwner) Ownable(initialOwner) {}
}
```

That is the entire contract: OZ `Ownable` (non-upgradeable) with a constructor-set owner. No slashing logic, no functions of its own.

---

## 2. Why It Works as a Slasher Stand-In

The platform's checks on task contracts are all **external observations** — nothing requires the contract to *do* anything:

| Platform check | What it needs | How MockSlasher satisfies it |
|----------------|---------------|------------------------------|
| `DinValidatorStake.onlySlasherContract` | `msg.sender` is a registered address | Tests register the mock's address via `dinCoordinator.addSlasherContract`, then **impersonate the address** (`setBalance` + `ethers.getImpersonatedSigner`) to call `slash` — the mock contract itself never sends the transaction |
| `DINModelRegistry` slasher validation | `dinValidatorStake.isSlasherContract(task)` returns `true` | Same registration |
| `DINModelRegistry` ownership validation | `IOwnable(task).owner()` equals the requester | `Ownable` provides `owner()`; tests deploy the mock with the requester as `initialOwner` (e.g. `MockSlasher.deploy(user.address)`) |

This makes the mock the smallest possible contract that can play a `DINTaskCoordinator` or `DINTaskAuditor` in registry and staking tests, without pulling in the real task contracts' size and setup.

---

## 3. Used By

- `test/DinValidatorStake.test.ts` — slashing and slasher-registry cases
- `test/DinCoordinator.upgrade.test.ts` — slasher wiring survival across upgrade
- `test/DinValidatorStake.upgrade.test.ts` — post-upgrade gate checks
- `test/DINModelRegistry.upgrade.test.ts` — plays both taskCoordinator and taskAuditor in the model registration flow

## 4. Notes

- Registry tests need **two instances** (coordinator and auditor must be distinct addresses — `TaskCoordinatorEqualsTaskAuditor` guard).
- Because the real `slash` caller is an impersonated address rather than contract code, tests do not prove a real task contract can construct the `slash` call — that integration is covered by the Foundry suites for the task contracts.
