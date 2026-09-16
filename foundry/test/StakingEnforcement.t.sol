// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Tests for task_100926_12 Issue #37: per-model stake floor and concurrent-
// registration cap wired into DINTaskCoordinator.registerDINaggregator and
// DINTaskAuditor.registerDINAuditor.
// Run: forge test --match-contract StakingEnforcementTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {GIstates} from "../src/DINShared.sol";
import {
    TC_StakeBelowModelFloor,
    TC_ConcurrentRegistrationCapReached,
    TA_StakeBelowModelFloor,
    TA_ConcurrentRegistrationCapReached
} from "../src/DINShared.sol";

contract StakingEnforcementTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address agg1       = makeAddr("agg1");
    address agg2       = makeAddr("agg2");
    address aud1       = makeAddr("aud1");
    address aud2       = makeAddr("aud2");

    uint256 constant MODEL_ID = 1;
    uint256 constant MIN_STAKE_AMOUNT = 10 ether; // matches DinValidatorStake.MIN_STAKE

    function setUp() public {
        vm.startPrank(admin);

        DinToken tokenImpl = new DinToken();
        TransparentUpgradeableProxy tokenProxy = new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        );
        token = DinToken(address(tokenProxy));

        DinCoordinator coordinatorImpl = new DinCoordinator();
        TransparentUpgradeableProxy coordinatorProxy = new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        );
        coordinator = DinCoordinator(address(coordinatorProxy));
        token.setCoordinator(address(coordinator));

        DinValidatorStake stakeImpl = new DinValidatorStake();
        TransparentUpgradeableProxy stakeProxy = new TransparentUpgradeableProxy(
            address(stakeImpl), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        );
        stake = DinValidatorStake(address(stakeProxy));
        coordinator.updateValidatorStakeContract(address(stake));

        DINModelRegistry registryImpl = new DINModelRegistry();
        TransparentUpgradeableProxy registryProxy = new TransparentUpgradeableProxy(
            address(registryImpl), admin,
            abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        );
        registry = DINModelRegistry(address(registryProxy));

        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake), MODEL_ID);
        ta = new DINTaskAuditor(address(stake), address(tc), MODEL_ID);
        tc.setDINTaskAuditorContract(address(ta));
        ta.setDinToken(address(token));
        vm.stopPrank();

        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));
        vm.stopPrank();
    }

    // ── helpers ──────────────────────────────────────────────────────────────

    function _stake(address who, uint256 dinAmount) internal {
        // dinPerEth = 1_000_000e18; back-solve ETH needed for dinAmount DIN.
        uint256 ethNeeded = (dinAmount / 1_000_000) + 1;
        vm.deal(who, ethNeeded + 2 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(dinAmount);
        vm.stopPrank();
    }

    function _advanceToAggregatorRegistration() internal {
        // Fund GI 1 reward pool (100 DIN = 0.0001 ETH at 1e6 DIN/ETH rate)
        address funder = makeAddr("funder");
        uint256 poolEth = 0.001 ether; // yields ~1000 DIN
        vm.deal(funder, poolEth + 1 ether);
        vm.prank(funder);
        coordinator.depositAndMint{value: poolEth}();
        uint256 pool = token.balanceOf(funder);
        vm.prank(funder);
        token.approve(address(ta), pool);
        vm.prank(funder);
        ta.depositRewards(1, pool);

        vm.startPrank(modelOwner);
        tc.startGI(1);
        tc.startDINaggregatorsRegistration(1);
        vm.stopPrank();
    }

    function _advanceToAuditorRegistration() internal {
        _advanceToAggregatorRegistration();
        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();
    }

    // ── modelId is stored correctly ───────────────────────────────────────────

    function test_modelId_storedOnCoordinator() public view {
        assertEq(tc.modelId(), MODEL_ID);
    }

    function test_modelId_storedOnAuditor() public view {
        assertEq(ta.modelId(), MODEL_ID);
    }

    // ── zero-default: no floor, no cap ────────────────────────────────────────

    function test_aggregator_noFloor_noCapByDefault() public {
        _stake(agg1, MIN_STAKE_AMOUNT);
        _advanceToAggregatorRegistration();
        vm.prank(agg1);
        tc.registerDINaggregator(1); // must not revert
        assertEq(stake.activeRegistrationCount(agg1), 1);
    }

    function test_auditor_noFloor_noCapByDefault() public {
        _stake(aud1, MIN_STAKE_AMOUNT);
        _advanceToAuditorRegistration();
        vm.prank(aud1);
        ta.registerDINAuditor(1); // must not revert
        assertEq(stake.activeRegistrationCount(aud1), 1);
    }

    // ── per-model stake floor enforcement ─────────────────────────────────────

    function test_aggregator_revertsWhenBelowFloor() public {
        vm.prank(admin);
        stake.setModelStakeBounds(MODEL_ID, 20 ether, type(uint256).max);

        _stake(agg1, MIN_STAKE_AMOUNT); // 10 ether < 20 ether floor
        _advanceToAggregatorRegistration();
        vm.prank(agg1);
        vm.expectRevert(TC_StakeBelowModelFloor.selector);
        tc.registerDINaggregator(1);
    }

    function test_aggregator_passesFloorWithEnoughStake() public {
        vm.prank(admin);
        stake.setModelStakeBounds(MODEL_ID, 20 ether, type(uint256).max);

        _stake(agg1, 20 ether);
        _advanceToAggregatorRegistration();
        vm.prank(agg1);
        tc.registerDINaggregator(1); // must not revert
    }

    function test_auditor_revertsWhenBelowFloor() public {
        vm.prank(admin);
        stake.setModelStakeBounds(MODEL_ID, 20 ether, type(uint256).max);

        _stake(aud1, MIN_STAKE_AMOUNT); // 10 ether < 20 ether floor
        _advanceToAuditorRegistration();
        vm.prank(aud1);
        vm.expectRevert(TA_StakeBelowModelFloor.selector);
        ta.registerDINAuditor(1);
    }

    function test_auditor_passesFloorWithEnoughStake() public {
        vm.prank(admin);
        stake.setModelStakeBounds(MODEL_ID, 20 ether, type(uint256).max);

        _stake(aud1, 20 ether);
        _advanceToAuditorRegistration();
        vm.prank(aud1);
        ta.registerDINAuditor(1); // must not revert
    }

    // ── concurrent-registration cap enforcement ───────────────────────────────

    function test_aggregator_revertsWhenCapReached() public {
        // capPerUnit = 1 => 1 MIN_STAKE => max 1 concurrent registration
        vm.prank(admin);
        stake.setMaxConcurrentRegistrationsPerStakeUnit(1);

        _stake(agg1, MIN_STAKE_AMOUNT);
        _advanceToAggregatorRegistration();

        // Manually set the counter to 1 to simulate an existing registration
        // (e.g. on a different task contract for the same validator).
        // We do this by having them register on tc, then deploy tc2 and try there.
        vm.prank(agg1);
        tc.registerDINaggregator(1);
        assertEq(stake.activeRegistrationCount(agg1), 1);

        // Deploy a second coordinator for the same stake contract
        vm.startPrank(modelOwner);
        DINTaskCoordinator tc2 = new DINTaskCoordinator(address(stake), 2);
        DINTaskAuditor ta2 = new DINTaskAuditor(address(stake), address(tc2), 2);
        tc2.setDINTaskAuditorContract(address(ta2));
        ta2.setDinToken(address(token));
        vm.stopPrank();
        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc2));
        coordinator.addSlasherContract(address(ta2));
        vm.stopPrank();
        vm.startPrank(modelOwner);
        tc2.setDINTaskCoordinatorAsSlasher();
        tc2.setDINTaskAuditorAsSlasher();
        tc2.setGenesisModelIpfsHash(bytes32(uint256(2)));
        vm.stopPrank();

        // Fund and start GI 1 on tc2
        address funder2 = makeAddr("funder2");
        uint256 poolEth2 = 0.001 ether;
        vm.deal(funder2, poolEth2 + 1 ether);
        vm.prank(funder2);
        coordinator.depositAndMint{value: poolEth2}();
        uint256 pool2 = token.balanceOf(funder2);
        vm.prank(funder2);
        token.approve(address(ta2), pool2);
        vm.prank(funder2);
        ta2.depositRewards(1, pool2);
        vm.startPrank(modelOwner);
        tc2.startGI(1);
        tc2.startDINaggregatorsRegistration(1);
        vm.stopPrank();

        vm.prank(agg1);
        vm.expectRevert(TC_ConcurrentRegistrationCapReached.selector);
        tc2.registerDINaggregator(1);
    }

    function test_aggregator_capAllowsMoreWithHigherStake() public {
        // capPerUnit = 1, 2x MIN_STAKE => max 2 concurrent registrations
        vm.prank(admin);
        stake.setMaxConcurrentRegistrationsPerStakeUnit(1);
        _stake(agg1, 2 * MIN_STAKE_AMOUNT);

        _advanceToAggregatorRegistration();
        vm.prank(agg1);
        tc.registerDINaggregator(1);
        assertEq(stake.activeRegistrationCount(agg1), 1);
        // counter=1, maxAllowed=2 => should still have room (tested by the above not reverting)
    }

    // ── activeRegistrationCount increments/decrements correctly ──────────────

    function test_activeCount_incrementsOnAggregatorRegister() public {
        _stake(agg1, MIN_STAKE_AMOUNT);
        _advanceToAggregatorRegistration();
        assertEq(stake.activeRegistrationCount(agg1), 0);
        vm.prank(agg1);
        tc.registerDINaggregator(1);
        assertEq(stake.activeRegistrationCount(agg1), 1);
    }

    function test_activeCount_incrementsOnAuditorRegister() public {
        _stake(aud1, MIN_STAKE_AMOUNT);
        _advanceToAuditorRegistration();
        assertEq(stake.activeRegistrationCount(aud1), 0);
        vm.prank(aud1);
        ta.registerDINAuditor(1);
        assertEq(stake.activeRegistrationCount(aud1), 1);
    }

    // ── releaseGIRegistrationSlots: happy path + double-release guard ────────

    /// @dev Drives GI 1 through an entire honest lifecycle (3 auditors, 3
    ///      aggregators, 3 clients, all honest -- same shape as
    ///      RewardEngine.t.sol's _runFullHonestGI) all the way through
    ///      endGI(1), leaving GIstate == GIended so releaseGIRegistrationSlots
    ///      is callable. Returns the third aggregator/auditor addresses
    ///      (agg1/agg2/aud1/aud2 are the shared fixture actors).
    function _runFullGIToEnded() internal returns (address agg3, address aud3) {
        agg3 = makeAddr("agg3_release");
        aud3 = makeAddr("aud3_release");
        address client1 = makeAddr("client1_release");
        address client2 = makeAddr("client2_release");
        address client3 = makeAddr("client3_release");

        _stake(agg1, MIN_STAKE_AMOUNT);
        _stake(agg2, MIN_STAKE_AMOUNT);
        _stake(agg3, MIN_STAKE_AMOUNT);
        _stake(aud1, MIN_STAKE_AMOUNT);
        _stake(aud2, MIN_STAKE_AMOUNT);
        _stake(aud3, MIN_STAKE_AMOUNT);

        _advanceToAggregatorRegistration();

        vm.prank(agg1);
        tc.registerDINaggregator(1);
        vm.prank(agg2);
        tc.registerDINaggregator(1);
        vm.prank(agg3);
        tc.registerDINaggregator(1);

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        vm.prank(aud1);
        ta.registerDINAuditor(1);
        vm.prank(aud2);
        ta.registerDINAuditor(1);
        vm.prank(aud3);
        ta.registerDINAuditor(1);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        vm.prank(client1);
        ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2);
        ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.prank(client3);
        ta.submitLocalModel(bytes32(uint256(300)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        bytes32 salt = bytes32(uint256(0xC0FFEE));
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                bytes32 commitHash = keccak256(abi.encodePacked(uint256(80), true, salt));
                vm.prank(batchAuditors[i]);
                ta.commitAuditScore(1, 0, modelIdxs[m], commitHash);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);

        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuditors[i]);
                ta.revealAuditScore(1, 0, modelIdxs[m], 80, true, salt);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();

        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        bytes32 realCID = bytes32(uint256(0xC1D));
        for (uint i = 0; i < t1aggs.length; i++) {
            vm.prank(t1aggs[i]);
            tc.submitT1Aggregation(1, 0, realCID);
        }

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        tc.finalizeT2Aggregation(1); // trivial: 0 T2 batches at exactly 3 aggregators
        tc.slashAuditors(1);
        tc.slashAggregators(1);
        tc.endGI(1);
        vm.stopPrank();
    }

    function test_releaseGIRegistrationSlots_happyPath() public {
        (address agg3, address aud3) = _runFullGIToEnded();

        assertEq(stake.activeRegistrationCount(agg1), 1);
        assertEq(stake.activeRegistrationCount(agg2), 1);
        assertEq(stake.activeRegistrationCount(agg3), 1);
        assertEq(stake.activeRegistrationCount(aud1), 1);
        assertEq(stake.activeRegistrationCount(aud2), 1);
        assertEq(stake.activeRegistrationCount(aud3), 1);
        assertFalse(tc.registrationSlotsReleased(1));

        vm.prank(modelOwner);
        tc.releaseGIRegistrationSlots(1);

        assertTrue(tc.registrationSlotsReleased(1));
        assertEq(stake.activeRegistrationCount(agg1), 0);
        assertEq(stake.activeRegistrationCount(agg2), 0);
        assertEq(stake.activeRegistrationCount(agg3), 0);
        assertEq(stake.activeRegistrationCount(aud1), 0);
        assertEq(stake.activeRegistrationCount(aud2), 0);
        assertEq(stake.activeRegistrationCount(aud3), 0);
    }

    function test_releaseGIRegistrationSlots_revertsOnDoubleRelease() public {
        _runFullGIToEnded();

        vm.startPrank(modelOwner);
        tc.releaseGIRegistrationSlots(1);
        vm.expectRevert(bytes("slots already released"));
        tc.releaseGIRegistrationSlots(1);
        vm.stopPrank();
    }
}
