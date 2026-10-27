# V2 Upgrade Fixtures

> **Files:** [`foundry/src/upgrade/DinTokenV2.sol`](../../../../../foundry/src/upgrade/DinTokenV2.sol), [`DinCoordinatorV2.sol`](../../../../../foundry/src/upgrade/DinCoordinatorV2.sol), [`DinValidatorStakeV2.sol`](../../../../../foundry/src/upgrade/DinValidatorStakeV2.sol), [`DINModelRegistryV2.sol`](../../../../../foundry/src/upgrade/DINModelRegistryV2.sol)

Four test fixtures, identical in shape, used to exercise the proxy upgrade path of the four original platform contracts:

```solidity
/// @custom:oz-upgrades-from DinToken
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinTokenV2 is DinToken {
    function version() external pure returns (uint256) {
        return 2;
    }
}
```

- **Inherit the V1 contract unchanged** and add one pure function, `version() == 2`. They add no state, so the storage layout is identical to V1.
- **`@custom:oz-upgrades-from <V1>`** tells OpenZeppelin's validator which implementation to compare the layout against.
- **`@custom:oz-upgrades-unsafe-allow missing-initializer`** is intentional: with no new state there is nothing to initialize, so V1's initializer is reused. A real V2 that adds state would need a `reinitializer(2)`.

## Used by

- [`foundry/test/DeployPlatform.t.sol`](../../../../../foundry/test/DeployPlatform.t.sol) — `DinTokenUpgradeTest`, `DinCoordinatorUpgradeTest`, `DinValidatorStakeUpgradeTest`, `DINModelRegistryUpgradeTest` upgrade a freshly deployed platform to these fixtures and check that state and access control survive.
- [UpgradePlatform.s.sol](../script/UpgradePlatform.md) — always upgrades to `<Name>V2`.

There are no fixtures for `DinTreasury`, `DinFeeRouter` or `DinEmission`.
