# Hardhat Tooling — Technical Documentation

Per-file documentation for the Hardhat workspace's supporting code: test suites, test helpers, deployment/upgrade scripts, deploy utilities, and test-only Solidity (mocks and V2 upgrade fixtures). The platform contracts themselves are documented one level up in [`Documentation/technical/contracts/`](../).

| Doc | Source file | What it is |
|-----|-------------|-----------|
| **Tests** | | |
| [tests/DinValidatorStake.test.md](tests/DinValidatorStake.test.md) | `hardhat/test/DinValidatorStake.test.ts` | Functional suite: staking, unbonding, slashing, blacklisting |
| [tests/DinToken.upgrade.test.md](tests/DinToken.upgrade.test.md) | `hardhat/test/DinToken.upgrade.test.ts` | Upgrade safety: balances, coordinator wiring, access control |
| [tests/DinCoordinator.upgrade.test.md](tests/DinCoordinator.upgrade.test.md) | `hardhat/test/DinCoordinator.upgrade.test.ts` | Upgrade safety: rate, token wiring, slasher management |
| [tests/DinValidatorStake.upgrade.test.md](tests/DinValidatorStake.upgrade.test.md) | `hardhat/test/DinValidatorStake.upgrade.test.ts` | Upgrade safety: stake custody, privileged gates |
| [tests/DINModelRegistry.upgrade.test.md](tests/DINModelRegistry.upgrade.test.md) | `hardhat/test/DINModelRegistry.upgrade.test.ts` | Upgrade safety: fees, models, pending requests |
| [tests/helpers/platform.md](tests/helpers/platform.md) | `hardhat/test/helpers/platform.ts` | Shared full-platform proxy fixture (`deployPlatform`, `mintDinViaDeposit`) |
| **Scripts** | | |
| [scripts/deploy-platform.md](scripts/deploy-platform.md) | `hardhat/scripts/deploy-platform.ts` | Canonical platform deployment + wiring order |
| [scripts/upgrade-platform.md](scripts/upgrade-platform.md) | `hardhat/scripts/upgrade-platform.ts` | Per-contract proxy upgrade workflow (`CONTRACT=<Name>`) |
| **Deploy utilities** | | |
| [deploy/helpers.md](deploy/helpers.md) | `hardhat/deploy/helpers.ts` | Proxy deploy/upgrade wrappers, address persistence, ProxyAdmin lookup |
| [deploy/constants.md](deploy/constants.md) | `hardhat/deploy/constants.ts` | `PROXY_KIND`, `PLATFORM_CONTRACTS` allowlist |
| [deploy/types.md](deploy/types.md) | `hardhat/deploy/types.ts` | `PlatformAddresses` — shape of `deployments/<network>.json` |
| **Test-only Solidity** | | |
| [mocks/MockSlasher.md](mocks/MockSlasher.md) | `hardhat/contracts/mocks/MockSlasher.sol` | Minimal ownable slasher stand-in for tests |
| [upgrades/DinTokenV2.md](upgrades/DinTokenV2.md) | `hardhat/contracts/upgrade/DinTokenV2.sol` | V2 fixture (`version() == 2`) for token upgrade tests |
| [upgrades/DinCoordinatorV2.md](upgrades/DinCoordinatorV2.md) | `hardhat/contracts/upgrade/DinCoordinatorV2.sol` | V2 fixture for coordinator upgrade tests |
| [upgrades/DinValidatorStakeV2.md](upgrades/DinValidatorStakeV2.md) | `hardhat/contracts/upgrade/DinValidatorStakeV2.sol` | V2 fixture for stake upgrade tests |
| [upgrades/DINModelRegistryV2.md](upgrades/DINModelRegistryV2.md) | `hardhat/contracts/upgrade/DINModelRegistryV2.sol` | V2 fixture for registry upgrade tests |
| **Interfaces** | | |
| [interfaces/IUniswapV2Router02.md](interfaces/IUniswapV2Router02.md) | `hardhat/contracts/interfaces/IUniswapV2Router02.sol` | Partial Uniswap V2 router interface — currently unused |

## Quick commands

```bash
cd hardhat
npx hardhat test                                              # full suite
npx hardhat run scripts/deploy-platform.ts --network <net>    # deploy platform
CONTRACT=<Name> npx hardhat run scripts/upgrade-platform.ts --network <net>   # upgrade one proxy
```
