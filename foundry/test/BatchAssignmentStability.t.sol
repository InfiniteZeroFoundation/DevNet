// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Position-stable batch seat assignment (issue #243 / BL-26).
//
// Invariant under test: when the autoCreateTier1AndTier2 or createAuditorsBatches
// seed is already locked, an unstake by a PRIMARY-SEAT holder changes ONLY that
// seat (filled by the first active reserve entry).  Every other validator's
// batch and seat position is identical whether or not the unstake happened.
//
// Run: forge test --match-contract BatchAssignmentStabilityTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DinTreasury} from "../src/DinTreasury.sol";
import {DinFeeRouter} from "../src/DinFeeRouter.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {auditCommitHash} from "./utils/AuditCommitHash.sol";

contract BatchAssignmentStabilityTest is Test {
    // ─────────────────────────────────────────────────────────────────────
    // Platform contracts
    // ─────────────────────────────────────────────────────────────────────

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DinTreasury treasury;
    DinFeeRouter feeRouter;

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");

    bytes32 constant SALT = bytes32(uint256(0xB47C));

    // 9 aggregators: 3 T1 seats + 3 T2 seats + 3 reserve
    address agg0 = makeAddr("agg0");
    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");
    address agg4 = makeAddr("agg4");
    address agg5 = makeAddr("agg5");
    address agg6 = makeAddr("agg6");
    address agg7 = makeAddr("agg7");
    address agg8 = makeAddr("agg8");

    // 3 auditors (auditorsPerBatch default = 3)
    address aud0 = makeAddr("aud0");
    address aud1 = makeAddr("aud1");
    address aud2 = makeAddr("aud2");

    // ─────────────────────────────────────────────────────────────────────
    // Deployment helpers (identical pattern to SecurityFindings.t.sol)
    // ─────────────────────────────────────────────────────────────────────

    function _deployPlatform() internal {
        vm.startPrank(admin);
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(new DinTreasury()), admin, abi.encodeCall(DinTreasury.initialize, ())
        ))));

        DinToken tokenImpl = new DinToken();
        token = DinToken(address(new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        )));

        DinCoordinator coordinatorImpl = new DinCoordinator();
        coordinator = DinCoordinator(address(new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin, abi.encodeCall(DinCoordinator.initialize, (address(token)))
        )));
        token.setCoordinator(address(coordinator));

        feeRouter = DinFeeRouter(address(new TransparentUpgradeableProxy(
            address(new DinFeeRouter()), admin,
            abi.encodeCall(DinFeeRouter.initialize, (address(token), address(treasury)))
        )));
        coordinator.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(coordinator));

        DinValidatorStake stakeImpl = new DinValidatorStake();
        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(stakeImpl), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));

        DINModelRegistry registryImpl = new DINModelRegistry();
        registry = DINModelRegistry(address(new TransparentUpgradeableProxy(
            address(registryImpl), admin,
            abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        )));
        registry.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(registry));
        stake.setSlashTreasury(address(treasury));
        vm.stopPrank();
    }

    function _deployTaskPair() internal {
        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake), 1);
        ta = new DINTaskAuditor(address(stake), address(tc), 1);
        tc.setDINTaskAuditorContract(address(ta));
        vm.stopPrank();

        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));

        ta.setDinToken(address(token));
        vm.deal(modelOwner, 1 ether);
        coordinator.depositAndMint{value: 0.001 ether}();
        token.approve(address(ta), type(uint256).max);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether);
        vm.stopPrank();
    }

    // ─────────────────────────────────────────────────────────────────────
    // Drives the GI up to the point just after lockAggSeed, before
    // autoCreateTier1AndTier2 is called.
    //
    // Setup: 9 aggregators, 3 auditors, 3 models.
    //   T1_MODELS_PER_BATCH=3 → t1cnt=1, T1 seats = 3
    //   rLen=9, rLen-3=6 >= 3 → hasT2=true, T2 seats = 3
    //   reserve = positions 6..8 in the shuffled list
    // ─────────────────────────────────────────────────────────────────────
    function _runToSeedLocked() internal {
        _deployPlatform();
        _deployTaskPair();

        address[9] memory aggs = [agg0,agg1,agg2,agg3,agg4,agg5,agg6,agg7,agg8];
        for (uint i = 0; i < 9; i++) _fundAndStake(aggs[i]);
        _fundAndStake(aud0);
        _fundAndStake(aud1);
        _fundAndStake(aud2);

        // ── aggregator registration ──────────────────────────────────────
        vm.prank(modelOwner);
        tc.startDINaggregatorsRegistration(1);

        for (uint i = 0; i < 9; i++) {
            vm.prank(aggs[i]);
            tc.registerDINaggregator(1);
        }

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);

        // ── auditor registration ─────────────────────────────────────────
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        vm.prank(aud0); ta.registerDINAuditor(1);
        vm.prank(aud1); ta.registerDINAuditor(1);
        vm.prank(aud2); ta.registerDINAuditor(1);

        // ── LMS: 3 models (gives exactly 1 T1 batch + T2) ───────────────
        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        address client1 = makeAddr("client1");
        address client2 = makeAddr("client2");
        address client3 = makeAddr("client3");
        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.prank(client3); ta.submitLocalModel(bytes32(uint256(300)), 1);

        // ── audit seed, batches, evaluation ─────────────────────────────
        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAuditSeed(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory batchAuds, uint[] memory modelIdxs,) = ta.getAuditorsBatch(1, 0);
        for (uint i = 0; i < batchAuds.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuds[i]);
                ta.commitAuditScore(
                    1, 0, modelIdxs[m],
                    auditCommitHash(uint256(100), true, SALT, batchAuds[i], 1, 0, modelIdxs[m])
                );
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);

        for (uint i = 0; i < batchAuds.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuds[i]);
                ta.revealAuditScore(1, 0, modelIdxs[m], 100, true, SALT);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAggSeed(1);
        vm.stopPrank();
        // ← caller may now call tc.autoCreateTier1AndTier2(1)
    }

    // ─────────────────────────────────────────────────────────────────────
    // Aggregator-side: position-stable seat assignment
    // ─────────────────────────────────────────────────────────────────────

    /// @dev With seed locked, discover the baseline assignment, then revert,
    ///      unstake the primary-seat holder at T1[0], and assert only that
    ///      seat changes — every other validator stays in their exact position.
    function test_aggregator_unstakeOnlydisplacesOwnSeat() public {
        _runToSeedLocked();

        // ── snapshot: seed is locked, batches not yet created ──────────
        uint256 snap = vm.snapshot();

        // ── baseline run: discover who occupies each seat ───────────────
        vm.prank(modelOwner);
        tc.autoCreateTier1AndTier2(1);

        (, address[] memory t1agg,,, ) = tc.getTier1Batch(1, 0);
        (, address[] memory t2agg,, )  = tc.getTier2Batch(1, 0);

        address seat0  = t1agg[0]; // this seat will be vacated
        address seat1  = t1agg[1];
        address seat2  = t1agg[2];
        address t2s0   = t2agg[0];
        address t2s1   = t2agg[1];
        address t2s2   = t2agg[2];

        // ── revert, unstake the seat-0 holder ───────────────────────────
        vm.revertTo(snap);

        vm.prank(seat0);
        stake.unstake(10 ether); // drops to Exiting — isValidatorActive = false

        // ── re-run with seat0 inactive ───────────────────────────────────
        vm.prank(modelOwner);
        tc.autoCreateTier1AndTier2(1);

        (, address[] memory t1agg2,,, ) = tc.getTier1Batch(1, 0);
        (, address[] memory t2agg2,, )  = tc.getTier2Batch(1, 0);

        // seat0 must be replaced (by first active reserve) — but NOT by seat0
        assertTrue(t1agg2[0] != seat0, "vacated seat must be filled by reserve");
        // all other primary seats are unchanged
        assertEq(t1agg2[1], seat1, "T1 seat1 must not move");
        assertEq(t1agg2[2], seat2, "T1 seat2 must not move");
        // T2 batch is entirely unchanged
        assertEq(t2agg2[0], t2s0, "T2 seat0 must not move");
        assertEq(t2agg2[1], t2s1, "T2 seat1 must not move");
        assertEq(t2agg2[2], t2s2, "T2 seat2 must not move");
        // replaced seat is active
        assertTrue(stake.isValidatorActive(t1agg2[0]), "replacement must be active");
    }

    /// @dev Same check for a T2 seat vacancy: only the T2 seat changes.
    function test_aggregator_t2SeatUnstakeOnlyDisplacesT2Seat() public {
        _runToSeedLocked();

        uint256 snap = vm.snapshot();

        vm.prank(modelOwner);
        tc.autoCreateTier1AndTier2(1);

        (, address[] memory t1agg,,, ) = tc.getTier1Batch(1, 0);
        (, address[] memory t2agg,, )  = tc.getTier2Batch(1, 0);

        address t1s0 = t1agg[0]; address t1s1 = t1agg[1]; address t1s2 = t1agg[2];
        address t2s0 = t2agg[0]; // this seat will be vacated

        vm.revertTo(snap);

        vm.prank(t2s0);
        stake.unstake(10 ether);

        vm.prank(modelOwner);
        tc.autoCreateTier1AndTier2(1);

        (, address[] memory t1agg2,,, ) = tc.getTier1Batch(1, 0);
        (, address[] memory t2agg2,, )  = tc.getTier2Batch(1, 0);

        // T1 batch is entirely unchanged
        assertEq(t1agg2[0], t1s0, "T1 seat0 must not move");
        assertEq(t1agg2[1], t1s1, "T1 seat1 must not move");
        assertEq(t1agg2[2], t1s2, "T1 seat2 must not move");
        // only T2 seat0 changed
        assertTrue(t2agg2[0] != t2s0, "vacated T2 seat must be filled by reserve");
        assertTrue(stake.isValidatorActive(t2agg2[0]), "T2 replacement must be active");
    }

    // ─────────────────────────────────────────────────────────────────────
    // Auditor-side: position-stable seat assignment
    //
    // With 6 auditors (3 primary + 3 reserve) and 3 models,
    // batchCnt = 1, vPre = 3, reserve = positions 3..5.
    // ─────────────────────────────────────────────────────────────────────

    function _runToAuditSeedLocked() internal {
        _deployPlatform();
        _deployTaskPair();

        // 6 auditors: 3 primary seats + 3 reserve
        address[6] memory auds = [
            makeAddr("aud_s0"), makeAddr("aud_s1"), makeAddr("aud_s2"),
            makeAddr("aud_r0"), makeAddr("aud_r1"), makeAddr("aud_r2")
        ];
        for (uint i = 0; i < 6; i++) _fundAndStake(auds[i]);

        // Need at least 3 aggregators to drive the GI forward
        address a0 = makeAddr("driveAgg0");
        address a1 = makeAddr("driveAgg1");
        address a2 = makeAddr("driveAgg2");
        _fundAndStake(a0); _fundAndStake(a1); _fundAndStake(a2);

        vm.prank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        vm.prank(a0); tc.registerDINaggregator(1);
        vm.prank(a1); tc.registerDINaggregator(1);
        vm.prank(a2); tc.registerDINaggregator(1);

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        for (uint i = 0; i < 6; i++) {
            vm.prank(auds[i]);
            ta.registerDINAuditor(1);
        }

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        // 3 models: 1 audit batch of 3 models
        vm.prank(makeAddr("c0")); ta.submitLocalModel(bytes32(uint256(10)), 1);
        vm.prank(makeAddr("c1")); ta.submitLocalModel(bytes32(uint256(20)), 1);
        vm.prank(makeAddr("c2")); ta.submitLocalModel(bytes32(uint256(30)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAuditSeed(1);
        vm.stopPrank();
        // ← caller may now call tc.createAuditorsBatches(1)
    }

    /// @dev With audit seed locked, discover baseline auditor assignment, revert,
    ///      unstake the seat-0 auditor, and assert only that seat changes.
    function test_auditor_unstakeOnlyDisplacesOwnSeat() public {
        _runToAuditSeedLocked();

        uint256 snap = vm.snapshot();

        // baseline
        vm.prank(modelOwner);
        tc.createAuditorsBatches(1);

        (, address[] memory auds, ,) = ta.getAuditorsBatch(1, 0);
        address aseat0 = auds[0];
        address aseat1 = auds[1];
        address aseat2 = auds[2];

        vm.revertTo(snap);

        vm.prank(aseat0);
        stake.unstake(10 ether);

        vm.prank(modelOwner);
        tc.createAuditorsBatches(1);

        (, address[] memory auds2, ,) = ta.getAuditorsBatch(1, 0);

        assertTrue(auds2[0] != aseat0, "vacated auditor seat must be filled by reserve");
        assertEq(auds2[1], aseat1, "auditor seat1 must not move");
        assertEq(auds2[2], aseat2, "auditor seat2 must not move");
        assertTrue(stake.isValidatorActive(auds2[0]), "replacement auditor must be active");
    }
}
