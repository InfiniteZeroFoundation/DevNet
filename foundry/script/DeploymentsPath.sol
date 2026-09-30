// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";

/// @notice Resolves foundry/deployments/<network>.json for the chain a script
///         runs against, so each network keeps its own addresses file.
///         <network> is dincli's deployments key — the name
///         `dincli system import-deployments` looks up (dincli "local" maps to
///         "localhost") — so imports need no --file flag.
///
///         Chain id → network:
///           1337, 31337  → localhost          (foundry/anvil.sh uses 1337;
///                                              31337 is anvil's / forge's default)
///           11155420     → sepolia_op_devnet  (Optimism Sepolia)
///         A non-empty DEPLOYMENTS_NETWORK env var overrides the mapping; any
///         other chain reverts unless it is set.
abstract contract DeploymentsPath is Script {
    function _deploymentsNetwork() internal view returns (string memory) {
        return _resolveDeploymentsNetwork(vm.envOr("DEPLOYMENTS_NETWORK", string("")), block.chainid);
    }

    /// @dev Pure so the mapping can be tested without vm.setEnv, which changes
    ///      the process environment shared by forge's parallel test functions.
    /// @param override_ DEPLOYMENTS_NETWORK value; empty means unset.
    function _resolveDeploymentsNetwork(string memory override_, uint256 chainId)
        internal
        pure
        returns (string memory)
    {
        if (bytes(override_).length != 0) return override_;

        if (chainId == 1337 || chainId == 31337) return "localhost";
        if (chainId == 11155420) return "sepolia_op_devnet";

        // Deliberately no guess: a wrong file name is how another chain's
        // addresses would end up in use.
        revert(
            string.concat(
                "DeploymentsPath: no deployments network for chain id ",
                vm.toString(chainId),
                "; set DEPLOYMENTS_NETWORK"
            )
        );
    }

    /// @param prefix filename prefix, e.g. "" for platform addresses or
    ///        "fair-launch-" for the fair-launch distributor.
    function _deploymentsFile(string memory prefix) internal view returns (string memory) {
        return string.concat(
            vm.projectRoot(),
            "/deployments/",
            prefix,
            _deploymentsNetwork(),
            ".json"
        );
    }
}
