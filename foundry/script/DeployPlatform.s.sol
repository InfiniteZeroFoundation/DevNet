// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";

/// @notice Deploys the four DIN platform contracts behind Transparent Proxies
///         on a local anvil chain, wires them together, and writes
///         foundry/deployments/localhost.json in the same schema as
///         hardhat/deployments/localhost.json so dincli import-deployments
///         accepts it without modification.
///
/// Usage (from repo root):
///   ./foundry/anvil.sh &
///   forge clean
///   cd foundry && forge script script/DeployPlatform.s.sol \
///     --rpc-url http://127.0.0.1:8545 \
///     --broadcast \
///     --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
///     --unlocked
///
/// Then import into dincli:
///   dincli system import-deployments --foundry
contract DeployPlatform is Script {
    using stdJson for string;

    function run() external {
        vm.startBroadcast();

        // 1. DinToken — no init args
        address dinTokenProxy = Upgrades.deployTransparentProxy(
            "DinToken.sol:DinToken",
            msg.sender,
            abi.encodeCall(DinToken.initialize, ())
        );
        console.log("DinToken proxy:         ", dinTokenProxy);

        // 2. DinCoordinator — receives the DinToken proxy address
        address dinCoordinatorProxy = Upgrades.deployTransparentProxy(
            "DinCoordinator.sol:DinCoordinator",
            msg.sender,
            abi.encodeCall(DinCoordinator.initialize, (dinTokenProxy))
        );
        console.log("DinCoordinator proxy:   ", dinCoordinatorProxy);

        // 3. Wire DinToken → DinCoordinator (one-shot setter)
        DinToken(dinTokenProxy).setCoordinator(dinCoordinatorProxy);
        console.log("DinToken coordinator wired");

        // 4. DinValidatorStake — receives both token and coordinator proxies
        address dinValidatorStakeProxy = Upgrades.deployTransparentProxy(
            "DinValidatorStake.sol:DinValidatorStake",
            msg.sender,
            abi.encodeCall(
                DinValidatorStake.initialize,
                (dinTokenProxy, dinCoordinatorProxy)
            )
        );
        console.log("DinValidatorStake proxy:", dinValidatorStakeProxy);

        // 5. Wire DinCoordinator → DinValidatorStake
        DinCoordinator(payable(dinCoordinatorProxy))
            .updateValidatorStakeContract(dinValidatorStakeProxy);
        console.log("DinCoordinator stake contract wired");

        // 6. DINModelRegistry — receives the stake proxy
        address dinModelRegistryProxy = Upgrades.deployTransparentProxy(
            "DINModelRegistry.sol:DINModelRegistry",
            msg.sender,
            abi.encodeCall(
                DINModelRegistry.initialize,
                (dinValidatorStakeProxy)
            )
        );
        console.log("DINModelRegistry proxy: ", dinModelRegistryProxy);

        // 7. ProxyAdmin — OZ v5 deploys one ProxyAdmin per proxy; record all four
        address proxyAdminToken       = Upgrades.getAdminAddress(dinTokenProxy);
        address proxyAdminCoordinator = Upgrades.getAdminAddress(dinCoordinatorProxy);
        address proxyAdminStake       = Upgrades.getAdminAddress(dinValidatorStakeProxy);
        address proxyAdminRegistry    = Upgrades.getAdminAddress(dinModelRegistryProxy);
        console.log("ProxyAdmin (token):     ", proxyAdminToken);
        console.log("ProxyAdmin (coord):     ", proxyAdminCoordinator);
        console.log("ProxyAdmin (stake):     ", proxyAdminStake);
        console.log("ProxyAdmin (registry):  ", proxyAdminRegistry);

        vm.stopBroadcast();

        // 8. Write deployments JSON — same schema as hardhat/deployments/localhost.json
        _writeDeployments(
            dinTokenProxy,
            dinCoordinatorProxy,
            dinValidatorStakeProxy,
            dinModelRegistryProxy,
            proxyAdminToken,
            proxyAdminCoordinator,
            proxyAdminStake,
            proxyAdminRegistry
        );
    }

    function _writeDeployments(
        address dinToken,
        address dinCoordinator,
        address dinValidatorStake,
        address dinModelRegistry,
        address proxyAdminToken,
        address proxyAdminCoordinator,
        address proxyAdminStake,
        address proxyAdminRegistry
    ) internal {
        string memory json = "deployments";
        vm.serializeAddress(json, "dinToken", dinToken);
        vm.serializeAddress(json, "dinCoordinator", dinCoordinator);
        vm.serializeAddress(json, "dinValidatorStake", dinValidatorStake);
        vm.serializeAddress(json, "dinModelRegistry", dinModelRegistry);
        vm.serializeAddress(json, "proxyAdminToken", proxyAdminToken);
        vm.serializeAddress(json, "proxyAdminCoordinator", proxyAdminCoordinator);
        vm.serializeAddress(json, "proxyAdminStake", proxyAdminStake);
        string memory finalJson = vm.serializeAddress(
            json,
            "proxyAdminRegistry",
            proxyAdminRegistry
        );

        string memory outDir = string.concat(vm.projectRoot(), "/deployments");
        vm.createDir(outDir, true);

        string memory outPath = string.concat(outDir, "/localhost.json");
        vm.writeJson(finalJson, outPath);
        console.log("Deployments written to:", outPath);
    }
}
