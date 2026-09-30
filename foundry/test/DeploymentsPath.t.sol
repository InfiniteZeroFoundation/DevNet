// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";

import {DeploymentsPath} from "../script/DeploymentsPath.sol";

/// @dev Exposes DeploymentsPath's internal helpers.
contract DeploymentsPathHarness is DeploymentsPath {
    function resolve(string memory override_, uint256 chainId) external pure returns (string memory) {
        return _resolveDeploymentsNetwork(override_, chainId);
    }

    function file(string memory prefix) external view returns (string memory) {
        return _deploymentsFile(prefix);
    }
}

/// @notice The chain-id → deployments-file mapping the Foundry scripts use.
///         Mapping and override precedence go through the pure resolver, so no
///         test calls vm.setEnv (the process environment is shared by forge's
///         parallel test functions). Run with:
///         forge test --match-contract DeploymentsPathTest -vv
contract DeploymentsPathTest is Test {
    DeploymentsPathHarness internal harness;

    function setUp() public {
        harness = new DeploymentsPathHarness();
    }

    function test_anvilChainIdMapsToLocalhost() public view {
        assertEq(harness.resolve("", 1337), "localhost");
    }

    function test_forgeDefaultChainIdMapsToLocalhost() public view {
        assertEq(harness.resolve("", 31337), "localhost");
    }

    function test_optimismSepoliaMapsToSepoliaOpDevnet() public view {
        assertEq(harness.resolve("", 11155420), "sepolia_op_devnet");
    }

    function test_unknownChainReverts() public {
        vm.expectRevert(bytes("DeploymentsPath: no deployments network for chain id 1; set DEPLOYMENTS_NETWORK"));
        harness.resolve("", 1);
    }

    function test_emptyOverrideTreatedAsUnset() public {
        // An exported-but-empty DEPLOYMENTS_NETWORK must not become the file name.
        assertEq(harness.resolve("", 11155420), "sepolia_op_devnet");
        vm.expectRevert(bytes("DeploymentsPath: no deployments network for chain id 10; set DEPLOYMENTS_NETWORK"));
        harness.resolve("", 10);
    }

    function test_overrideWinsOnKnownChain() public view {
        assertEq(harness.resolve("custom", 11155420), "custom");
        assertEq(harness.resolve("custom", 1337), "custom");
    }

    function test_overrideCoversUnknownChain() public view {
        assertEq(harness.resolve("custom", 1), "custom");
    }

    function test_deploymentsFileUsesPrefixAndChainNetwork() public {
        vm.chainId(11155420);
        // Honour a DEPLOYMENTS_NETWORK the caller's shell may export, so the test
        // stays deterministic without touching the environment itself.
        string memory override_ = vm.envOr("DEPLOYMENTS_NETWORK", string(""));
        string memory network = bytes(override_).length != 0 ? override_ : "sepolia_op_devnet";

        assertEq(
            harness.file("fair-launch-"),
            string.concat(vm.projectRoot(), "/deployments/fair-launch-", network, ".json")
        );
        assertEq(harness.file(""), string.concat(vm.projectRoot(), "/deployments/", network, ".json"));
    }
}
