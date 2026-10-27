# DeploymentsPath.sol

> **File:** [`foundry/script/DeploymentsPath.sol`](../../../../../foundry/script/DeploymentsPath.sol)
> **Type:** `abstract contract DeploymentsPath is Script`

Shared helper for the deploy and upgrade scripts. It resolves the per-network deployments file so each chain keeps its own addresses, and its file names match what `dincli system import-deployments` looks up.

## Functions

```solidity
function _deploymentsNetwork() internal view returns (string memory)
function _resolveDeploymentsNetwork(string memory override_, uint256 chainId) internal pure returns (string memory)
function _deploymentsFile(string memory prefix) internal view returns (string memory)
```

`_deploymentsNetwork()` reads `DEPLOYMENTS_NETWORK` (`vm.envOr`, default `""`) and `block.chainid`, and hands both to the pure `_resolveDeploymentsNetwork`, which:

1. Returns the override if it is non-empty. An exported-but-empty `DEPLOYMENTS_NETWORK` counts as unset.
2. Otherwise maps the chain ID:

   | Chain ID | Network name | dincli network |
   |----------|--------------|----------------|
   | 1337, 31337 | `localhost` | `local` (mapped to `localhost` by `import-deployments`) |
   | 11155420 | `sepolia_op_devnet` | `sepolia_op_devnet` |

3. Any other chain reverts: `DeploymentsPath: no deployments network for chain id <id>; set DEPLOYMENTS_NETWORK`.

`_deploymentsFile(prefix)` returns `<foundry root>/deployments/<prefix><network>.json` — `""` for platform addresses, `"fair-launch-"` for the fair-launch distributor.

The override also covers chains that aren't in the table (e.g. a future mainnet before its ID is added).

## Tested by

[`foundry/test/DeploymentsPath.t.sol`](../../../../../foundry/test/DeploymentsPath.t.sol) exposes the helpers through a harness and tests the pure resolver directly: both local chain IDs, Optimism Sepolia, the exact revert message for an unknown chain, override precedence on known and unknown chains, and empty-as-unset. It never calls `vm.setEnv`, because that changes the process environment shared by forge's parallel test functions. The one `_deploymentsFile` test uses `vm.chainId`, which only affects that test's EVM.

## Used by

[DeployPlatform](DeployPlatform.md) (writes), [UpgradePlatform](UpgradePlatform.md) (reads), [DeployFairLaunchDistributor](DeployFairLaunchDistributor.md) (reads the platform file, writes its own).

## Why

Before this helper existed, every script hard-coded `deployments/localhost.json`. That made an Optimism Sepolia deploy overwrite local addresses, and let later upgrade or fair-launch runs read the wrong chain's proxies. Reverting on an unknown chain is deliberate: guessing a file name is how the wrong addresses would end up in use.
