// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Upgrades, Options} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

/// @notice Validates that each of the four upgradeable platform contracts
///         satisfies the OpenZeppelin Transparent Proxy storage-layout rules.
///         Run with: forge test --match-contract UpgradeValidationTest -vv
contract UpgradeValidationTest is Test {
    /// @dev Validates DinToken is upgrade-safe (Initializable, ERC20Upgradeable,
    ///      OwnableUpgradeable, __gap reservation, _disableInitializers constructor).
    function test_validateImplementation_DinToken() public {
        Options memory opts;
        Upgrades.validateImplementation("DinToken.sol:DinToken", opts);
    }

    /// @dev Validates DinCoordinator is upgrade-safe (Initializable, OwnableUpgradeable,
    ///      ReentrancyGuardTransient — transient storage, __gap reservation).
    function test_validateImplementation_DinCoordinator() public {
        Options memory opts;
        Upgrades.validateImplementation("DinCoordinator.sol:DinCoordinator", opts);
    }

    /// @dev Validates DinValidatorStake is upgrade-safe (Initializable, OwnableUpgradeable,
    ///      ReentrancyGuardTransient — transient storage, __gap reservation).
    function test_validateImplementation_DinValidatorStake() public {
        Options memory opts;
        Upgrades.validateImplementation(
            "DinValidatorStake.sol:DinValidatorStake",
            opts
        );
    }

    /// @dev Validates DINModelRegistry is upgrade-safe (Initializable, OwnableUpgradeable,
    ///      __gap reservation).
    function test_validateImplementation_DINModelRegistry() public {
        Options memory opts;
        Upgrades.validateImplementation(
            "DINModelRegistry.sol:DINModelRegistry",
            opts
        );
    }
}
