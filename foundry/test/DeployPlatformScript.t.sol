// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {Upgrades} from "@openzeppelin/foundry-upgrades/Upgrades.sol";
import {ProxyAdmin} from "@openzeppelin/contracts/proxy/transparent/ProxyAdmin.sol";
import {OwnableUpgradeable} from "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";

import {DeployPlatform} from "../script/DeployPlatform.s.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DinEmission} from "../src/DinEmission.sol";

/// @notice Script-level coverage for DeployPlatform.s.sol's tokenomics
///         overrides (issue No. 199, follow-up to No. 155 / PR No. 184): runs
///         the script's own deploy() with explicit values and a fixed deployer,
///         then reads every parameter and every owner back from the deployed
///         proxies.
///
///         deploy() takes the values as an argument instead of reading the
///         environment, so no deploy test depends on env. The env-read path
///         (readTokenomics) is covered by exactly one test, which is the only
///         place in foundry/test that sets these keys; see its comment. No test
///         calls run(), which would overwrite foundry/deployments/*.json. Run with:
///         forge test --match-contract DeployPlatformScriptTest -vv
contract DeployPlatformScriptTest is Test {
    DeployPlatform internal script;
    address internal deployer = makeAddr("deployer");

    function setUp() public {
        script = new DeployPlatform();
    }

    function _overrides() internal pure returns (DeployPlatform.Tokenomics memory) {
        return DeployPlatform.Tokenomics({
            dinPerEth:           2_000_000 * 1e18,
            mintCap:             500_000_000 * 1e18,
            emissionPerGI:       50e18,
            emissionDecayBps:    9000,
            emissionEpochLength: 200,
            emissionMaxEpochs:   5,
            minStake:            50e18,
            s5Window:            10,
            s5Threshold:         4,
            s5JailDuration:      14 days,
            s6Threshold:         5,
            s5GlobalWindow:      3 days,
            s5GlobalThreshold:   8
        });
    }

    function _assertOwnedByDeployer(address proxy, string memory name) internal view {
        assertEq(OwnableUpgradeable(proxy).owner(), deployer, string.concat(name, " owner"));
        assertEq(
            ProxyAdmin(Upgrades.getAdminAddress(proxy)).owner(),
            deployer,
            string.concat(name, " ProxyAdmin owner")
        );
    }

    function _assertOnChain(DeployPlatform.Deployment memory d, DeployPlatform.Tokenomics memory t) internal view {
        DinCoordinator coord = DinCoordinator(payable(d.dinCoordinator));
        DinValidatorStake stake = DinValidatorStake(d.dinValidatorStake);
        DinEmission emission = DinEmission(d.dinEmission);

        assertEq(coord.dinPerEth(), t.dinPerEth, "dinPerEth");
        assertEq(coord.mintCap(), t.mintCap, "mintCap");
        assertEq(coord.emissionContract(), d.dinEmission, "emission contract wired");
        assertEq(emission.initialEmissionPerGI(), t.emissionPerGI, "initialEmissionPerGI");
        assertEq(emission.decayBps(), t.emissionDecayBps, "decayBps");
        assertEq(emission.epochLength(), t.emissionEpochLength, "epochLength");
        assertEq(emission.maxEpochs(), t.emissionMaxEpochs, "maxEpochs");
        assertEq(stake.MIN_STAKE(), t.minStake, "MIN_STAKE");
        assertEq(stake.s5RecidivismWindow(), t.s5Window, "s5RecidivismWindow");
        assertEq(stake.s5RecidivismThreshold(), t.s5Threshold, "s5RecidivismThreshold");
        assertEq(stake.s5JailDuration(), t.s5JailDuration, "s5JailDuration");
        assertEq(stake.s6NoParticipationThreshold(), t.s6Threshold, "s6NoParticipationThreshold");
        assertEq(stake.s5GlobalWindow(), t.s5GlobalWindow, "s5GlobalWindow");
        assertEq(stake.s5GlobalThreshold(), t.s5GlobalThreshold, "s5GlobalThreshold");

        _assertOwnedByDeployer(d.dinTreasury, "DinTreasury");
        _assertOwnedByDeployer(d.dinToken, "DinToken");
        _assertOwnedByDeployer(d.dinCoordinator, "DinCoordinator");
        _assertOwnedByDeployer(d.dinFeeRouter, "DinFeeRouter");
        _assertOwnedByDeployer(d.dinValidatorStake, "DinValidatorStake");
        _assertOwnedByDeployer(d.dinModelRegistry, "DINModelRegistry");
        _assertOwnedByDeployer(d.dinEmission, "DinEmission");
    }

    function test_defaults_landOnChain() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        DeployPlatform.Deployment memory d = script.deploy(t, deployer);
        _assertOnChain(d, t);
    }

    function test_allOverrides_landOnChain() public {
        DeployPlatform.Tokenomics memory t = _overrides();
        DeployPlatform.Deployment memory d = script.deploy(t, deployer);
        _assertOnChain(d, t);
    }

    /// @dev The S5 setter takes all three values together; overriding only one
    ///      must still apply it and keep the other two at their defaults.
    function test_singleS5Override_appliesWithOtherDefaults() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s5JailDuration = 3 days;
        DeployPlatform.Deployment memory d = script.deploy(t, deployer);
        _assertOnChain(d, t);
    }

    /// @dev Invalid overrides must revert the deploy, not ship a broken value.
    function test_zeroMinStake_revertsDeploy() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.minStake = 0;
        vm.expectRevert(DinValidatorStake.InvalidMinStake.selector);
        script.deploy(t, deployer);
    }

    function test_s5ThresholdAboveWindow_revertsDeploy() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s5Threshold = t.s5Window + 1;
        vm.expectRevert(DinValidatorStake.InvalidS5Params.selector);
        script.deploy(t, deployer);
    }

    /// @dev The S5 global setter takes window and threshold together;
    ///      overriding only one must apply both, with the other at its default.
    function test_singleS5GlobalOverride_appliesWithOtherDefault() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s5GlobalThreshold = 9;
        DeployPlatform.Deployment memory d = script.deploy(t, deployer);
        _assertOnChain(d, t);
    }

    /// @dev (0, 0) turns the global S5 level off at deploy time.
    function test_s5GlobalOff_landsOnChain() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s5GlobalWindow = 0;
        t.s5GlobalThreshold = 0;
        DeployPlatform.Deployment memory d = script.deploy(t, deployer);
        _assertOnChain(d, t);
    }

    function test_s5GlobalHalfZero_revertsDeploy() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s5GlobalWindow = 0;
        vm.expectRevert(DinValidatorStake.InvalidS5Params.selector);
        script.deploy(t, deployer);
    }

    function test_zeroS6Threshold_revertsDeploy() public {
        DeployPlatform.Tokenomics memory t = script.defaultTokenomics();
        t.s6Threshold = 0;
        vm.expectRevert(DinValidatorStake.InvalidS6Params.selector);
        script.deploy(t, deployer);
    }

    /// @dev readTokenomics() returns the defaults with no key set, and exactly
    ///      the env values once every key is set.
    ///
    ///      Both halves live in this ONE function on purpose. The process
    ///      environment is shared by forge's parallel test functions, and
    ///      vm.setEnv cannot unset a key (envOr also reverts on an empty
    ///      string), so the keys stay set for the rest of the run. Any future
    ///      test that reads these keys MUST go into this function, or it will
    ///      race with the setEnv below.
    ///
    ///      Skipped when the caller's shell or foundry/.env already sets a key,
    ///      so the defaults half stays deterministic.
    function test_readTokenomics_defaultsThenEnvOverrides() public {
        string[13] memory keys = [
            "DIN_PER_ETH", "MINT_CAP", "EMISSION_PER_GI", "EMISSION_DECAY_BPS",
            "EMISSION_EPOCH_LENGTH", "EMISSION_MAX_EPOCHS", "MIN_STAKE",
            "S5_RECIDIVISM_WINDOW", "S5_RECIDIVISM_THRESHOLD", "S5_JAIL_DURATION",
            "S6_NO_PARTICIPATION_THRESHOLD", "S5_GLOBAL_WINDOW", "S5_GLOBAL_THRESHOLD"
        ];
        for (uint256 i = 0; i < keys.length; i++) {
            if (vm.envExists(keys[i])) vm.skip(true, "tokenomics env key set");
        }
        assertEq(abi.encode(script.readTokenomics()), abi.encode(script.defaultTokenomics()), "defaults");

        DeployPlatform.Tokenomics memory t = _overrides();
        uint256[13] memory values = [
            t.dinPerEth, t.mintCap, t.emissionPerGI, t.emissionDecayBps,
            t.emissionEpochLength, t.emissionMaxEpochs, t.minStake,
            t.s5Window, t.s5Threshold, t.s5JailDuration,
            t.s6Threshold, t.s5GlobalWindow, t.s5GlobalThreshold
        ];
        for (uint256 i = 0; i < keys.length; i++) {
            vm.setEnv(keys[i], vm.toString(values[i]));
        }
        assertEq(abi.encode(script.readTokenomics()), abi.encode(t), "env overrides");
    }
}
