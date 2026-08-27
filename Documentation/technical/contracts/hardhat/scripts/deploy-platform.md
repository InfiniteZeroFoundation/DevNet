# deploy-platform.ts — Script Documentation

> **File:** `hardhat/scripts/deploy-platform.ts`
> **Role:** one-shot deployment of the full DIN platform behind Transparent Proxies
> **Run:** `cd hardhat && npx hardhat run scripts/deploy-platform.ts --network <network>`

---

## 1. Purpose

Deploys all four platform contracts (`DinToken`, `DinCoordinator`, `DinValidatorStake`, `DINModelRegistry`) as OpenZeppelin **Transparent Proxies**, performs the two post-deploy wiring calls, and records every address in `hardhat/deployments/<network>.json`.

This script is the **canonical definition of the platform wiring order** — the test fixture ([`test/helpers/platform.ts`](../tests/helpers/platform.md)) mirrors it step for step.

---

## 2. What It Does

| Step | Action | Notes |
|------|--------|-------|
| 1 | Deploy `DinToken` proxy → `initialize()` | Token exists but has **no minter** yet |
| 2 | Deploy `DinCoordinator` proxy → `initialize(dinTokenAddress)` | Coordinator knows the token; token doesn't know the coordinator |
| 3 | `dinToken.setCoordinator(dinCoordinatorAddress)` | One-shot wiring — minting (and therefore `depositAndMint`) goes live here |
| 4 | Deploy `DinValidatorStake` proxy → `initialize(dinTokenAddress, dinCoordinatorAddress)` | Staking is functional from this point |
| 5 | `dinCoordinator.updateValidatorStakeContract(dinValidatorStakeAddress)` | Enables slasher management through the coordinator |
| 6 | Deploy `DINModelRegistry` proxy → `initialize(dinValidatorStakeAddress)` | Registry needs the stake proxy for slasher verification |
| 7 | `getProxyAdminAddress(dinToken)` + `savePlatformAddresses(...)` | Writes `deployments/<network>.json` |

Each proxy is created with `deployTransparentProxy` from [`deploy/helpers.ts`](../deploy/helpers.md), which passes the initializer args into `upgrades.deployProxy` — so **initialization is atomic with proxy creation** (no front-running window between deploy and init).

Every wiring transaction is awaited (`.wait()`) before the next step, so a failure leaves an obvious partial state rather than racing ahead.

---

## 3. Output: `deployments/<network>.json`

Shape defined by [`deploy/types.ts`](../deploy/types.md) (`PlatformAddresses`):

```json
{
  "dinToken": "0x…",
  "dinCoordinator": "0x…",
  "dinValidatorStake": "0x…",
  "dinModelRegistry": "0x…",
  "proxyAdmin": "0x…"
}
```

- Addresses are the **proxy** addresses — the permanent, user-facing ones.
- `proxyAdmin` is read from the `DinToken` proxy's ERC-1967 admin slot. The OZ upgrades plugin reuses one ProxyAdmin per deployer+network in a deployment run, so a single value is recorded.
- `implementations` (per-contract implementation addresses) is populated later by [`upgrade-platform.ts`](upgrade-platform.md), not by this script.
- The upgrade script **requires** this file — losing it means the upgrade tooling can't find the proxies (recoverable from chain data, but avoid it; commit or back up the file).

---

## 4. Roles After Running

The signer executing the script (first configured account for the network) ends up holding **every** privileged role:

| Role | Holder after deploy |
|------|--------------------|
| `owner()` of all four contracts | Deployer |
| ProxyAdmin owner (upgrade rights) | Deployer |
| `DinToken.coordinator` (minter) | `DinCoordinator` proxy (contract, not a person) |

Transferring `owner()` / ProxyAdmin ownership to the DIN-Representative multisig is a **manual follow-up step** — the script does not do it.

---

## 5. Failure Modes

| Interrupted after | Symptom | Recovery |
|-------------------|---------|----------|
| Step 1–2 | `depositAndMint` reverts `Unauthorized` (no minter wired) | Run `setCoordinator` manually, continue |
| Step 3–4 | Coordinator slasher management reverts `ValidatorStakeContractNotSet` | Run `updateValidatorStakeContract` manually, continue |
| Step 5–6 | No deployments file written | Re-run wiring-safe steps manually; note `setCoordinator` **cannot** be re-run (one-shot) — a full re-run of the script deploys fresh proxies instead |

The script has no idempotence/resume logic: a re-run always deploys a **new** set of proxies.
