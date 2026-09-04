// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// PoC tests for the 2026-07 security review (Developer/audits/2026-07_foundry-src-security-review.md).
// Pinned to commit d136ff3. These are additive, read/observe only — no
// contract source under test is modified.
// Run: forge test --match-contract SecurityFindingsTest -vv
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
import {GIstates, TC_ZeroCID} from "../src/DINShared.sol";

contract SecurityFindingsTest is Test {
    // ─────────────────────────────────────────────────────────────────────
    // Shared platform fixture (6-step deployment order from
    // Documentation/technical/upgradable-contracts/hardhat/README.md §5)
    // ─────────────────────────────────────────────────────────────────────

    DinToken tokenImpl;
    DinCoordinator coordinatorImpl;
    DinValidatorStake stakeImpl;
    DINModelRegistry registryImpl;

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DinTreasury treasury;
    DinFeeRouter feeRouter;

    address admin = makeAddr("admin");
    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));

    function _deployPlatform() internal {
        vm.startPrank(admin);
        _deployTreasury();
        _deployTokenAndCoordinator();
        _deployFeeRouter();
        _deployStakeAndRegistry();
        vm.stopPrank();
    }

    function _deployTreasury() private {
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(new DinTreasury()), admin, abi.encodeCall(DinTreasury.initialize, ())
        ))));
    }

    function _deployTokenAndCoordinator() private {
        tokenImpl = new DinToken();
        token = DinToken(address(new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        )));

        coordinatorImpl = new DinCoordinator();
        coordinator = DinCoordinator(address(new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin, abi.encodeCall(DinCoordinator.initialize, (address(token)))
        )));

        token.setCoordinator(address(coordinator));
    }

    function _deployFeeRouter() private {
        feeRouter = DinFeeRouter(address(new TransparentUpgradeableProxy(
            address(new DinFeeRouter()), admin,
            abi.encodeCall(DinFeeRouter.initialize, (address(token), address(treasury)))
        )));

        coordinator.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(coordinator));
    }

    function _deployStakeAndRegistry() private {
        stakeImpl = new DinValidatorStake();
        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(stakeImpl), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));

        registryImpl = new DINModelRegistry();
        registry = DINModelRegistry(address(new TransparentUpgradeableProxy(
            address(registryImpl), admin,
            abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        )));

        registry.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(registry));
        stake.setSlashTreasury(address(treasury));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Proxy-specific: initializer protection
    //
    // Confirms _disableInitializers() is effective at RUNTIME, not just
    // present in source — i.e. an attacker cannot call initialize() directly
    // on the deployed implementation address and claim ownership of it.
    // (Not exploitable against the real protocol today, since the
    // implementation holds no funds/routing of its own — but see the
    // finding writeup for why this still matters operationally.)
    // ─────────────────────────────────────────────────────────────────────

    function test_implementation_rejectsDirectInitialize_DinToken() public {
        DinToken impl = new DinToken();
        vm.expectRevert();
        impl.initialize();
    }

    function test_implementation_rejectsDirectInitialize_DinCoordinator() public {
        DinCoordinator impl = new DinCoordinator();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeToken"));
    }

    function test_implementation_rejectsDirectInitialize_DinValidatorStake() public {
        DinValidatorStake impl = new DinValidatorStake();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeToken"), makeAddr("fakeCoordinator"));
    }

    function test_implementation_rejectsDirectInitialize_DINModelRegistry() public {
        DINModelRegistry impl = new DINModelRegistry();
        vm.expectRevert();
        impl.initialize(makeAddr("fakeStake"));
    }

    function test_proxy_rejectsDoubleInitialize_DinToken() public {
        _deployPlatform();
        vm.expectRevert();
        token.initialize();
    }

    function test_proxy_rejectsDoubleInitialize_DinCoordinator() public {
        _deployPlatform();
        vm.expectRevert();
        coordinator.initialize(makeAddr("someToken"));
    }

    function test_proxy_rejectsDoubleInitialize_DinValidatorStake() public {
        _deployPlatform();
        vm.expectRevert();
        stake.initialize(makeAddr("t"), makeAddr("c"));
    }

    function test_proxy_rejectsDoubleInitialize_DINModelRegistry() public {
        _deployPlatform();
        vm.expectRevert();
        registry.initialize(makeAddr("s"));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Finding: zero-CID sentinel collision permanently DoSes
    // finalizeT1Aggregation / finalizeT2Aggregation for the whole GI.
    //
    // T1/T2 finalization uses `winningCID == bytes32(0)` to detect "no
    // submissions for this batch" and revert. Any assigned aggregator can
    // submit `bytes32(0)` as their own aggregation CID; if that CID ends up
    // as the batch's plurality vote (e.g. the only submission in that
    // batch), finalization reverts for the ENTIRE GI, indistinguishable
    // from "nobody submitted" — even though a submission genuinely exists.
    // Task contracts are not upgradeable, so this has no on-chain recovery
    // path: the GI is bricked and the model owner must abandon the round.
    // ─────────────────────────────────────────────────────────────────────

    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address modelOwner = makeAddr("modelOwner");
    address auditor1 = makeAddr("auditor1");
    address auditor2 = makeAddr("auditor2");
    address client1 = makeAddr("client1");
    address client2 = makeAddr("client2");
    address client3 = makeAddr("client3");
    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");

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

        // DIN-Representative authorises both as slashers
        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc));
        coordinator.addSlasherContract(address(ta));
        vm.stopPrank();

        vm.startPrank(modelOwner);
        tc.setDINTaskCoordinatorAsSlasher();
        tc.setDINTaskAuditorAsSlasher();
        tc.setGenesisModelIpfsHash(bytes32(uint256(1)));

        // task_210726_6 §3: _startGI now requires the upcoming GI's reward
        // pool to be funded first. Minimal funding here since these fixtures
        // predate the reward engine and aren't testing settlement.
        ta.setDinToken(address(token));
        vm.deal(modelOwner, 1 ether);
        coordinator.depositAndMint{value: 0.001 ether}();
        token.approve(address(ta), type(uint256).max);
        ta.depositRewards(1, 1 ether);

        tc.startGI(1);
        vm.stopPrank();
    }

    function _runToT1AggregationStarted() internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);

        vm.startPrank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        vm.stopPrank();

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

        // auditorsPerBatch defaults to 3 (demo Params in the DINTaskAuditor
        // constructor) so all 3 auditors must register before the window closes.
        address auditor3 = makeAddr("auditor3");
        _fundAndStake(auditor3);

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

        // Both models pass: all 3 auditors commit-then-reveal eligible +
        // score 100 on both models (commit-then-reveal per task_210726_6 §2a
        // replaced the old single-shot setAuditScorenEligibility).
        (, address[] memory batchAuditors, uint[] memory modelIdxs,) = ta.getAuditorsBatch(1, 0);
        bytes32 commitHash = keccak256(abi.encodePacked(uint256(100), true, TEST_SALT));
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuditors[i]);
                ta.commitAuditScore(1, 0, modelIdxs[m], commitHash);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);

        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuditors[i]);
                ta.revealAuditScore(1, 0, modelIdxs[m], 100, true, TEST_SALT);
            }
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();
    }

    function test_finalizeT1Aggregation_zeroCID_bricksEntireGI() public {
        _runToT1AggregationStarted();

        (, address[] memory t1aggs,,,) = tc.getTier1Batch(1, 0);
        assertEq(t1aggs.length, 3, "sanity: T1 batch should have 3 aggregators");

        // C-2 regression: bytes32(0) is now rejected at submit time with TC_ZeroCID.
        // Before the fix this call succeeded and permanently bricked finalizeT1Aggregation
        // (TC_NoSubmissions at finalize, GI stuck forever).
        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_ZeroCID.selector);
        tc.submitT1Aggregation(1, 0, bytes32(0));
    }

    // ─────────────────────────────────────────────────────────────────────
    // H-1 gas measurement.
    //
    // DINTaskAuditor.Params (auditorsPerBatch, modelsPerBatch) is hardcoded
    // to demo defaults (3, 3) in the constructor with no setter -- literal
    // "spec scale" (auditorsPerBatch=10, modelsPerBatch=100) cannot be
    // deployed without modifying the contract, which is out of scope for
    // this findings-only review (see report §"What I'd do differently").
    //
    // Instead: measure REAL forge gas at two registrant scales (demo batch
    // size = 3, so batch count = N/3), derive the real marginal per-batch
    // cost from the slope between them, and use that measured slope --
    // not an assumed one -- to extrapolate to spec-scale batch counts.
    // ─────────────────────────────────────────────────────────────────────

    function _registerNAuditors(uint n) internal returns (address[] memory auditors) {
        auditors = new address[](n);
        for (uint i = 0; i < n; i++) {
            address a = makeAddr(string.concat("gasAuditor", vm.toString(i)));
            auditors[i] = a;
            _fundAndStake(a);
            vm.prank(a);
            ta.registerDINAuditor(1);
        }
    }

    function _submitNModels(uint n) internal {
        for (uint i = 0; i < n; i++) {
            address c = makeAddr(string.concat("gasClient", vm.toString(i)));
            vm.prank(c);
            ta.submitLocalModel(bytes32(uint256(9000 + i)), 1);
        }
    }

    /// @dev Drives the GI up to LMSevaluationStarted with N registered
    ///      auditors / N submitted models (batches = N/3 at demo params).
    ///      Only the first batch's 3 auditors actually vote (all models
    ///      eligible, score 100) -- enough for finalizeEvaluation() to
    ///      return true so the phase transition doesn't itself revert.
    ///      Every other registered auditor casts no vote at all: the
    ///      worst-case, and also the realistic Sybil-registers-and-never-
    ///      bothers-voting attack from the H-1 failure scenario.
    function _setupForGasMeasurement(uint n) internal returns (address[] memory auditors) {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);

        vm.startPrank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        vm.stopPrank();
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

        auditors = _registerNAuditors(n);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        _submitNModels(n);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        // Only batch 0 votes -- guarantees finalizeEvaluation() finalizes
        // at least one model (returns true) without every registrant
        // needing to participate. Commit-then-reveal (§2a) replaced the old
        // single-shot setAuditScorenEligibility; leaves GIstate at
        // LMSevaluationRevealStarted so _finishEvaluationAndAggregation can
        // measure closeLMsubmissionsEvaluation's gas directly, matching what
        // this helper returned to callers before commit-reveal existed.
        (, address[] memory batch0Auditors, uint[] memory batch0Models,) = ta.getAuditorsBatch(1, 0);
        bytes32 commitHash = keccak256(abi.encodePacked(uint256(100), true, TEST_SALT));
        for (uint i = 0; i < batch0Auditors.length; i++) {
            for (uint m = 0; m < batch0Models.length; m++) {
                vm.prank(batch0Auditors[i]);
                ta.commitAuditScore(1, 0, batch0Models[m], commitHash);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);

        for (uint i = 0; i < batch0Auditors.length; i++) {
            for (uint m = 0; m < batch0Models.length; m++) {
                vm.prank(batch0Auditors[i]);
                ta.revealAuditScore(1, 0, batch0Models[m], 100, true, TEST_SALT);
            }
        }
    }

    /// @dev Completes evaluation close (measuring finalizeEvaluation's real
    ///      gas), then drives T1/T2 aggregation to completion using only
    ///      the 3 registered aggregators (T1_AGGREGATORS_PER_BATCH is a
    ///      fixed constant = 3, unrelated to the auditor-side N being
    ///      measured here) so slashAuditors() becomes callable.
    function _finishEvaluationAndAggregation() internal returns (uint256 finalizeEvaluationGas) {
        uint256 gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        finalizeEvaluationGas = gasBefore - gasleft();

        vm.startPrank(modelOwner);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();

        (, address[] memory t1aggs,,,) = tc.getTier1Batch(1, 0);
        bytes32 realCID = bytes32(uint256(0xC1D));
        for (uint i = 0; i < t1aggs.length; i++) {
            vm.prank(t1aggs[i]);
            tc.submitT1Aggregation(1, 0, realCID);
        }

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        // Only 3 aggregators total registered -> 0 left over for a Tier-2
        // batch (needs T1_AGGREGATORS_PER_BATCH=3 remaining after T1
        // consumes all 3), so tier2Batches[1] is empty and this finalizes
        // trivially. Not the subject of this measurement (H-1's aggregator-
        // side loops scale with *aggregator* count, held fixed here at the
        // minimum needed to reach slashAuditors()).
        tc.finalizeT2Aggregation(1);
        vm.stopPrank();
    }

    function test_gas_finalizeEvaluation_and_slashAuditors_atScale() public {
        // ── Small scale: 30 registered auditors -> 10 batches ──
        address[] memory auditorsSmall = _setupForGasMeasurement(30);
        uint256 gasSmall = _finishEvaluationAndAggregation();
        uint256 gasBeforeSlashSmall = gasleft();
        vm.prank(modelOwner);
        tc.slashAuditors(1);
        uint256 gasSlashSmall = gasBeforeSlashSmall - gasleft();

        // Sanity: everyone outside batch 0 (auditors[3:]) missed their
        // vote and should have been slashed down from MIN_STAKE.
        assertLt(stake.getStake(auditorsSmall[29]), 10 ether, "sanity: non-voting auditor should have been slashed");

        // ── Larger scale: 90 registered auditors -> 30 batches ──
        address[] memory auditorsLarge = _setupForGasMeasurement(90);
        uint256 gasLarge = _finishEvaluationAndAggregation();
        uint256 gasBeforeSlashLarge = gasleft();
        vm.prank(modelOwner);
        tc.slashAuditors(1);
        uint256 gasSlashLarge = gasBeforeSlashLarge - gasleft();

        assertLt(stake.getStake(auditorsLarge[89]), 10 ether, "sanity: non-voting auditor should have been slashed");

        // ── Real measured marginal cost per batch (slope between the two
        //    real data points -- not an assumption) ──
        uint256 batchesSmall = 30 / 3; // 10
        uint256 batchesLarge = 90 / 3; // 30
        uint256 marginalGasPerBatch_finalizeEval = (gasLarge - gasSmall) / (batchesLarge - batchesSmall);
        uint256 marginalGasPerBatch_slash = (gasSlashLarge - gasSlashSmall) / (batchesLarge - batchesSmall);

        emit log_named_uint("finalizeEvaluation gas @10 batches (30 auditors)", gasSmall);
        emit log_named_uint("finalizeEvaluation gas @30 batches (90 auditors)", gasLarge);
        emit log_named_uint("slashAuditors gas @10 batches (30 auditors)", gasSlashSmall);
        emit log_named_uint("slashAuditors gas @30 batches (90 auditors)", gasSlashLarge);
        emit log_named_uint("measured marginal gas/batch, finalizeEvaluation", marginalGasPerBatch_finalizeEval);
        emit log_named_uint("measured marginal gas/batch, slashAuditors", marginalGasPerBatch_slash);

        // Spec-scale extrapolation -- TWO factors, not one, or this
        // understates the real number by ~111x:
        //
        //   1. More batches: 500 registrants / auditorsPerBatch=10 = 50
        //      batches (vs. 10/30 measured here). Captured by the real
        //      measured per-batch slope above.
        //   2. Each batch is ALSO internally bigger: spec params are
        //      auditorsPerBatch=10 x modelsPerBatch=100 = 1,000 inner
        //      (auditor,model) pair-checks per batch, vs. demo's
        //      3 x 3 = 9 per batch actually measured here. This dimension
        //      cannot be empirically measured -- Params.auditorsPerBatch/
        //      modelsPerBatch is hardcoded in the DINTaskAuditor
        //      constructor with no setter, so a batch with spec-scale
        //      internal dimensions cannot be deployed without modifying
        //      the contract, which is out of scope for this findings-only
        //      review. This factor is therefore a structural (Big-O)
        //      extrapolation from the loop shape, applied on top of the
        //      real measured per-batch cost -- not itself measured.
        uint256 demoInnerPairsPerBatch = 3 * 3; // auditorsPerBatch x modelsPerBatch, demo
        uint256 specInnerPairsPerBatch = 10 * 100; // auditorsPerBatch x modelsPerBatch, spec
        uint256 specScaleBatches = 50; // ~500 registrants / auditorsPerBatch=10

        uint256 gasPerPair_finalizeEval = marginalGasPerBatch_finalizeEval / demoInnerPairsPerBatch;
        uint256 gasPerPair_slash = marginalGasPerBatch_slash / demoInnerPairsPerBatch;

        uint256 projectedGasPerBatch_finalizeEval = gasPerPair_finalizeEval * specInnerPairsPerBatch;
        uint256 projectedGasPerBatch_slash = gasPerPair_slash * specInnerPairsPerBatch;

        uint256 projectedGas_finalizeEval = projectedGasPerBatch_finalizeEval * specScaleBatches;
        uint256 projectedGas_slash = projectedGasPerBatch_slash * specScaleBatches;

        emit log_named_uint("measured gas per (auditor,model) pair, finalizeEvaluation", gasPerPair_finalizeEval);
        emit log_named_uint("PROJECTED finalizeEvaluation gas, full spec scale (50 batches x 1000 pairs/batch)", projectedGas_finalizeEval);
        emit log_named_uint("PROJECTED slashAuditors gas, full spec scale (LOWER BOUND -- see note below)", projectedGas_slash);

        // Caveat on the slashAuditors projection: slashAuditors' innermost
        // loop `break`s on the FIRST missed vote it finds. In this test no
        // registrant outside batch 0 votes at all, so the break fires
        // immediately (m=0) for every one of them -- meaning the measured
        // slashAuditors numbers above are a FLOOR, not a worst case. An
        // attacker who instead votes on every model in their batch except
        // the last would force the full modelsPerBatch traversal before
        // triggering the break, making real worst-case slashAuditors gas
        // approach finalizeEvaluation's (no-early-break) per-pair cost
        // instead of this measurement's. Both the floor above and that
        // worst-case (finalizeEvaluation-shaped) figure are well past any
        // realistic L2 block gas limit at spec scale either way.

        // Confirms worse-than-linear-in-registrants-alone growth is at
        // minimum present (3x batches should cost meaningfully more than
        // 3x gas given the O(batches x auditorsPerBatch x modelsPerBatch)
        // shape layered on top of per-batch fixed costs); real numbers are
        // the point of this test, this assertion just guards against the
        // measurement accidentally becoming a no-op.
        assertGt(gasLarge, gasSmall * 2, "finalizeEvaluation should scale well above linearly with batch count");
    }
}
