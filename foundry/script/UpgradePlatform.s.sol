// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DeploymentsPath} from "./DeploymentsPath.sol";

/// @notice Upgrades a single platform proxy to its V2 implementation.
///         Reads the proxy address from foundry/deployments/<network>.json
///         (written by DeployPlatform.s.sol; see DeploymentsPath) and updates the implementation
///         slot via the TransparentUpgradeableProxy admin.
///
/// Usage (from repo root; CONTRACT must be one of: DinToken, DinCoordinator,
///        DinValidatorStake, DINModelRegistry):
///
///   cd foundry && CONTRACT=DinToken forge script script/UpgradePlatform.s.sol \
///     --rpc-url http://127.0.0.1:8545 \
///     --broadcast \
///     --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
///     --unlocked
///
/// On Optimism Sepolia, sign with a keystore account instead of --unlocked
/// (--unlocked only works against anvil's dev accounts). SEPOLIA_OP_DEVNET_RPC_URL comes
/// from .env.sepolia_op_devnet (from the repo root: set -a; source .env.sepolia_op_devnet; set +a):
///   cd foundry && CONTRACT=DinToken forge script script/UpgradePlatform.s.sol \
///     --rpc-url "$SEPOLIA_OP_DEVNET_RPC_URL" \
///     --broadcast \
///     --account <keystore_name> \
///     --sender <din_representative_address>
contract UpgradePlatform is DeploymentsPath {
    using stdJson for string;

    // Maps contract names to their deployments JSON key
    string constant KEY_DIN_TOKEN = "dinToken";
    string constant KEY_DIN_COORDINATOR = "dinCoordinator";
    string constant KEY_DIN_VALIDATOR_STAKE = "dinValidatorStake";
    string constant KEY_DIN_MODEL_REGISTRY = "dinModelRegistry";

    function run() external {
        string memory contractName = vm.envString("CONTRACT");
        string memory implName = string.concat(contractName, "V2");

        string memory deploymentsPath = _deploymentsFile("");
        string memory raw = vm.readFile(deploymentsPath);

        string memory proxyKey = _proxyKey(contractName);
        address proxyAddress = stdJson.readAddress(
            raw,
            string.concat(".", proxyKey)
        );

        console.log("Contract:       ", contractName);
        console.log("Proxy:          ", proxyAddress);
        console.log("New impl:       ", implName);

        vm.startBroadcast();
        Upgrades.upgradeProxy(
            proxyAddress,
            string.concat(implName, ".sol:", implName),
            ""
        );
        vm.stopBroadcast();

        address newImpl = Upgrades.getImplementationAddress(proxyAddress);
        console.log("Implementation: ", newImpl);
    }

    function _proxyKey(
        string memory contractName
    ) internal pure returns (string memory) {
        if (keccak256(bytes(contractName)) == keccak256(bytes("DinToken"))) {
            return KEY_DIN_TOKEN;
        } else if (
            keccak256(bytes(contractName)) == keccak256(bytes("DinCoordinator"))
        ) {
            return KEY_DIN_COORDINATOR;
        } else if (
            keccak256(bytes(contractName)) ==
            keccak256(bytes("DinValidatorStake"))
        ) {
            return KEY_DIN_VALIDATOR_STAKE;
        } else if (
            keccak256(bytes(contractName)) ==
            keccak256(bytes("DINModelRegistry"))
        ) {
            return KEY_DIN_MODEL_REGISTRY;
        } else {
            revert(
                string.concat(
                    "Unknown CONTRACT '",
                    contractName,
                    "'. Expected one of: DinToken, DinCoordinator, DinValidatorStake, DINModelRegistry"
                )
            );
        }
    }
}
