// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Regression coverage for the two verified defects found reviewing PR #146
// (feat/slashing-s1-s2-tiers): the S1/S6 (and S2/S6) double-fire over-slash,
// and the cross-model GI-collision underflow in DinValidatorStake's S5
// recidivism ring. Both were fixed as deviations while merging PR #146 into
// develop -- these tests pin the fixed behavior so it can't silently regress.
// Run: forge test --match-contract PR146SlashingRegressionTest -vv
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

contract PR146SlashingRegressionTest is Test {
    // ─────────────────────────────────────────────────────────────────────
    // Shared platform + task fixture (same deployment order as
    // SecurityFindings.t.sol / RewardEngine.t.sol).
    // ─────────────────────────────────────────────────────────────────────

    DinToken token;
    DinCoordinator coordinator;
    DinValidatorStake stake;
    DINModelRegistry registry;
    DinTreasury treasury;
    DinFeeRouter feeRouter;
    DINTaskCoordinator tc;
    DINTaskAuditor ta;

    address admin = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));

    function _deployPlatform() internal {
        vm.startPrank(admin);
        treasury = DinTreasury(payable(address(new TransparentUpgradeableProxy(
            address(new DinTreasury()), admin, abi.encodeCall(DinTreasury.initialize, ())
        ))));

        token = DinToken(address(new TransparentUpgradeableProxy(
            address(new DinToken()), admin, abi.encodeCall(DinToken.initialize, ())
        )));
        coordinator = DinCoordinator(address(new TransparentUpgradeableProxy(
            address(new DinCoordinator()), admin, abi.encodeCall(DinCoordinator.initialize, (address(token)))
        )));
        token.setCoordinator(address(coordinator));

        feeRouter = DinFeeRouter(address(new TransparentUpgradeableProxy(
            address(new DinFeeRouter()), admin,
            abi.encodeCall(DinFeeRouter.initialize, (address(token), address(treasury)))
        )));
        coordinator.setFeeRouter(address(feeRouter));
        feeRouter.addFeeSource(address(coordinator));

        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(new DinValidatorStake()), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));

        registry = DINModelRegistry(address(new TransparentUpgradeableProxy(
            address(new DINModelRegistry()), admin,
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

        // DIN-Representative authorises both as slashers.
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
        stake.stake(10 ether); // MIN_STAKE
        vm.stopPrank();
    }

    // ─────────────────────────────────────────────────────────────────────
    // Finding 1 (S1/S2 x S6 double-fire): a single missed-vote/missed-
    // submission event must be penalised once (via slashPartial, S1/S2 +
    // S5 recidivism tracking), never twice via a concurrent S6
    // recordNoParticipation call on the same branch. Before the fix, a
    // single such event could slash well over 100% of MIN_STAKE.
    //
    // Setup: 6 auditors register (auditorsPerBatch=3 -> 2 batches), 6
    // clients submit models. Only batch 0's 3 auditors vote; batch 1's 3
    // auditors miss their vote entirely.
    // ─────────────────────────────────────────────────────────────────────

    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");

    function _registerNAuditors(uint n) internal returns (address[] memory auditors) {
        auditors = new address[](n);
        for (uint i = 0; i < n; i++) {
            address a = makeAddr(string.concat("regAuditor", vm.toString(i)));
            auditors[i] = a;
            _fundAndStake(a);
            vm.prank(a);
            ta.registerDINAuditor(1);
        }
    }

    function _submitNModels(uint n) internal {
        for (uint i = 0; i < n; i++) {
            address c = makeAddr(string.concat("regClient", vm.toString(i)));
            vm.prank(c);
            ta.submitLocalModel(bytes32(uint256(9000 + i)), 1);
        }
    }

    function _runToSlashAuditors(uint n) internal returns (address[] memory auditors) {
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

        // Only batch 0 votes -- batch 1's auditors miss their vote entirely.
        (, address[] memory batch0Auditors, uint[] memory batch0Models, ) = ta.getAuditorsBatch(1, 0);
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

        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();

        // T1: agg3 misses its submission (S2 liveness fault). agg1/agg2
        // agree, giving submissionCount=2 >= T1_AGGREGATORS_PER_BATCH/2+1=2,
        // so finalization still succeeds.
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        bytes32 realCID = bytes32(uint256(0xC1D));
        for (uint i = 0; i < t1aggs.length; i++) {
            if (t1aggs[i] == agg3) continue;
            vm.prank(t1aggs[i]);
            tc.submitT1Aggregation(1, 0, realCID);
        }

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        tc.finalizeT2Aggregation(1); // trivial: 0 T2 batches at exactly 3 aggregators
        vm.stopPrank();
    }

    function test_S1_missedVote_doesNotDoubleFireS6() public {
        address[] memory auditors = _runToSlashAuditors(6);

        // batch 1 = auditors[3..5], all miss their vote.
        address missedAuditor = auditors[3];
        uint256 stakeBefore = stake.getStake(missedAuditor);

        vm.prank(modelOwner);
        tc.slashAuditors(1);

        uint256 expectedS1Amount = (stake.MIN_STAKE() * ta.s1SlashFractionBps()) / 10_000;
        uint256 stakeAfter = stake.getStake(missedAuditor);

        // Regression guard: exactly the S1 partial fraction was slashed for
        // this single missed-vote event -- not S1 + a concurrent S6 slash.
        assertEq(
            stakeBefore - stakeAfter,
            expectedS1Amount,
            "missed vote should slash exactly the S1 fraction, not more"
        );
        // Regression guard: S6's counter was never touched by this branch.
        assertEq(
            stake.s6NoParticipationCount(missedAuditor),
            0,
            "S1 missed-vote path must not also fire S6 recordNoParticipation"
        );
    }

    function test_S2_missedSubmission_doesNotDoubleFireS6() public {
        _runToSlashAuditors(6);

        uint256 stakeBefore = stake.getStake(agg3);

        vm.startPrank(modelOwner);
        tc.slashAuditors(1);
        tc.slashAggregators(1);
        vm.stopPrank();

        uint256 expectedS2Amount = (stake.MIN_STAKE() * tc.s2SlashFractionBps()) / 10_000;
        uint256 stakeAfter = stake.getStake(agg3);

        assertEq(
            stakeBefore - stakeAfter,
            expectedS2Amount,
            "missed T1 submission should slash exactly the S2 fraction, not more"
        );
        assertEq(
            stake.s6NoParticipationCount(agg3),
            0,
            "S2 missed-submission path must not also fire S6 recordNoParticipation"
        );
    }

    // ─────────────────────────────────────────────────────────────────────
    // Finding 2 (cross-model GI-collision underflow): DinValidatorStake's
    // S5 recidivism ring is namespaced per calling slasher contract
    // (validator -> caller -> GI[]), not per validator alone. Before the
    // fix, a validator active under two different task contracts (whose
    // GI counters are independent and can interleave in any order) would
    // push non-monotonic values into one shared ring, and the
    // ascending-order trim in _trimAndRecordPartialSlash would underflow
    // and revert. `ta` and `tc` here are two distinct real registered
    // slasher contracts from the same fixture -- a direct stand-in for
    // "two different models' task contracts".
    // ─────────────────────────────────────────────────────────────────────

    function test_crossModelGICollision_slashPartialDoesNotUnderflow() public {
        _deployPlatform();
        _deployTaskPair();

        address validator = makeAddr("crossModelValidator");
        _fundAndStake(validator);
        // Plenty of headroom so partial slashes never get capped by
        // insufficient stake, which would mask the underflow this test
        // is checking for.
        vm.startPrank(validator);
        token.approve(address(stake), type(uint256).max);
        stake.stake(990 ether);
        vm.stopPrank();

        uint256 partialAmt = (stake.MIN_STAKE() * 1000) / 10_000; // 10%, well under S5 threshold

        // Model A (`ta`, acting as its own model's task contract) records a
        // high GI index first.
        vm.prank(address(ta));
        stake.slashPartial(validator, partialAmt, "AUD_NO_VOTE", 50);

        // Model B (`tc`, a completely different task contract with its own
        // independent, lower GI counter) then records a LOWER GI index for
        // the same validator. Before the fix this underflowed
        // (giIndex=2 - ring[0]=50) and reverted; after the fix, `tc`'s ring
        // is independent of `ta`'s, so this succeeds.
        vm.prank(address(tc));
        stake.slashPartial(validator, partialAmt, "AGG_T1_NO_SUBMISSION", 2);

        uint256[] memory ringA = stake.getPartialSlashGIs(validator, address(ta));
        uint256[] memory ringB = stake.getPartialSlashGIs(validator, address(tc));
        assertEq(ringA.length, 1, "ta's ring holds only its own entry");
        assertEq(ringA[0], 50, "ta's ring entry unaffected by tc's lower GI");
        assertEq(ringB.length, 1, "tc's ring holds only its own entry");
        assertEq(ringB[0], 2, "tc's ring entry recorded independently");

        // Each ring can keep accumulating in its own ascending order without
        // interference from the other's (unrelated) GI sequence.
        vm.prank(address(ta));
        stake.slashPartial(validator, partialAmt, "AUD_NO_VOTE", 51);
        vm.prank(address(tc));
        stake.slashPartial(validator, partialAmt, "AGG_T1_NO_SUBMISSION", 3);

        assertEq(stake.getPartialSlashGIs(validator, address(ta)).length, 2);
        assertEq(stake.getPartialSlashGIs(validator, address(tc)).length, 2);
    }
}
