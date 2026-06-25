// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "../DinValidatorStake.sol";

/// @custom:oz-upgrades-from DinValidatorStake
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinValidatorStakeV2 is DinValidatorStake {
    function version() external pure returns (uint256) {
        return 2;
    }
}
