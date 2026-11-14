// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";

import {DeployPlatform} from "../script/DeployPlatform.s.sol";
import {UpgradePlatform} from "../script/UpgradePlatform.s.sol";
import {DinTokenV2} from "../src/upgrade/DinTokenV2.sol";

/// @dev Exposes _writeUpgradeMetadata for white-box testing.
contract UpgradePlatformHarness is UpgradePlatform {
    function writeUpgradeMetadata(
        address newImpl,
        string memory proxyKey,
        string memory deploymentsPath,
        string memory gitCommit
    ) external {
        _writeUpgradeMetadata(newImpl, proxyKey, deploymentsPath, gitCommit);
    }
}

/// @dev Exposes _writeDeploymentsTo to create the initial deployments JSON needed
///      by the upgrade metadata test, without coupling to DeployPlatformScript.t.sol.
contract DeployHarness is DeployPlatform {
    function writeDeploymentsTo(Deployment memory d, address deployer_, string memory outPath) external {
        _writeDeploymentsTo(d, deployer_, outPath);
    }
}

/// @notice Script-level coverage for UpgradePlatform.s.sol's metadata-writing
///         block (_writeUpgradeMetadata). Verifies that after an upgrade the
///         deployments JSON records the correct implementation address,
///         extcodehash, and (when GIT_COMMIT_HASH is supplied) commit hash.
///
///         The test passes its own file, foundry/deployments/test-upgrade-metadata.json,
///         explicitly and sets no environment variables: vm.setEnv changes the
///         environment shared by forge's parallel test contracts (PR No. 254).
///         Run with: forge test --match-contract UpgradePlatformScriptTest -vv
contract UpgradePlatformScriptTest is Test {
    UpgradePlatformHarness internal harness;
    DeployHarness          internal deployHarness;
    DeployPlatform         internal deployScript;
    address internal deployer = makeAddr("deployer");

    function setUp() public {
        harness      = new UpgradePlatformHarness();
        deployHarness = new DeployHarness();
        deployScript = new DeployPlatform();
    }

    /// @dev Verifies the metadata-writing block of UpgradePlatform.s.sol:
    ///      (a) recorded implementation address matches the upgraded impl,
    ///      (b) recorded codehash matches extcodehash(newImpl),
    ///      (c) .deployedAtCommit is written when a non-empty commit is passed.
    function test_writeUpgradeMetadata_writesImplCodehashAndCommit() public {
        string memory path = string.concat(
            vm.projectRoot(), "/deployments/test-upgrade-metadata.json"
        );

        // Write an initial deployments JSON so the three-arg vm.writeJson calls
        // inside _writeUpgradeMetadata have an existing file to update.
        DeployPlatform.Tokenomics memory t = deployScript.defaultTokenomics();
        DeployPlatform.Deployment  memory d = deployScript.deploy(t, deployer);
        deployHarness.writeDeploymentsTo(d, deployer, path);

        // Deploy DinTokenV2 to get a real implementation address and codehash.
        // We only need the bytecode to be present; the contract need not be
        // initialized for extcodehash to return a non-zero value.
        address newImpl = address(new DinTokenV2());
        bytes32 expectedCodehash;
        assembly { expectedCodehash := extcodehash(newImpl) }

        // --- (a) & (b): impl address and codehash ---
        harness.writeUpgradeMetadata(newImpl, "dinToken", path, "");

        string memory content     = vm.readFile(path);
        address recordedImpl      = vm.parseJsonAddress(content, ".dinTokenImpl");
        bytes32 recordedCodehash  = vm.parseJsonBytes32(content, ".dinTokenImplCodehash");

        assertEq(recordedImpl, newImpl,             "dinTokenImpl must match upgraded implementation");
        assertNotEq(recordedCodehash, bytes32(0),   "dinTokenImplCodehash must not be zero");
        assertEq(recordedCodehash, expectedCodehash,"dinTokenImplCodehash must match extcodehash(newImpl)");

        // --- (c): commit hash written when non-empty ---
        string memory commit = "abc1234def5678900000000000000000000000000";
        harness.writeUpgradeMetadata(newImpl, "dinToken", path, commit);

        content = vm.readFile(path);
        string memory recordedCommit = vm.parseJsonString(content, ".deployedAtCommit");
        assertEq(recordedCommit, commit, ".deployedAtCommit must match the commit passed in");
    }
}
