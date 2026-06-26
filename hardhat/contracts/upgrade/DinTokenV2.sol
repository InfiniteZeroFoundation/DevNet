// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import "../DinToken.sol";

/// @custom:oz-upgrades-from DinToken
// missing-initializer is intentional: V2 adds no new state, so it reuses
// V1's initializer. A reinitializer would only be needed if V2 introduced
// new storage variables that require one-time setup.
/// @custom:oz-upgrades-unsafe-allow missing-initializer
contract DinTokenV2 is DinToken {
    function version() external pure returns (uint256) {
        return 2;
    }
}
