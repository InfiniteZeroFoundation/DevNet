// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "../DINModelRegistry.sol";

/// @custom:oz-upgrades-from DINModelRegistry
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DINModelRegistryV2 is DINModelRegistry {
    function version() external pure returns (uint256) {
        return 2;
    }
}
