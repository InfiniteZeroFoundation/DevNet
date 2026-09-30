# UpgradePlatform.s.sol

> **File:** [`foundry/script/UpgradePlatform.s.sol`](../../../../../foundry/script/UpgradePlatform.s.sol)
> **Inherits:** [`DeploymentsPath`](DeploymentsPath.md) (→ `forge-std` `Script`)

Upgrades a single platform proxy to its **`<Name>V2`** implementation.

## Behavior

1. Reads `CONTRACT` from the environment — one of `DinToken`, `DinCoordinator`, `DinValidatorStake`, `DINModelRegistry` (anything else reverts with "Unknown CONTRACT …").
2. Loads the proxy address for that contract (`dinToken`, `dinCoordinator`, `dinValidatorStake`, `dinModelRegistry` key) from `foundry/deployments/<network>.json`, resolved by [`DeploymentsPath`](DeploymentsPath.md) from the chain ID.
3. Broadcasts `Upgrades.upgradeProxy(proxy, "<Name>V2.sol:<Name>V2", "")`. This runs OpenZeppelin's upgrade-safety validation against the reference named in the V2 contract's `@custom:oz-upgrades-from` annotation before deploying the new implementation and upgrading through the proxy's ProxyAdmin.
4. Logs the new implementation address (`Upgrades.getImplementationAddress`).

The broadcaster must own the proxy's ProxyAdmin (the deployer from [DeployPlatform](DeployPlatform.md)).

## Usage

```bash
cd foundry && CONTRACT=DinToken forge script script/UpgradePlatform.s.sol \
  --rpc-url http://127.0.0.1:8545 --broadcast \
  --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 --unlocked
```

On Optimism Sepolia use `--rpc-url "$SEPOLIA_OP_DEVNET_RPC_URL"` (from `.env.sepolia_op_devnet`) with `--account <keystore_name> --sender <din_representative_address>` instead of `--unlocked`; the proxy address then comes from `foundry/deployments/sepolia_op_devnet.json`.

## Limitations

- **Fixed target:** the new implementation is always `<Name>V2` from `foundry/src/upgrade/`. Those fixtures only add `version() == 2` (see [V2 fixtures](../upgrades/V2-fixtures.md)), so today this script exercises the upgrade path rather than shipping real upgrades. A real upgrade means pointing it at a new implementation contract.
- **Four of seven contracts:** `DinTreasury`, `DinFeeRouter` and `DinEmission` are not supported (no `CONTRACT` mapping, no V2 fixtures).
- **No re-initialization data:** it passes empty calldata, which is fine only while a new version adds no state that needs setup.
- **Deployments file not updated:** the new implementation address is logged only, not written back.
