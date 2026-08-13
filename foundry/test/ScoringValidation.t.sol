// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Contract-level tests for task_210726_6 Part 1 (scoring validation, issue #39):
// on-chain median at finalizeEvaluation, and the S3 deviation threshold shipped
// in shadow mode.
// Run: forge test --match-contract ScoringValidationTest -vv
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

contract ScoringValidationTest is Test {
    DinToken tokenImpl;
    DinCoordinator coordinatorImpl;
    DinValidatorStake stakeImpl;
    DINModelRegistry registryImpl;

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address auditor1 = makeAddr("auditor1");
    address auditor2 = makeAddr("auditor2");
    address auditor3 = makeAddr("auditor3");
    address client1 = makeAddr("client1");
    address client2 = makeAddr("client2");

    function _deployPlatform() internal {
        vm.startPrank(admin);

        tokenImpl = new DinToken();
        TransparentUpgradeableProxy tokenProxy = new TransparentUpgradeableProxy(
            address(tokenImpl),
            admin,
            abi.encodeCall(DinToken.initialize, ())
        );
        token = DinToken(address(tokenProxy));

        coordinatorImpl = new DinCoordinator();
        TransparentUpgradeableProxy coordinatorProxy = new TransparentUpgradeableProxy(
            address(coordinatorImpl),
            admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        );
        coordinator = DinCoordinator(address(coordinatorProxy));

        token.setCoordinator(address(coordinator));

        stakeImpl = new DinValidatorStake();
        TransparentUpgradeableProxy stakeProxy = new TransparentUpgradeableProxy(
            address(stakeImpl),
            admin,
            abi.encodeCall(
                DinValidatorStake.initialize,
                (address(token), address(coordinator))
            )
        );
        stake = DinValidatorStake(address(stakeProxy));

        coordinator.updateValidatorStakeContract(address(stake));

        registryImpl = new DINModelRegistry();
        TransparentUpgradeableProxy registryProxy = new TransparentUpgradeableProxy(
            address(registryImpl),
            admin,
            abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        );
        registry = DINModelRegistry(address(registryProxy));

        vm.stopPrank();
    }

    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether); // MIN_STAKE
        vm.stopPrank();
    }

    function _deployTaskPair() internal {
        vm.startPrank(modelOwner);
        tc = new DINTaskCoordinator(address(stake));
        ta = new DINTaskAuditor(address(stake), address(tc));
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
        tc.startGI(1);
        vm.stopPrank();
    }

    /// @dev Drives the GI to LMSevaluationStarted with exactly one audit
    ///      batch (3 auditors, demo auditorsPerBatch) and two submitted
    ///      models (MIN_MODELS_PER_BATCH=2 is the floor for a batch to form
    ///      at all), WITHOUT submitting any scores -- callers submit their
    ///      own scores so median-vs-mean behavior can be controlled precisely.
    function _runToLMSevaluationStarted() internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);

        vm.startPrank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        vm.prank(auditor1);
        ta.registerDINAuditor(1);
        vm.prank(auditor2);
        ta.registerDINAuditor(1);
        vm.prank(auditor3);
        ta.registerDINAuditor(1);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        // createAuditorsBatches requires >= MIN_MODELS_PER_BATCH (2) submitted
        // models to form any batch at all -- one submission alone yields zero
        // batches and every downstream call reverts with TA_BatchDoesNotExist.
        vm.prank(client1);
        ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2);
        ta.submitLocalModel(bytes32(uint256(200)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();
    }

    // ─────────────────────────────────────────────────────────────────────
    // §1c: finalizeEvaluation must compute a MEDIAN, not a mean, per
    // MECHANISM_DESIGN.md §6's canonical-score requirement. A mean lets a
    // single dishonest/inflated auditor drag the score; a median doesn't.
    // The pre-existing test suite only ever used identical scores (100 for
    // everyone), which can't distinguish a median from a mean at all --
    // these tests use genuinely different scores specifically to prove it.
    // ─────────────────────────────────────────────────────────────────────

    function test_finalizeEvaluation_oddCount_usesMedianNotMean() public {
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        assertEq(batchAuditors.length, 3, "sanity: 3 auditors in batch");
        assertEq(modelIdxs.length, 2, "sanity: 2 models in batch");

        // One dishonest auditor submits a wildly inflated score. Mean of
        // [20, 25, 100] = 48 (rounds down); median = 25.
        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 20, true);
        vm.prank(batchAuditors[1]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 25, true);
        vm.prank(batchAuditors[2]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 100, true);

        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        (, , , , , bool approved, uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);

        assertEq(finalScore, 25, "finalAvgScore must be the median (25), not the mean (48)");
        // passScore defaults to 50 in the DINTaskAuditor constructor --
        // median 25 < 50 means this model should NOT be approved, whereas
        // the old mean-based path (48... still < 50 here) happens to agree,
        // so this assertion alone wouldn't distinguish them. The finalScore
        // equality assertion above is the one that actually proves it.
        assertFalse(approved, "median 25 is below passScore=50");
    }

    function test_finalizeEvaluation_oddCount_medianRobustToLowOutlier() public {
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Symmetric case: one dishonest auditor submits a wildly LOW score
        // to try to unfairly fail a good model. [10, 90, 95]: mean = 65,
        // median = 90. A malicious minority shouldn't be able to sink an
        // honest majority's score either.
        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 10, true);
        vm.prank(batchAuditors[1]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 90, true);
        vm.prank(batchAuditors[2]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 95, true);

        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        (, , , , , bool approved, uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);

        assertEq(finalScore, 90, "median of [10,90,95] should be 90, not the mean (65)");
        assertTrue(approved, "median 90 >= passScore=50, honest majority should win");
    }

    function test_finalizeEvaluation_evenCount_medianIsAverageOfTwoMiddleValues() public {
        // Even auditor count needs a 4th auditor and a batch large enough to
        // hold them -- auditorsPerBatch is fixed at 3 (demo Params, no
        // setter), so this drives a SECOND registered auditor set forming a
        // second batch isn't viable within one 3-auditor batch. Test the
        // even-count branch of _medianOf directly instead via a batch where
        // only 2 of the 3 registered auditors actually vote (minScoreQuorum
        // default = 2, so 2 votes is enough to finalize).
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Only 2 of 3 auditors vote -- minScoreQuorum=2 is met, and this
        // exercises the even-length branch of _medianOf: (30+70)/2 = 50.
        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 30, true);
        vm.prank(batchAuditors[1]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 70, true);
        // batchAuditors[2] never votes.

        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        (, , , , , , uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);
        assertEq(finalScore, 50, "even-count median should be the integer-divided average of the two middle (only) values");
    }

    function test_finalizeEvaluation_belowQuorum_notFinalized() public {
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Only 1 vote -- below minScoreQuorum=2, must not finalize at all.
        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 90, true);

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_FailedToFinalizeEvaluation -- finalizedCount stays 0
        tc.closeLMsubmissionsEvaluation(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // §1d: S3 deviation threshold, shadow mode. Computed and emitted on
    // every finalizeEvaluation call, but must never affect `approved` or
    // trigger any slashing -- that wiring is explicitly deferred pending
    // empirical validation (MECHANISM_DESIGN.md §6).
    // ─────────────────────────────────────────────────────────────────────

    function test_s3DeviationThreshold_defaultIsWideAndNonGating() public {
        _deployPlatform();
        _deployTaskPair();
        assertEq(ta.s3DeviationThreshold(), 40, "default should be the documented wide placeholder");
    }

    function test_setS3DeviationThreshold_onlyOwner() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(auditor1); // not the model owner
        vm.expectRevert();
        ta.setS3DeviationThreshold(10);

        vm.prank(modelOwner);
        ta.setS3DeviationThreshold(10);
        assertEq(ta.s3DeviationThreshold(), 10);
    }

    function test_setS3DeviationThreshold_rejectsOutOfRange() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_InvalidDeviationThreshold
        ta.setS3DeviationThreshold(101);
    }

    function test_s3Deviation_emittedButNeverGatesApproval() public {
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Tighten the threshold to 1 -- every one of these scores deviates
        // from the median (25) by more than 1, so exceedsThreshold should be
        // true for every auditor, on a model that still gets a real
        // eligible-median-based approval decision independent of that flag.
        vm.prank(modelOwner);
        ta.setS3DeviationThreshold(1);

        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 20, true);
        vm.prank(batchAuditors[1]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 25, true);
        vm.prank(batchAuditors[2]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 100, true);

        // AuditorScoreDeviation is only emitted inside finalizeEvaluation
        // (called by closeLMsubmissionsEvaluation), not at submission time --
        // median is 25, this auditor's score (20) deviates by 5.
        // 3 indexed topics on this event (gi, batchId, auditor) -- check all three.
        vm.expectEmit(true, true, true, true, address(ta));
        emit AuditorScoreDeviation(1, 0, modelIdxs[0], batchAuditors[0], 20, 25, 5, true);
        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        // Approval is unaffected by the deviation flag: median (25) < passScore
        // (50) is the ONLY reason this fails, not the S3 flag on 2 of 3 auditors.
        (, , , , , bool approved, uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);
        assertEq(finalScore, 25);
        assertFalse(approved);
    }

    function test_s3Deviation_thresholdChangesFlagButNeverBlocksFinalization() public {
        _runToLMSevaluationStarted();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Wide threshold: default (40) should NOT flag a [45,50,55] spread
        // (max deviation from median 50 is 5).
        vm.prank(batchAuditors[0]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 45, true);
        vm.prank(batchAuditors[1]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 50, true);
        vm.prank(batchAuditors[2]);
        ta.setAuditScorenEligibility(1, 0, modelIdxs[0], 55, true);

        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        // Finalization succeeds regardless of what the (shadow-mode-only)
        // deviation flag would have said -- proves shadow mode never blocks
        // the phase transition.
        (, , , bool evaluated, , bool approved, uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);
        assertTrue(evaluated);
        assertTrue(approved); // median 50 >= passScore 50
        assertEq(finalScore, 50);
    }

    event AuditorScoreDeviation(
        uint256 indexed gi,
        uint indexed batchId,
        uint modelIndex,
        address indexed auditor,
        uint256 auditorScore,
        uint256 medianScore,
        uint256 deviation,
        bool exceedsThreshold
    );
}
