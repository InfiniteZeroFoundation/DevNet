// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "../DinToken.sol";

/// @custom:oz-upgrades-from DinToken
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinTokenV2 is DinToken {
    function version() external pure returns (uint256) {
        return 2;
    }
}
