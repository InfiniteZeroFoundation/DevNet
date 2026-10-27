# Foundry Tooling — Technical Documentation

Per-file documentation for the Foundry workspace's supporting code — deploy/upgrade scripts and V2 upgrade fixtures. Foundry (`foundry/`) is the **reference toolchain**: `foundry/src/` holds the current contracts, which are documented one level up in [`Documentation/technical/contracts/`](../). The [Hardhat tooling docs](../hardhat/README.md) describe the older, secondary toolchain, whose contracts lag `foundry/src/`.

| Doc | Source file | What it is |
|-----|-------------|-----------|
| **Scripts** | | |
| [script/DeployPlatform.md](script/DeployPlatform.md) | [`foundry/script/DeployPlatform.s.sol`](../../../../foundry/script/DeployPlatform.s.sol) | Deploys and wires the seven platform proxies; writes `deployments/<network>.json` |
| [script/UpgradePlatform.md](script/UpgradePlatform.md) | [`foundry/script/UpgradePlatform.s.sol`](../../../../foundry/script/UpgradePlatform.s.sol) | Upgrades one platform proxy to its `<Name>V2` implementation |
| [script/DeployFairLaunchDistributor.md](script/DeployFairLaunchDistributor.md) | [`foundry/script/DeployFairLaunchDistributor.s.sol`](../../../../foundry/script/DeployFairLaunchDistributor.s.sol) | Deploys `DinFairLaunchDistributor` behind a proxy |
| [script/DeploymentsPath.md](script/DeploymentsPath.md) | [`foundry/script/DeploymentsPath.sol`](../../../../foundry/script/DeploymentsPath.sol) | Shared chain-ID → `deployments/<network>.json` resolver |
| **Upgrade fixtures** | | |
| [upgrades/V2-fixtures.md](upgrades/V2-fixtures.md) | `foundry/src/upgrade/*V2.sol` | `DinTokenV2`, `DinCoordinatorV2`, `DinValidatorStakeV2`, `DINModelRegistryV2` |

Test suites (`foundry/test/*.t.sol`) are not yet documented per file; the upgrade-related ones are covered in [upgradable-contracts/foundry](../../upgradable-contracts/foundry/README.md).

## Quick commands

```bash
cd foundry && npm ci                                   # required before forge test / scripts (OZ upgrades-core via npx)
forge build
forge test                                             # full suite
forge script script/DeployPlatform.s.sol --rpc-url <rpc> --broadcast ...          # deploy platform
CONTRACT=<Name> forge script script/UpgradePlatform.s.sol --rpc-url <rpc> --broadcast ...   # upgrade one proxy
```

Local and Optimism Sepolia usage (anvil `--unlocked` vs. keystore `--account`/`--sender`) is in each script's page and NatSpec; [DeployPlatform](script/DeployPlatform.md) has the full sequence.
