// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import "../DinCoordinator.sol";

/// @custom:oz-upgrades-from DinCoordinator
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinCoordinatorV2 is DinCoordinator {
    function version() external pure returns (uint256) {
        return 2;
    }
}
