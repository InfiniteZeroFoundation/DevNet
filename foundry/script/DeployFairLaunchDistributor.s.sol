// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {stdJson} from "forge-std/StdJson.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";

import {DinFairLaunchDistributor} from "../src/DinFairLaunchDistributor.sol";

/// @notice Deploys DinFairLaunchDistributor behind a Transparent Proxy.
///
/// Prerequisites:
///   - Platform contracts already deployed (foundry/deployments/localhost.json must exist).
///   - DIN tokens available and the treasury admin has approved this contract.
///
/// Required environment variables:
///   TREASURY_ADMIN          — owner/treasury admin address (EOA for testnet; use a
///                             Gnosis Safe for production per contract NatSpec)
///   CLIFF_DURATION_SECONDS  — cliff in seconds (e.g. 7776000 = 90 days)
///   VESTING_DURATION_SECONDS— total vesting in seconds (e.g. 31536000 = 365 days)
///
/// Usage (from repo root):
///   ./foundry/anvil.sh &
///   forge clean
///   TREASURY_ADMIN=0xYourAddress \
///   CLIFF_DURATION_SECONDS=7776000 \
///   VESTING_DURATION_SECONDS=31536000 \
///   cd foundry && forge script script/DeployFairLaunchDistributor.s.sol \
///     --rpc-url http://127.0.0.1:8545 \
///     --broadcast \
///     --sender 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266 \
///     --unlocked
///
/// Note: this script does NOT wire the distributor into dincli import-deployments;
///       dincli manages only platform/task contracts. Record the proxy address manually.
contract DeployFairLaunchDistributor is Script {
    using stdJson for string;

    uint64 constant DEFAULT_CLIFF_SECONDS   = 90 days;  // placeholder
    uint64 constant DEFAULT_VESTING_SECONDS = 365 days; // placeholder

    function run() external {
        // Read dinToken address from the platform deployments file
        string memory deploymentsPath = string.concat(
            vm.projectRoot(),
            "/deployments/localhost.json"
        );
        string memory deploymentsJson = vm.readFile(deploymentsPath);
        address dinToken = deploymentsJson.readAddress(".dinToken");

        // Env-var overrides (fall back to placeholder defaults with a console warning)
        address treasuryAdmin = vm.envOr("TREASURY_ADMIN", msg.sender);
        if (treasuryAdmin == msg.sender) {
            console.log("[WARN] TREASURY_ADMIN not set - using broadcaster as owner (testnet only)");
        }

        uint64 cliffSeconds = uint64(vm.envOr("CLIFF_DURATION_SECONDS", uint256(DEFAULT_CLIFF_SECONDS)));
        uint64 vestingSeconds = uint64(vm.envOr("VESTING_DURATION_SECONDS", uint256(DEFAULT_VESTING_SECONDS)));

        if (cliffSeconds == DEFAULT_CLIFF_SECONDS) {
            console.log("[WARN] CLIFF_DURATION_SECONDS not set - using placeholder 90-day cliff");
        }
        if (vestingSeconds == DEFAULT_VESTING_SECONDS) {
            console.log("[WARN] VESTING_DURATION_SECONDS not set - using placeholder 365-day vesting");
        }

        console.log("dinToken:         ", dinToken);
        console.log("treasuryAdmin:    ", treasuryAdmin);
        console.log("cliffDuration:    ", cliffSeconds, "seconds");
        console.log("vestingDuration:  ", vestingSeconds, "seconds");

        vm.startBroadcast();

        address proxy = Upgrades.deployTransparentProxy(
            "DinFairLaunchDistributor.sol:DinFairLaunchDistributor",
            msg.sender, // ProxyAdmin owner (deployer); can be transferred separately
            abi.encodeCall(
                DinFairLaunchDistributor.initialize,
                (dinToken, treasuryAdmin, cliffSeconds, vestingSeconds)
            )
        );

        address proxyAdmin = Upgrades.getAdminAddress(proxy);

        vm.stopBroadcast();

        console.log("DinFairLaunchDistributor proxy: ", proxy);
        console.log("ProxyAdmin:                     ", proxyAdmin);

        _writeDeployments(proxy, proxyAdmin);
    }

    function _writeDeployments(address proxy, address proxyAdmin) internal {
        string memory json = "fld";
        vm.serializeAddress(json, "dinFairLaunchDistributor", proxy);
        string memory finalJson = vm.serializeAddress(json, "proxyAdminFairLaunch", proxyAdmin);

        string memory outDir = string.concat(vm.projectRoot(), "/deployments");
        vm.createDir(outDir, true);

        string memory outPath = string.concat(outDir, "/fair-launch-localhost.json");
        vm.writeJson(finalJson, outPath);
        console.log("Deployments written to:", outPath);
    }
}
