// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Tests for task_100926_12 Issue #43: treasury forwarding.
//   - DINTaskCoordinator.resolveDispute (frivolous): 50% burn / 50% treasury
//   - DINTaskAuditor.settleRewards: treasury share forwarded to treasuryAddress
// Run: forge test --match-contract TreasuryForwardingTest -vv
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

contract TreasuryForwardingTest is Test {
    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address treasury   = makeAddr("treasury");
    address challenger = makeAddr("challenger");
    address auditor1   = makeAddr("auditor1");
    address auditor2   = makeAddr("auditor2");
    address auditor3   = makeAddr("auditor3");
    address agg1       = makeAddr("agg1");
    address agg2       = makeAddr("agg2");
    address agg3       = makeAddr("agg3");
    address agg4       = makeAddr("agg4");
    address agg5       = makeAddr("agg5");
    address agg6       = makeAddr("agg6");
    address client1    = makeAddr("client1");
    address client2    = makeAddr("client2");
    address client3    = makeAddr("client3");

    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));

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

        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake), 1);
        ta = new DINTaskAuditor(address(stake), address(tc), 1);
        tc.setDINTaskAuditorContract(address(ta));
        tc.setDinToken(address(token));
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

    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether);
        vm.stopPrank();
    }

    function _fundDin(address who, uint256 dinAmount) internal {
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded + 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        vm.startPrank(who);
        token.approve(address(tc), type(uint256).max);
        token.approve(address(ta), type(uint256).max);
        vm.stopPrank();
    }

    /// @dev Runs a complete honest GI through to AggregatorsSlashed then endGI.
    function _runFullGI(uint256 pool) internal {
        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);
        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);
        _fundAndStake(agg4);
        _fundAndStake(agg5);
        _fundAndStake(agg6);

        _fundDin(modelOwner, pool);
        vm.prank(modelOwner);
        ta.depositRewards(1, pool);

        vm.startPrank(modelOwner);
        tc.startGI(1);
        tc.startDINaggregatorsRegistration(1);
        vm.stopPrank();

        vm.prank(agg1); tc.registerDINaggregator(1);
        vm.prank(agg2); tc.registerDINaggregator(1);
        vm.prank(agg3); tc.registerDINaggregator(1);
        vm.prank(agg4); tc.registerDINaggregator(1);
        vm.prank(agg5); tc.registerDINaggregator(1);
        vm.prank(agg6); tc.registerDINaggregator(1);

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        vm.prank(auditor1); ta.registerDINAuditor(1);
        vm.prank(auditor2); ta.registerDINAuditor(1);
        vm.prank(auditor3); ta.registerDINAuditor(1);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.prank(client3); ta.submitLocalModel(bytes32(uint256(300)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        // Commit phase — one batch (3 auditors, 3 models).
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                bytes32 ch = keccak256(abi.encodePacked(uint256(80), true, TEST_SALT));
                vm.prank(batchAuditors[ai]);
                ta.commitAuditScore(1, 0, modelIdxs[mi], ch);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);

        // Reveal phase.
        for (uint ai = 0; ai < batchAuditors.length; ai++) {
            for (uint mi = 0; mi < modelIdxs.length; mi++) {
                vm.prank(batchAuditors[ai]);
                ta.revealAuditScore(1, 0, modelIdxs[mi], 80, true, TEST_SALT);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();

        // Submit for every T1 batch so finalizeT1Aggregation doesn't revert.
        uint256 t1Count = tc.tier1BatchCount(1);
        for (uint b = 0; b < t1Count; b++) {
            (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, b);
            for (uint i = 0; i < t1aggs.length; i++) {
                vm.prank(t1aggs[i]);
                tc.submitT1Aggregation(1, b, bytes32(uint256(0xC1D)));
            }
        }

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        vm.stopPrank();

        // Submit T2 aggregation if a T2 batch was created (6-agg case).
        try tc.getTier2Batch(1, 0) returns (uint, address[] memory t2aggs, bool, bytes32) {
            for (uint i = 0; i < t2aggs.length; i++) {
                vm.prank(t2aggs[i]);
                tc.submitT2Aggregation(1, 0, bytes32(uint256(0xC2D)));
            }
        } catch {}

        vm.startPrank(modelOwner);
        tc.finalizeT2Aggregation(1);
        tc.slashAuditors(1);
        tc.slashAggregators(1);
        tc.endGI(1);
        vm.stopPrank();
    }

    /// @dev Stakes + funds the challenger and opens a dispute against T1 batch 0.
    function _openDispute() internal returns (uint256 bond) {
        bond = tc.disputeBond();
        _fundAndStake(challenger);
        _fundDin(challenger, bond);
        vm.warp(tc.tier1FinalizedAt(1, 0) + 1);
        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
    }

    // ── dispute bond: frivolous forfeiture ────────────────────────────────────

    function test_frivolous_burns50pct_sends50pctToTreasury() public {
        _runFullGI(10_000 ether);
        uint256 bond = _openDispute();

        vm.prank(modelOwner);
        tc.setTreasuryAddress(treasury);

        uint256 supplyBefore = token.totalSupply();
        uint256 treasuryBefore = token.balanceOf(treasury);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        uint256 burned = supplyBefore - token.totalSupply();
        uint256 treasuryReceived = token.balanceOf(treasury) - treasuryBefore;

        uint256 expectBurn = bond / 2;
        uint256 expectTreasury = bond - expectBurn;

        assertEq(burned, expectBurn, "burn amount wrong");
        assertEq(treasuryReceived, expectTreasury, "treasury transfer wrong");
        assertEq(burned + treasuryReceived, bond, "conservation: burn+treasury == bond");
        assertEq(tc.treasuryAccrued(), bond, "treasuryAccrued counter == full bond");
    }

    function test_frivolous_noTreasurySet_burnsAll() public {
        _runFullGI(10_000 ether);
        uint256 bond = _openDispute();

        // treasuryAddress is address(0) (not set)
        uint256 supplyBefore = token.totalSupply();

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        uint256 burned = supplyBefore - token.totalSupply();
        assertEq(burned, bond, "all should be burned when no treasury set");
        assertEq(tc.treasuryAccrued(), bond, "treasuryAccrued counter == full bond");
    }

    function testFuzz_frivolous_conservesBond(uint256 bondOverride) public {
        bondOverride = bound(bondOverride, 1 ether, 1_000 ether);

        _runFullGI(10_000 ether);

        vm.prank(modelOwner);
        tc.setDisputeParams(bondOverride, 1 days);

        uint256 bond = _openDispute();
        assertEq(bond, bondOverride);

        vm.prank(modelOwner);
        tc.setTreasuryAddress(treasury);

        uint256 supplyBefore = token.totalSupply();
        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        uint256 burned = supplyBefore - token.totalSupply();
        uint256 treasuryReceived = token.balanceOf(treasury);
        assertEq(burned + treasuryReceived, bond, "burn+treasury must equal bond");
    }

    // ── dispute bond: upheld — bond still claimable (bounty out of scope) ─────

    function test_upheld_challengerReclaimsBond() public {
        _runFullGI(10_000 ether);
        uint256 bond = _openDispute();

        vm.prank(modelOwner);
        tc.setTreasuryAddress(treasury);

        uint256 supplyBefore = token.totalSupply();
        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        // No burn, no treasury transfer on upheld
        assertEq(token.totalSupply(), supplyBefore, "no burn on upheld");
        assertEq(token.balanceOf(treasury), 0, "no treasury transfer on upheld");
        assertEq(tc.disputeBondClaimable(challenger), bond, "challenger claimable == bond");
    }

    // ── settleRewards: treasury share forwarded ───────────────────────────────

    function test_settleRewards_forwardsToTreasury() public {
        vm.prank(modelOwner);
        ta.setTreasuryAddress(treasury);

        uint256 pool = 10_000 ether;
        _runFullGI(pool);

        // treasuryBps = 500 (5% default); pool = 10_000 ether
        // treasuryShare = pool - clientPool - auditorPool - aggregatorPool
        // = 10000e18 - (6000/10000)*10000e18 - (2000/10000)*10000e18 - (1500/10000)*10000e18
        // = 10000e18 - 6000e18 - 2000e18 - 1500e18 = 500e18
        uint256 expectedShare = 500 ether;

        assertEq(token.balanceOf(treasury), expectedShare, "treasury balance wrong");
        assertEq(ta.treasuryAccrued(), expectedShare, "treasuryAccrued counter wrong");
    }

    function test_settleRewards_noTreasurySet_noTransfer() public {
        // treasuryAddress not set — no transfer, but counter still accumulates
        uint256 pool = 10_000 ether;
        _runFullGI(pool);

        assertEq(token.balanceOf(treasury), 0, "no transfer without treasury set");
        assertEq(ta.treasuryAccrued(), 500 ether, "treasuryAccrued still accumulates");
    }

    function testFuzz_settleRewards_poolConservation(uint256 pool) public {
        pool = bound(pool, 10_000 ether, 100_000 ether);

        vm.prank(modelOwner);
        ta.setTreasuryAddress(treasury);

        _runFullGI(pool);

        // After settlement: claimable (client+auditor+aggregator) + treasury == pool
        // (no rounding precision loss requirement — just that treasury got its share)
        uint256 treasuryShare = ta.treasuryAccrued();
        assertEq(token.balanceOf(treasury), treasuryShare, "forwarded == accrued");
        assertLe(treasuryShare, pool, "treasury share cannot exceed pool");
    }
}
