# DINModelRegistry.upgrade.test.ts — Test Documentation

> **File:** `hardhat/test/DINModelRegistry.upgrade.test.ts`
> **Subject under test:** `DINModelRegistry` upgrade safety (Transparent Proxy)
> **Run:** `cd hardhat && npx hardhat test test/DINModelRegistry.upgrade.test.ts`

---

## 1. Purpose

Verifies that upgrading the `DINModelRegistry` proxy preserves governance settings (fees), registered models, and **pending** registration requests — including that a request submitted before an upgrade can still be approved after it. Upgrade target: [`DINModelRegistryV2`](../upgrades/DINModelRegistryV2.md) (adds only `version() == 2`).

This suite exercises the most end-to-end flow of the four upgrade suites: it walks a real model registration (slasher authorisation → request → approval) before upgrading.

---

## 2. Test Cases

| Test | Scenario | Asserts |
|------|----------|---------|
| preserves fee settings and model state across upgrade | Sets a custom `proprietaryFee` (42 wei); deploys two `MockSlasher`s owned by `user`, authorises both via `dinCoordinator.addSlasherContract`; `user` requests registration with the fee; owner approves; `validateUpgrade` + upgrade | Custom fee survives; `totalModels() == 1`; `version() == 2`; the full `Model` record (owner, manifestCID, taskCoordinator, taskAuditor) is intact |
| keeps owner-only governance restricted after upgrade | Upgrade, then non-owner calls `setProprietaryFee` | Reverts `OwnableUnauthorizedAccount` |
| keeps pending requests readable after upgrade | Submit a request but do **not** process it; upgrade | `totalModelRequests() == 1`; the stored request's `requester`/`processed` fields intact; the owner can still `approveModel(0)` post-upgrade and `totalModels()` becomes 1 |
| implementation contract cannot be initialized directly | Deploys raw implementation, calls `initialize(addr)` | Reverts `InvalidInitialization` |

---

## 3. The "implementation cannot be initialized directly" test, explained

```ts
const impl = await DINModelRegistry.deploy();   // succeeds — plain deployment
await expect(impl.initialize(signer.address))   // reverts InvalidInitialization
```

The test separates two things that sound alike but differ:

- **Deploying the implementation directly is allowed** — the test itself does
  it, and the real deploy flow requires it (the implementation always goes on
  chain as an ordinary contract before the proxy can reference it).
- **Initializing it directly is blocked by design.** `Initializable` keeps an
  initialization version counter in *storage*. The implementation's
  constructor runs `_disableInitializers()`, and a constructor executes
  against the implementation's **own** storage — so the implementation's copy
  of that counter is permanently set to `type(uint64).max` ("already
  initialized"). Any direct `initialize` call on the implementation address
  reverts with `InvalidInitialization`.

The **proxy's** storage is a separate world where the counter is still `0` —
which is why the delegatecalled `initialize()` during proxy construction
succeeds exactly once, after which the `initializer` modifier bricks it in the
proxy's storage too.

Why assert this at all: without `_disableInitializers()`, anyone could call
`initialize` on the bare implementation and become its `owner()`. That never
touches the proxy's state, but an attacker-owned implementation is a known
risk surface (the Parity wallet kill was an initialized implementation that
could be `selfdestruct`ed) and at minimum a confusing on-chain decoy.

Consequence: a directly-deployed `DINModelRegistry` can never be initialized,
so it can never have an owner or wired stake contract — the contract is only
*usable* behind a proxy. The same test (and reasoning) appears in all four
`*.upgrade.test.ts` suites; see also Step 2 of
[deploy/helpers.md](../deploy/helpers.md).

---

## 4. What the Suite Establishes

- **Approval-time revalidation still passes post-upgrade** for a request created pre-upgrade — the third test approves after the swap, which re-runs the slasher and ownership checks against the surviving `MockSlasher` state.
- Demonstrates how model registration is tested end-to-end: `MockSlasher(user.address)` satisfies both the `isSlasherContract` check (after coordinator authorisation) and the `IOwnable(task).owner() == requester` check (see [MockSlasher.md](../mocks/MockSlasher.md)).

## 5. Coverage Gaps

- Manifest update requests, the kill switch (`disableModel`), and `withdrawFees` are not exercised across an upgrade.
- The `daoAdmin()` / `setDAOAdmin()` compatibility shims are untested here (and have no functional suite either).
- No functional (non-upgrade) suite exists for the registry at all — request/approve/reject edge cases are only covered incidentally by this file.
