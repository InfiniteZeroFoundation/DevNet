// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Tests for the dispute-resolution scaffold (task_210726_6 Part 4c, issue #38,
// S4: invalid aggregation via recomputation). Covers bond custody, the dispute
// window, upheld-vs-rejected settlement, fresh-subgroup reassignment (with
// exclusion of the accused batch's original aggregators), and pull-payment
// bond claims.
// Run: forge test --match-contract DisputeResolutionTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";

contract DisputeResolutionTest is Test {
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
    address challenger = makeAddr("challenger");

    address auditor1 = makeAddr("auditor1");
    address auditor2 = makeAddr("auditor2");
    address auditor3 = makeAddr("auditor3");
    address client1 = makeAddr("client1");
    address client2 = makeAddr("client2");
    address client3 = makeAddr("client3");

    bytes32 constant WINNING_CID = bytes32(uint256(0xC1D));

    // Commit-then-reveal (task_210726_6 §2a, PR #63) replaced the old
    // single-shot setAuditScorenEligibility this file was written against.
    // Fixed salt is fine here -- these tests don't exercise salt secrecy,
    // only driving the GI far enough to reach T1 finalization.
    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));

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

    function _fundDinBalance(address who, uint256 dinAmount) internal {
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded + 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        vm.startPrank(who);
        token.approve(address(tc), type(uint256).max);
        token.approve(address(ta), type(uint256).max);
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
        tc.setDinToken(address(token));
        ta.setDinToken(address(token));
        vm.stopPrank();

        // task_210726_6 §3: startGI reverts with TC_GIRewardPoolNotFunded
        // unless DINTaskAuditor.depositRewards(_GI, ...) has already been
        // called for that GI -- same sequence AuditorCommitReveal.t.sol and
        // ScoringValidation.t.sol use.
        _fundDinBalance(modelOwner, 1 ether);
        vm.startPrank(modelOwner);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    /// @dev Registers `numAggregators` aggregators (>= 3), runs a full GI
    ///      through T1 finalization with all assigned T1 aggregators voting
    ///      the same CID, and returns with GIstate == T1AggregationDone.
    ///      Registering more than 3 aggregators leaves an excludable pool for
    ///      the fresh-subgroup tests.
    function _runToT1Finalized(uint256 numAggregators) internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);

        address[] memory aggs = new address[](numAggregators);
        for (uint i = 0; i < numAggregators; i++) {
            aggs[i] = makeAddr(string(abi.encodePacked("agg", i)));
            _fundAndStake(aggs[i]);
        }

        vm.prank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        for (uint i = 0; i < numAggregators; i++) {
            vm.prank(aggs[i]);
            tc.registerDINaggregator(1);
        }

        vm.startPrank(modelOwner);
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

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta
            .getAuditorsBatch(1, 0);
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                bytes32 commitHash = keccak256(
                    abi.encodePacked(uint256(100), true, TEST_SALT)
                );
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

        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        for (uint i = 0; i < t1aggs.length; i++) {
            vm.prank(t1aggs[i]);
            tc.submitT1Aggregation(1, 0, WINNING_CID);
        }

        vm.prank(modelOwner);
        tc.finalizeT1Aggregation(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Setters
    // ─────────────────────────────────────────────────────────────────────

    function test_setDinToken_onlyOwner() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(challenger);
        vm.expectRevert();
        tc.setDinToken(address(token));
    }

    function test_setDinToken_rejectsZeroAddress() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_InvalidAddress
        tc.setDinToken(address(0));
    }

    function test_setDisputeParams_onlyOwner() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(challenger);
        vm.expectRevert();
        tc.setDisputeParams(50 ether, 2 days);
    }

    function test_setDisputeParams_rejectsZeroValues() public {
        _deployPlatform();
        _deployTaskPair();

        vm.startPrank(modelOwner);
        vm.expectRevert(); // TC_InvalidDisputeParams
        tc.setDisputeParams(0, 2 days);

        vm.expectRevert(); // TC_InvalidDisputeParams
        tc.setDisputeParams(50 ether, 0);
        vm.stopPrank();
    }

    function test_setDisputeParams_updatesValues() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        tc.setDisputeParams(50 ether, 2 days);

        assertEq(tc.disputeBond(), 50 ether);
        assertEq(tc.disputeWindow(), 2 days);
    }

    function test_setTreasuryAddress_rejectsZeroAddress() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_InvalidAddress
        tc.setTreasuryAddress(address(0));
    }

    // ─────────────────────────────────────────────────────────────────────
    // openDispute
    // ─────────────────────────────────────────────────────────────────────

    function test_openDispute_happyPath_pullsBondAndRecordsChallenger() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        uint256 balanceBefore = token.balanceOf(challenger);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        (
            address disputeChallenger,
            uint256 bond,
            uint64 openedAt,
            bool resolved,
            bool upheld
        ) = tc.disputes(1, DINTaskCoordinator.TierKind.Tier1, 0);

        assertEq(disputeChallenger, challenger);
        assertEq(bond, tc.disputeBond());
        assertEq(openedAt, block.timestamp);
        assertFalse(resolved);
        assertFalse(upheld);
        assertEq(token.balanceOf(challenger), balanceBefore - tc.disputeBond());
        assertEq(token.balanceOf(address(tc)), tc.disputeBond());
    }

    function test_openDispute_revertsIfBatchNotFinalized() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        vm.expectRevert(); // TC_InvalidBatch: no batch 1 exists
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 1);
    }

    function test_openDispute_revertsAfterWindowCloses() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.warp(block.timestamp + tc.disputeWindow() + 1);

        vm.prank(challenger);
        vm.expectRevert(); // TC_DisputeWindowClosed
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
    }

    function test_openDispute_revertsIfAlreadyOpen() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        address secondChallenger = makeAddr("secondChallenger");
        _fundAndStake(secondChallenger);
        _fundDinBalance(secondChallenger, 1_000 ether);

        vm.prank(secondChallenger);
        vm.expectRevert(); // TC_DisputeAlreadyOpen
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
    }

    function test_openDispute_revertsIfCallerNotActiveValidator() public {
        _runToT1Finalized(3);
        _fundDinBalance(challenger, 1_000 ether); // funded but never staked

        vm.prank(challenger);
        vm.expectRevert(); // TC_AggregatorNotActive
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
    }

    // ─────────────────────────────────────────────────────────────────────
    // resolveDispute
    // ─────────────────────────────────────────────────────────────────────

    function test_resolveDispute_upheld_creditsBondClaimableAndAssignsFreshSubgroup()
        public
    {
        _runToT1Finalized(6); // 3 in the disputed batch, 3 excludable
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        assertEq(tc.disputeBondClaimable(challenger), tc.disputeBond());

        (, address[] memory originalAggs, , , ) = tc.getTier1Batch(1, 0);
        for (uint i = 0; i < originalAggs.length; i++) {
            assertFalse(
                _addrInArray(originalAggs[i], _freshSubgroupOf(1, 0)),
                "fresh subgroup must exclude the accused batch's aggregators"
            );
        }
        assertEq(_freshSubgroupOf(1, 0).length, 3); // T1_AGGREGATORS_PER_BATCH
    }

    function test_resolveDispute_upheld_revertsIfNotEnoughEligibleAggregators()
        public
    {
        _runToT1Finalized(3); // exactly the accused batch, nobody left to reassign
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_NotEnoughValidators
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);
    }

    function test_resolveDispute_rejected_forfeitsBondToTreasuryAccrued() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        assertEq(tc.treasuryAccrued(), tc.disputeBond());
        assertEq(tc.disputeBondClaimable(challenger), 0);
    }

    function test_resolveDispute_onlyOwner() public {
        _runToT1Finalized(3);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(challenger);
        vm.expectRevert();
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);
    }

    function test_resolveDispute_cannotResolveTwice() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.startPrank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        vm.expectRevert(); // TC_DisputeAlreadyResolved
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);
        vm.stopPrank();
    }

    function test_resolveDispute_revertsIfNoDisputeOpen() public {
        _runToT1Finalized(3);

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_DisputeNotOpen
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);
    }

    // ─────────────────────────────────────────────────────────────────────
    // claimDisputeBond
    // ─────────────────────────────────────────────────────────────────────

    function test_claimDisputeBond_transfersAndZeroesBalance() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _fundDinBalance(challenger, 1_000 ether);

        vm.prank(challenger);
        tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
        uint256 balanceAfterOpen = token.balanceOf(challenger);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        vm.prank(challenger);
        tc.claimDisputeBond();

        assertEq(token.balanceOf(challenger), balanceAfterOpen + tc.disputeBond());
        assertEq(tc.disputeBondClaimable(challenger), 0);
    }

    function test_claimDisputeBond_zeroBalanceReverts() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(challenger);
        vm.expectRevert(); // TC_NoBondClaimable
        tc.claimDisputeBond();
    }

    // ─────────────────────────────────────────────────────────────────────
    // helpers
    // ─────────────────────────────────────────────────────────────────────

    function _freshSubgroupOf(
        uint _GI,
        uint batchId
    ) internal view returns (address[] memory) {
        // reEvaluationAssignees is a public mapping of dynamic arrays --
        // Solidity's auto-getter needs an index, so read length via a manual
        // loop bound instead: T1_AGGREGATORS_PER_BATCH is always the size
        // when the resolve call succeeded, so just probe indexes until revert.
        address[] memory out = new address[](3);
        for (uint i = 0; i < 3; i++) {
            out[i] = tc.reEvaluationAssignees(
                _GI,
                DINTaskCoordinator.TierKind.Tier1,
                batchId,
                i
            );
        }
        return out;
    }

    function _addrInArray(
        address needle,
        address[] memory haystack
    ) internal pure returns (bool) {
        for (uint i = 0; i < haystack.length; i++) {
            if (haystack[i] == needle) return true;
        }
        return false;
    }
}
