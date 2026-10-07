# DeployPlatform.s.sol

> **File:** [`foundry/script/DeployPlatform.s.sol`](../../../../../foundry/script/DeployPlatform.s.sol)
> **Inherits:** [`DeploymentsPath`](DeploymentsPath.md) (→ `forge-std` `Script`)

The canonical platform deployment. It deploys the seven platform contracts behind OpenZeppelin Transparent Proxies (via `Upgrades.deployTransparentProxy`, which runs the OZ upgrade-safety validation), wires them together, and writes their addresses to `foundry/deployments/<network>.json` for `dincli system import-deployments`.

The deployer becomes `owner()` of every contract and the owner of every ProxyAdmin — this is the DIN-Representative.

## Structure

`run()` is what `forge script` calls. It does three things in order:

1. **`readTokenomics()`:** reads the 13 tokenomics keys below with `vm.envOr`, falling back to `defaultTokenomics()`, and logs `[INFO] <KEY> not set - using default: <value>` for every key that is absent.
2. **`deploy(Tokenomics, deployer)`:** runs steps 1–15 under `vm.startBroadcast(deployer)`, and passes `deployer` as the owner of all seven ProxyAdmins. `run()` passes `msg.sender`, i.e. forge script's `--sender`. It returns a `Deployment` struct with the 7 proxies and 7 ProxyAdmins.
3. **`_writeDeployments(...)`:** step 16, after `vm.stopBroadcast()`.

Tests call `deploy()` directly with explicit values, so they need neither `vm.setEnv` nor a write to the deployments file.

## Tokenomics env keys

`forge script` only auto-loads `foundry/.env`, not the repo-root `.env` or `.env.<network>` files that dincli uses. Put overrides in `foundry/.env`, or export them first (from `foundry/`: `set -a; source ../.env.<network>; set +a`). Descriptions are in `.env.example`.

| Key | Default | Applied at |
|---|---|---|
| `DIN_PER_ETH` | `1_000_000e18` | step 15 |
| `MINT_CAP` | `0` (uncapped) | step 15 |
| `EMISSION_PER_GI` | `100e18` | step 13 |
| `EMISSION_DECAY_BPS` | `8000` | step 13 |
| `EMISSION_EPOCH_LENGTH` | `100` | step 13 |
| `EMISSION_MAX_EPOCHS` | `10` | step 13 |
| `MIN_STAKE` | `10e18` | step 15 |
| `S5_RECIDIVISM_WINDOW` | `5` | step 15 |
| `S5_RECIDIVISM_THRESHOLD` | `3` | step 15 |
| `S5_JAIL_DURATION` | `604800` (7 days) | step 15 |
| `S6_NO_PARTICIPATION_THRESHOLD` | `3` | step 15 |
| `S5_GLOBAL_WINDOW` | `604800` (7 days) | step 15 |
| `S5_GLOBAL_THRESHOLD` | `6` (with `S5_GLOBAL_WINDOW=0`, `0` turns the global level off) | step 15 |

The script ends the broadcast by logging a `--- Effective tokenomics ---` block with all 13 values.

## Sequence

| # | Step | Why here |
|---|------|----------|
| 1 | `DinTreasury` proxy — `initialize()` | No dependencies |
| 2 | `DinToken` proxy — `initialize()` | No dependencies; no minter yet |
| 3 | `DinFeeRouter` proxy — `initialize(dinToken, dinTreasury)` | Needs token + treasury |
| 4 | `DinCoordinator` proxy — `initialize(dinToken)` | Needs token |
| 5 | `dinToken.setCoordinator(dinCoordinator)` | One-shot minter wiring |
| 6 | `dinCoordinator.setFeeRouter(dinFeeRouter)`; `dinFeeRouter.addFeeSource(dinCoordinator)` | Faucet ETH can be swept to the router |
| 7 | `DinValidatorStake` proxy — `initialize(dinToken, dinCoordinator)` | Needs token + coordinator |
| 8 | `dinCoordinator.updateValidatorStakeContract(dinValidatorStake)` | Enables slasher management |
| 9 | `dinValidatorStake.setSlashTreasury(dinTreasury)` | Treasury half of every slash |
| 10 | `DINModelRegistry` proxy — `initialize(dinValidatorStake)` | Needs stake |
| 11 | `dinFeeRouter.addFeeSource(dinModelRegistry)` | Registry fees can be swept to the router |
| 12 | `dinModelRegistry.setFeeRouter(dinFeeRouter)` | |
| 13 | `DinEmission` proxy — `initialize(dinCoordinator, dinToken, dinModelRegistry, emissionPerGI, emissionDecayBps, emissionEpochLength, emissionMaxEpochs)` | Schedule from the env keys; defaults are 100 DIN/GI, 80% retained per epoch, 100 GIs per epoch, 10 epochs |
| 14 | `dinCoordinator.setEmissionContract(dinEmission)` | Authorises emission minting |
| 15 | Apply each post-deploy override only when it differs from its default: `updateDinPerEth`, `setMintCap`, `setMinStake`, `setS5RecidivismParams` (all three S5 values together, if any one differs), `setS6NoParticipationThreshold`, `setS5GlobalParams` (window and threshold together, if either differs). Then record the seven ProxyAdmins (`Upgrades.getAdminAddress`) | Invalid values revert the whole deploy (e.g. `InvalidMinStake`, `InvalidS5Params`, `InvalidS6Params`) |
| 16 | `run()` writes the JSON, after `vm.stopBroadcast()` | |

## Output

`foundry/deployments/<network>.json`, named by [`DeploymentsPath`](DeploymentsPath.md) from the chain ID (`localhost.json` on anvil, `sepolia_op_devnet.json` on Optimism Sepolia). Keys:

```
dinTreasury, dinToken, dinCoordinator, dinFeeRouter, dinValidatorStake, dinModelRegistry, dinEmission,
proxyAdminTreasury, proxyAdminToken, proxyAdminCoordinator, proxyAdminFeeRouter,
proxyAdminStake, proxyAdminRegistry, proxyAdminEmission
```

`localhost.json` is gitignored; the public-network file is committed as that network's record.

## Usage

Local:

```bash
./foundry/anvil.sh &
cd foundry && npm ci && forge clean
set -a; source ../.env.<network>; set +a   # optional: tokenomics overrides
forge script script/DeployPlatform.s.sol --rpc-url http://127.0.0.1:8545 --broadcast \
  --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 --unlocked
dincli --network local system import-deployments
```

Optimism Sepolia: sign with a keystore account instead of `--unlocked` (which only works with anvil's dev accounts). `SEPOLIA_OP_DEVNET_RPC_URL` comes from `.env.sepolia_op_devnet` (from the repo root: `set -a; source .env.sepolia_op_devnet; set +a`):

```bash
cd foundry && forge script script/DeployPlatform.s.sol \
  --rpc-url "$SEPOLIA_OP_DEVNET_RPC_URL" --broadcast \
  --account <keystore_name> --sender <din_representative_address>
dincli --network sepolia_op_devnet system import-deployments
```

This writes `foundry/deployments/sepolia_op_devnet.json` and `foundry/broadcast/DeployPlatform.s.sol/11155420/`; both are committed as the network's deploy record (the broadcast holds tx data, never keys).

## Tested by

[`foundry/test/DeployPlatform.t.sol`](../../../../../foundry/test/DeployPlatform.t.sol) reproduces this sequence in its `PlatformTest._deployPlatform()` fixture and checks every wiring edge (`ProxyWiringTest`), initializer protection (`ReInitializerProtectionTest`), and V2 upgrades (`*UpgradeTest`). [`foundry/test/DeployPlatformScript.t.sol`](../../../../../foundry/test/DeployPlatformScript.t.sol) (`DeployPlatformScriptTest`) runs the script's own `deploy()`: defaults, all 13 overrides, a single S5 override, a single S5 global override and the S5 global off switch (0, 0) land on chain, invalid overrides revert the deploy, every contract and ProxyAdmin is owned by the deployer, and `readTokenomics()` returns the defaults and then the values set with `vm.setEnv`. The `tests/dincli/` integration harness runs this script against a local chain (`PLATFORM_DEPLOY_TOOLCHAIN=foundry`).

## Notes

- The script does not deploy `DinFairLaunchDistributor` (see [DeployFairLaunchDistributor](DeployFairLaunchDistributor.md)) or any task contracts.
- `DinEmission` gets its schedule at initialization (step 13), so its four keys must be set before the deploy. The testnet values are still to be decided (issue #155).
