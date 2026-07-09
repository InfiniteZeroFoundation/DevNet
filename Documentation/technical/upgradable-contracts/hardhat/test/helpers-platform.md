# `test/helpers/platform.ts` — Shared Platform Deployment Fixture

Not a test file — the shared fixture every suite builds on. It exists so that all tests exercise the **exact same proxy deployment path** production uses, instead of each suite hand-rolling (and drifting from) the wiring.

## `deployPlatform(): Promise<PlatformFixture>`

Deploys the full 4-contract platform behind Transparent Proxies, in the canonical 6-step order (identical to `scripts/deploy-platform.ts`):

```
1. DinToken proxy            → initialize()
2. DinCoordinator proxy      → initialize(dinTokenAddress)
3. dinToken.setCoordinator(dinCoordinatorAddress)     // one-shot wiring
4. DinValidatorStake proxy   → initialize(dinTokenAddress, dinCoordinatorAddress)
5. dinCoordinator.updateValidatorStakeContract(stakeAddress)
6. DINModelRegistry proxy    → initialize(stakeAddress)
```

Each deploy goes through `deployTransparentProxy()` from `hardhat/deploy/helpers.ts` — the same `upgrades.deployProxy(..., { kind: "transparent" })` wrapper the production script uses. This is a deliberate design point: **if the wiring order in the fixture and the deploy script ever diverge, tests stop reflecting reality.** They share the constant (`PROXY_KIND`) and the helper, so they can't.

### Returned fixture

| Field | What it is |
|---|---|
| `deployer` | Signer 0 — owner of all four proxies (the DIN-Representative role in tests) |
| `user` | Signer 1 — a regular participant (mints DIN, stakes, registers models) |
| `other` | Signer 2 — an unauthorized third party, used for negative access-control assertions |
| `dinToken`, `dinCoordinator`, `dinValidatorStake`, `dinModelRegistry` | Ethers `Contract` handles **attached to the proxy addresses** (never to raw implementations) |

## `mintDinViaDeposit(dinCoordinator, user, ethAmount)`

One-liner wrapper around `dinCoordinator.connect(user).depositAndMint({ value: ethAmount })`.

This is the **only** way tests obtain DIN — through the real economic path (ETH deposit → coordinator mints at `dinPerEth`), not through any privileged mint backdoor. At the default rate (1,000,000 DIN/ETH), the commonly used `10_000_000_000_000_000n` wei (0.01 ETH) yields 10,000 DIN — comfortably above the 10-DIN `MIN_STAKE`.

## Why fresh deployment per test (no snapshots)

`deployPlatform()` is called at the top of each test rather than via `loadFixture` snapshots. Slower, but each test gets a fully isolated chain state, and — importantly for upgrade tests — each test controls exactly *when* in its scenario the upgrade happens relative to state creation. Total suite runtime is ~6 s, so isolation wins over speed here.
