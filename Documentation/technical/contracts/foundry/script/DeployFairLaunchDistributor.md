# DeployFairLaunchDistributor.s.sol

> **File:** [`foundry/script/DeployFairLaunchDistributor.s.sol`](../../../../../foundry/script/DeployFairLaunchDistributor.s.sol)
> **Inherits:** [`DeploymentsPath`](DeploymentsPath.md) (→ `forge-std` `Script`)

Deploys `DinFairLaunchDistributor` ([`foundry/src/DinFairLaunchDistributor.sol`](../../../../../foundry/src/DinFairLaunchDistributor.sol)) behind a Transparent Proxy.

## Behavior

1. Reads `dinToken` from the platform deployments file `foundry/deployments/<network>.json` — so [DeployPlatform](DeployPlatform.md) must have run on the same chain first.
2. Reads optional environment variables, falling back to placeholders with a `[WARN]` log:

   | Variable | Default | Meaning |
   |----------|---------|---------|
   | `TREASURY_ADMIN` | the broadcaster | Distributor owner / treasury admin (use a Gnosis Safe in production) |
   | `CLIFF_DURATION_SECONDS` | 90 days | Vesting cliff |
   | `VESTING_DURATION_SECONDS` | 365 days | Total vesting |

3. Broadcasts `Upgrades.deployTransparentProxy("DinFairLaunchDistributor.sol:DinFairLaunchDistributor", msg.sender, initialize(dinToken, treasuryAdmin, cliff, vesting))`. The broadcaster owns the ProxyAdmin.
4. Writes `{ dinFairLaunchDistributor, proxyAdminFairLaunch }` to `foundry/deployments/fair-launch-<network>.json`.

## Usage

```bash
cd foundry && TREASURY_ADMIN=0x… CLIFF_DURATION_SECONDS=7776000 VESTING_DURATION_SECONDS=31536000 \
  forge script script/DeployFairLaunchDistributor.s.sol --rpc-url <rpc> --broadcast ...
```

## Notes

- Not imported by `dincli system import-deployments`; dincli manages only platform and task contracts, so record the address manually.
- Funding the distributor with DIN and the treasury admin's approvals are separate, manual steps.
- `fair-launch-localhost.json` is gitignored like `localhost.json`.
