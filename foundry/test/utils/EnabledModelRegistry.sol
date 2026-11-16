// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

/// @dev Enabled/approved registry fixture for isolated task tests. Kill-switch
///      integration tests in RewardEngine use the actual registry proxy instead.
contract EnabledModelRegistry {
    function getModelIdByTaskAuditor(address) external pure returns (bool, uint256) {
        return (true, 0);
    }

    function modelDisabled(uint256) external pure returns (bool) {
        return false;
    }
}
