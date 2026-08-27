# platform.ts — Test Helper Documentation

> **File:** `hardhat/test/helpers/platform.ts`
> **Role:** shared platform-deployment fixture for all Hardhat test suites

---

## 1. Purpose

Deploys the complete DIN platform — all four contracts behind Transparent Proxies, fully wired — exactly the way `scripts/deploy-platform.ts` does in production. Every test suite starts from this fixture, which keeps the tests honest: nothing is deployed "bare" or wired by shortcut, so a test passing here implies the production wiring order works.

---

## 2. Exports

### `PlatformFixture` (interface)

| Field | Description |
|-------|-------------|
| `deployer` | First Hardhat signer — runs every `initialize`, so it is the `owner()` of all four contracts and the ProxyAdmin owner |
| `user` | Second signer — plays the model owner / validator / token holder |
| `other` | Third signer — plays the unauthorized caller in negative tests |
| `dinToken`, `dinCoordinator`, `dinValidatorStake`, `dinModelRegistry` | Ethers `Contract` handles attached to the **proxy** addresses |

### `deployPlatform(): Promise<PlatformFixture>`

Mirrors the production deploy script step for step (see [deploy-platform.md](../../scripts/deploy-platform.md)):

```
1. DinToken proxy            initialize()
2. DinCoordinator proxy      initialize(dinToken)
3. dinToken.setCoordinator(dinCoordinator)
4. DinValidatorStake proxy   initialize(dinToken, dinCoordinator)
5. dinCoordinator.updateValidatorStakeContract(dinValidatorStake)
6. DINModelRegistry proxy    initialize(dinValidatorStake)
```

All proxies are created with `deployTransparentProxy` from [`deploy/helpers.ts`](../../deploy/helpers.md) — the same wrapper the production script uses.

### `mintDinViaDeposit(dinCoordinator, user, ethAmount)`

Funds a signer with DIN **the real way**: `dinCoordinator.depositAndMint({ value: ethAmount })`. There is no test-only mint backdoor (there can't be — `mint` is `onlyCoordinator`), so every test that needs DIN also implicitly regression-tests the deposit → mint path. At the default rate, `0.01 ETH` yields `10,000 DIN`.

---

## 3. Usage Pattern

```ts
const { deployer, user, other, dinValidatorStake } = await deployPlatform();
await mintDinViaDeposit(dinCoordinator, user, 10_000_000_000_000_000n);
```

Suites layer their own setup on top (e.g. `DinValidatorStake.test.ts` adds a `MockSlasher` and a token approval in its local `setup()`).

---

## 4. Notes & Caveats

- **No `loadFixture` snapshotting:** each call redeploys the platform from scratch rather than using `@nomicfoundation/hardhat-network-helpers` `loadFixture`. Correct but slower; see [§5](#5-adopting-loadfixture) for how to adopt it.
- **Deployer concentration is intentional:** one signer holding every owner role matches the current single-operator deployment reality; tests that need role separation must transfer ownership explicitly.
- The fixture returns `Contract` (loosely typed) rather than TypeChain-typed handles; call sites rely on runtime ABI resolution.

---

## 5. Adopting `loadFixture`

### How it works


`loadFixture(fn)` from `@nomicfoundation/hardhat-network-helpers` (already a
test dependency — `DinValidatorStake.test.ts` imports `setBalance`/`time` from
it) keys an EVM snapshot by the **function reference** passed in:

- **First call** with a given function: runs it, takes a snapshot of the
  Hardhat network state, and returns the function's result.
- **Every later call** with the *same* function reference: reverts the chain to
  that snapshot (undoing whatever the previous test did) and returns the
  cached result — no redeploy, typically an order of magnitude faster than
  re-running the deployment.

Because the snapshot is keyed by function identity, the fixture function must
be defined **once at module scope**. An arrow function created inline inside
each `it` is a new reference every time and silently defeats the caching.

### Where to call it — test files, not `platform.ts`

`deployPlatform` should stay a plain async function. `loadFixture` belongs at
the **call site** in the test files, for two reasons:

1. Suites layer their own setup on top of the platform (e.g.
   `DinValidatorStake.test.ts` adds `MockSlasher`, mints DIN, approves the
   stake contract in its local `setup()`). Wrapping only `deployPlatform`
   inside the helper would snapshot the bare platform but still re-run the
   suite-local layering per test. Wrapping the suite's *outer* `setup`
   captures everything in one snapshot.
2. Keeping the helper free of `loadFixture` leaves it usable outside Mocha
   (scripts, ad-hoc REPL debugging), where the snapshot machinery isn't
   available.

### Usage

For a suite with no extra setup, wrap `deployPlatform` directly:

```ts
import { loadFixture } from "@nomicfoundation/hardhat-network-helpers";
import { deployPlatform } from "./helpers/platform";

it("...", async function () {
  const { user, dinValidatorStake } = await loadFixture(deployPlatform);
  // ...
});
```

For a suite with its own module-scope `setup()` (the `DinValidatorStake.test.ts`
pattern), keep `setup` calling `deployPlatform()` unchanged and wrap `setup`
itself — replace each `await setup()` inside the tests with:

```ts
const fixture = await loadFixture(setup);
```

Each suite's distinct setup function gets its own snapshot, and tests remain
fully isolated: any state a test creates after the fixture is rolled back the
next time `loadFixture` reverts to the snapshot.

One caveat: fixtures that depend on wall-clock assumptions (e.g. unbonding
windows advanced with `time.increase`) are also rolled back — the snapshot
restores the EVM timestamp, so per-test time manipulation keeps working as
before.
