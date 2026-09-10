// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Contract-level tests for task_210726_6 Part 3 (reward engine, issue #41):
// giRewardPool, depositRewards, the _startGI funding precondition, RewardSplit,
// on-chain settlement at endGI, and pull-payment claimRewards.
// Run: forge test --match-contract RewardEngineTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {stdStorage, StdStorage} from "forge-std/StdStorage.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {GIstates} from "../src/DINShared.sol";

contract RewardEngineTest is Test {
    using stdStorage for StdStorage;

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
    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");
    address client1 = makeAddr("client1");
    address client2 = makeAddr("client2");
    address client3 = makeAddr("client3");

    // Deviation from PR #64 as submitted: #63 replaced the single-shot
    // setAuditScorenEligibility this file was written against with
    // commit-then-reveal (commitAuditScore/revealAuditScore), same as
    // ScoringValidation.t.sol/SecurityFindings.t.sol already needed.
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

    /// @dev Mints `dinAmount` DIN to `who` via the real ETH->DIN exchange
    ///      (not a test-only mint) and approves `ta` to pull it, so
    ///      depositRewards exercises the real safeTransferFrom path.
    function _fundDinBalance(address who, uint256 dinAmount) internal {
        // dinPerEth defaults to 1_000_000 * 1e18 -- back-solve the ETH needed.
        uint256 ethNeeded = (dinAmount * 1e18) / (1_000_000 * 1e18) + 1;
        vm.deal(who, ethNeeded + 1 ether);
        vm.prank(who);
        coordinator.depositAndMint{value: ethNeeded}();
        vm.prank(who);
        token.approve(address(ta), type(uint256).max);
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
        ta.setDinToken(address(token));
        vm.stopPrank();
    }

    /// @dev Drives an entire honest GI from a funded pool through to
    ///      GIstates.AggregatorsSlashed (one call away from endGI): 3
    ///      auditors, 3 aggregators, 3 clients, everyone honest (all
    ///      auditors score all three models 80/eligible, all aggregators
    ///      submit the same T1 CID). Leaves all three clients `approved`
    ///      with `finalMedianScore == 80`, and all 3 aggregators rewardable for
    ///      one finalized T1 batch (0 aggregators left for a T2 batch, same
    ///      as SecurityFindings.t.sol's fixture, at exactly 3 registered).
    function _runFullHonestGI(uint256 poolAmount) internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);
        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);

        _fundDinBalance(modelOwner, poolAmount);
        vm.prank(modelOwner);
        ta.depositRewards(1, poolAmount);

        vm.prank(modelOwner);
        tc.startGI(1);

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
        // T1_MODELS_PER_BATCH is a constant 3 on DINTaskCoordinator --
        // autoCreateTier1AndTier2 needs at least 3 *approved* models to form
        // a T1 batch at all, so 2 clients isn't enough here even though
        // MIN_MODELS_PER_BATCH (the auditor-batch-formation floor) is 2.
        ta.submitLocalModel(bytes32(uint256(300)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                bytes32 commitHash = keccak256(
                    abi.encodePacked(uint256(80), true, TEST_SALT)
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
                ta.revealAuditScore(1, 0, modelIdxs[m], 80, true, TEST_SALT);
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
        vm.stopPrank();
    }

    // ─────────────────────────────────────────────────────────────────────
    // Setters: access control + validation
    // ─────────────────────────────────────────────────────────────────────

    function test_setDinToken_onlyOwner() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(auditor1);
        vm.expectRevert();
        ta.setDinToken(address(token));
    }

    function test_setDinToken_rejectsZeroAddress() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_InvalidAddress
        ta.setDinToken(address(0));
    }

    function test_setRewardSplit_defaultMatches60_20_15_5Proposal() public {
        _deployPlatform();
        _deployTaskPair();

        (uint16 clientBps, uint16 auditorBps, uint16 aggregatorBps, uint16 treasuryBps) = ta.rewardSplit();
        assertEq(clientBps, 6000);
        assertEq(auditorBps, 2000);
        assertEq(aggregatorBps, 1500);
        assertEq(treasuryBps, 500);
    }

    function test_setRewardSplit_onlyOwner() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(auditor1);
        vm.expectRevert();
        ta.setRewardSplit(DINTaskAuditor.RewardSplit(5000, 3000, 1500, 500));
    }

    function test_setRewardSplit_mustSumToTenThousand() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_InvalidRewardSplit
        ta.setRewardSplit(DINTaskAuditor.RewardSplit(5000, 3000, 1500, 501)); // sums to 10001

        vm.prank(modelOwner);
        ta.setRewardSplit(DINTaskAuditor.RewardSplit(5000, 3000, 1500, 500)); // sums to exactly 10000, ok
        (uint16 clientBps, , , ) = ta.rewardSplit();
        assertEq(clientBps, 5000);
    }

    // ─────────────────────────────────────────────────────────────────────
    // depositRewards + the _startGI funding precondition
    // ─────────────────────────────────────────────────────────────────────

    function test_depositRewards_creditsGiRewardPool() public {
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(modelOwner, 1000 ether);

        vm.prank(modelOwner);
        ta.depositRewards(1, 1000 ether);

        assertEq(ta.giRewardPool(1), 1000 ether);
    }

    function test_depositRewards_zeroAmountReverts() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_AmountMustBePositive
        ta.depositRewards(1, 0);
    }

    function test_depositRewards_anyoneCanFundAnyGi() public {
        // Matches the "market-set pool" framing -- not restricted to the
        // model owner.
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(client1, 500 ether);

        vm.prank(client1);
        ta.depositRewards(1, 500 ether);

        assertEq(ta.giRewardPool(1), 500 ether);
    }

    function test_depositRewards_rejectsGiZero() public {
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(modelOwner, 1 ether);

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_InvalidRewardGI
        ta.depositRewards(0, 1 ether);
    }

    function test_depositRewards_allowsCurrentAndFutureGi() public {
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(modelOwner, 2 ether);

        // GI is 0 before the first startGI call -- both the immediate next
        // GI (1) and one further out (2) must be fundable in advance.
        vm.startPrank(modelOwner);
        ta.depositRewards(1, 1 ether);
        ta.depositRewards(2, 1 ether);
        vm.stopPrank();

        assertEq(ta.giRewardPool(1), 1 ether);
        assertEq(ta.giRewardPool(2), 1 ether);
    }

    function test_depositRewards_rejectsAGiThatHasAlreadyPassed() public {
        // Run GI 1 all the way through and start GI 2, so the coordinator's
        // GI counter has moved past 1 -- GI 1 can never be started again,
        // so a deposit tagged with gi=1 at this point could never be spent.
        _runFullHonestGI(1_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        _fundDinBalance(modelOwner, 1 ether);
        vm.prank(modelOwner);
        ta.depositRewards(2, 1 ether); // fund GI 2 so it can start
        vm.prank(modelOwner);
        tc.startGI(2);
        assertEq(tc.GI(), 2);

        _fundDinBalance(modelOwner, 1 ether);
        vm.prank(modelOwner);
        vm.expectRevert(); // TA_InvalidRewardGI
        ta.depositRewards(1, 1 ether);
    }

    function test_startGI_revertsWithoutFundedPool() public {
        _deployPlatform();
        _deployTaskPair();
        // No depositRewards call at all.

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_GIRewardPoolNotFunded
        tc.startGI(1);
    }

    function test_startGI_succeedsOnceFunded() public {
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(modelOwner, 1 ether);
        vm.prank(modelOwner);
        ta.depositRewards(1, 1 ether);

        vm.prank(modelOwner);
        tc.startGI(1);

        assertEq(uint256(tc.GIstate()), uint256(GIstates.GIstarted));
    }

    // ─────────────────────────────────────────────────────────────────────
    // Full settlement at endGI
    // ─────────────────────────────────────────────────────────────────────

    function test_endGI_settlesAllFourShares() public {
        uint256 pool = 10_000 ether;
        _runFullHonestGI(pool);

        vm.prank(modelOwner);
        tc.endGI(1);

        assertEq(uint256(tc.GIstate()), uint256(GIstates.GIended));

        // Each participant calls claimReward(gi) to credit their claimable balance.
        vm.prank(client1);  ta.claimReward(1);
        vm.prank(client2);  ta.claimReward(1);
        vm.prank(client3);  ta.claimReward(1);
        vm.prank(auditor1); ta.claimReward(1);
        vm.prank(auditor2); ta.claimReward(1);
        vm.prank(auditor3); ta.claimReward(1);
        vm.prank(agg1);     ta.claimReward(1);
        vm.prank(agg2);     ta.claimReward(1);
        vm.prank(agg3);     ta.claimReward(1);

        // Default split: 60/20/15/5 of 10,000 = 6000/2000/1500/500.
        // All three clients scored identically (80, approved) -> equal
        // three-way split of the 6000 client pool.
        assertEq(ta.claimable(client1), uint256(6000 ether) / 3);
        assertEq(ta.claimable(client2), uint256(6000 ether) / 3);
        assertEq(ta.claimable(client3), uint256(6000 ether) / 3);

        // 3 auditors, each voted on all three of the batch's models -> equal
        // weight (3 each) -> equal split of the 2000 auditor pool.
        assertEq(ta.claimable(auditor1), uint256(2000 ether) / 3);
        assertEq(ta.claimable(auditor2), uint256(2000 ether) / 3);
        assertEq(ta.claimable(auditor3), uint256(2000 ether) / 3);

        // 3 aggregators, one finalized T1 batch each, no T2 batch -> equal
        // split of the 1500 aggregator pool.
        assertEq(ta.claimable(agg1), uint256(1500 ether) / 3);
        assertEq(ta.claimable(agg2), uint256(1500 ether) / 3);
        assertEq(ta.claimable(agg3), uint256(1500 ether) / 3);

        assertEq(ta.treasuryAccrued(), 500 ether);
    }

    function testFuzz_endGI_totalClaimablePlusTreasuryNeverExceedsPool(
        uint256 pool
    ) public {
        // Rounding-dust invariant: individually-divided shares can lose a
        // few wei to integer division, but nothing should ever be minted
        // out of thin air -- sum of everything credited must not exceed the
        // deposited pool, for any pool size, not just one fixed
        // not-evenly-divisible-by-3 example.
        pool = bound(pool, 1 ether, 1_000_000 ether);
        _runFullHonestGI(pool);

        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);  ta.claimReward(1);
        vm.prank(client2);  ta.claimReward(1);
        vm.prank(client3);  ta.claimReward(1);
        vm.prank(auditor1); ta.claimReward(1);
        vm.prank(auditor2); ta.claimReward(1);
        vm.prank(auditor3); ta.claimReward(1);
        vm.prank(agg1);     ta.claimReward(1);
        vm.prank(agg2);     ta.claimReward(1);
        vm.prank(agg3);     ta.claimReward(1);

        uint256 totalCredited = ta.claimable(client1) +
            ta.claimable(client2) +
            ta.claimable(client3) +
            ta.claimable(auditor1) +
            ta.claimable(auditor2) +
            ta.claimable(auditor3) +
            ta.claimable(agg1) +
            ta.claimable(agg2) +
            ta.claimable(agg3) +
            ta.treasuryAccrued();

        assertLe(totalCredited, pool);
    }

    function test_endGI_onlyOwner() public {
        _runFullHonestGI(1000 ether);

        vm.prank(auditor1);
        vm.expectRevert();
        tc.endGI(1);
    }

    function test_endGI_revertsBeforeAggregatorsSlashed() public {
        _deployPlatform();
        _deployTaskPair();
        _fundDinBalance(modelOwner, 1 ether);
        vm.prank(modelOwner);
        ta.depositRewards(1, 1 ether);
        vm.prank(modelOwner);
        tc.startGI(1);

        vm.prank(modelOwner);
        vm.expectRevert(); // TC_NotReadyToEndGI
        tc.endGI(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // claimRewards: pull payment
    // ─────────────────────────────────────────────────────────────────────

    function test_claimRewards_transfersAndZeroesBalance() public {
        _runFullHonestGI(10_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);
        ta.claimReward(1);

        uint256 owed = ta.claimable(client1);
        assertGt(owed, 0);
        uint256 balanceBefore = token.balanceOf(client1);

        vm.prank(client1);
        ta.claimRewards();

        assertEq(token.balanceOf(client1), balanceBefore + owed);
        assertEq(ta.claimable(client1), 0);
    }

    function test_claimRewards_zeroBalanceReverts() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(client1);
        vm.expectRevert(); // TA_NoRewardsToClaim
        ta.claimRewards();
    }

    function test_claimRewards_cannotDoubleClaim() public {
        _runFullHonestGI(10_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);
        ta.claimReward(1);

        vm.prank(client1);
        ta.claimRewards();

        vm.prank(client1);
        vm.expectRevert(); // TA_NoRewardsToClaim, balance already zeroed
        ta.claimRewards();
    }

    function test_claimRewards_doesNotAffectOtherClaimants() public {
        _runFullHonestGI(10_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);
        ta.claimReward(1);
        vm.prank(client2);
        ta.claimReward(1);

        uint256 client2Owed = ta.claimable(client2);

        vm.prank(client1);
        ta.claimRewards();

        assertEq(ta.claimable(client2), client2Owed, "claiming client1's balance must not touch client2's");
    }

    // ─────────────────────────────────────────────────────────────────────
    // claimReward: new claim-pull reverts (BL-10)
    // ─────────────────────────────────────────────────────────────────────

    function test_claimReward_revertsIfNotSettled() public {
        _deployPlatform();
        _deployTaskPair();

        vm.prank(client1);
        vm.expectRevert(abi.encodeWithSignature("TA_RewardsNotSettled()"));
        ta.claimReward(1);
    }

    function test_claimReward_revertsOnDoubleClaim() public {
        _runFullHonestGI(1_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);
        ta.claimReward(1);

        vm.prank(client1);
        vm.expectRevert(abi.encodeWithSignature("TA_RewardAlreadyClaimed()"));
        ta.claimReward(1);
    }

    function test_claimReward_revertsIfNoRewardEarned() public {
        _runFullHonestGI(1_000 ether);
        vm.prank(modelOwner);
        tc.endGI(1);

        address nobody = makeAddr("nobody");
        vm.prank(nobody);
        vm.expectRevert(abi.encodeWithSignature("TA_NoRewardEarned()"));
        ta.claimReward(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Weighted aggregator settlement (BL-10 / #125, task_100926_11 §1)
    //
    // #134 shipped an O(1) settleRewards + claimReward(gi), but collapsed
    // the aggregator side to a flat `aggregatorPool / count` share behind an
    // isRewardableAggregator boolean -- while still deriving `count` from the
    // duplicate-containing (aggregator, finalized-batch) list. An aggregator
    // credited for both a T1 and the T2 batch was counted twice in the
    // divisor but paid once, permanently stranding one share in the
    // contract. This PR restores the per-finalized-batch weighting via
    // DINTaskCoordinator.aggregatorWeight, matching _collectFinalizedBatch-
    // Aggregators' documented "appears twice, earns proportionally more"
    // basis (task_210726_6 §3).
    //
    // NOTE on constructability: under the current autoCreateTier1AndTier2,
    // T1 and T2 aggregators are always drawn from disjoint slices of the
    // shuffled pool, so no aggregator is naturally assigned to both. The
    // weight-2 case is reachable by the contract's own NatSpec contract but
    // not by the happy-path assignment, so these tests inject the overlap
    // via stdstore rather than driving it through a full GI.
    // ─────────────────────────────────────────────────────────────────────

    /// @dev Force `agg` to carry `weight` finalized-batch units in `gi` and
    ///      set the GI's aggregator-weight total, as if `agg` had finalized
    ///      an extra batch. Mirrors what a T1+T2 overlap would produce.
    function _injectAggregatorOverlap(
        address agg,
        uint256 gi,
        uint256 weight,
        uint256 total
    ) internal {
        stdstore
            .target(address(tc))
            .sig("aggregatorWeight(uint256,address)")
            .with_key(gi)
            .with_key(agg)
            .checked_write(weight);
        stdstore
            .target(address(tc))
            .sig("totalAggregatorWeight(uint256)")
            .with_key(gi)
            .checked_write(total);
    }

    function test_aggregatorWeight_accumulatesOnePerFinalizedBatch() public {
        _runFullHonestGI(10_000 ether);

        // One finalized T1 batch of 3, no T2 batch -> weight 1 each, total 3.
        assertEq(tc.aggregatorWeight(1, agg1), 1);
        assertEq(tc.aggregatorWeight(1, agg2), 1);
        assertEq(tc.aggregatorWeight(1, agg3), 1);
        assertEq(tc.totalAggregatorWeight(1), 3);
    }

    function test_endGI_snapshotsAggregatorTotalWeight() public {
        _runFullHonestGI(10_000 ether);

        vm.prank(modelOwner);
        tc.endGI(1);

        (, , , uint256 aggTotalWeight, bool settled) = ta.giRewardSnapshot(1);
        assertTrue(settled);
        assertEq(aggTotalWeight, 3);
    }

    function test_claimReward_aggregatorInBothT1AndT2_earnsProportionally()
        public
    {
        uint256 pool = 10_000 ether;
        _runFullHonestGI(pool);

        // agg1 as if it also finalized the T2 batch: weight 2, GI total 4.
        _injectAggregatorOverlap(agg1, 1, 2, 4);

        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(agg1);
        ta.claimReward(1);
        vm.prank(agg2);
        ta.claimReward(1);
        vm.prank(agg3);
        ta.claimReward(1);

        uint256 aggregatorPool = (pool * 1500) / 10000; // 1,500 ether

        // Weighted: agg1 gets 2/4, agg2 and agg3 get 1/4 each.
        assertEq(ta.claimable(agg1), (aggregatorPool * 2) / 4);
        assertEq(ta.claimable(agg2), (aggregatorPool * 1) / 4);
        assertEq(ta.claimable(agg3), (aggregatorPool * 1) / 4);
        assertEq(
            ta.claimable(agg1),
            2 * ta.claimable(agg2),
            "double-weight aggregator earns twice a single-weight one"
        );

        // Nothing stranded: the three shares sum to the whole aggregator pool
        // (2+1+1 == 4 divides 1,500 ether exactly). The pre-#125 flat split
        // would have paid agg1 only aggregatorPool/4, leaving aggregatorPool/4
        // permanently unclaimable.
        assertEq(
            ta.claimable(agg1) + ta.claimable(agg2) + ta.claimable(agg3),
            aggregatorPool,
            "weighted shares must exhaust the aggregator pool"
        );
    }

    function testFuzz_aggregatorInBothBatches_noPoolStranded(
        uint256 pool
    ) public {
        pool = bound(pool, 1 ether, 1_000_000 ether);
        _runFullHonestGI(pool);

        _injectAggregatorOverlap(agg1, 1, 2, 4);

        vm.prank(modelOwner);
        tc.endGI(1);

        vm.prank(client1);  ta.claimReward(1);
        vm.prank(client2);  ta.claimReward(1);
        vm.prank(client3);  ta.claimReward(1);
        vm.prank(auditor1); ta.claimReward(1);
        vm.prank(auditor2); ta.claimReward(1);
        vm.prank(auditor3); ta.claimReward(1);
        vm.prank(agg1);     ta.claimReward(1);
        vm.prank(agg2);     ta.claimReward(1);
        vm.prank(agg3);     ta.claimReward(1);

        uint256 totalCredited = ta.claimable(client1) +
            ta.claimable(client2) +
            ta.claimable(client3) +
            ta.claimable(auditor1) +
            ta.claimable(auditor2) +
            ta.claimable(auditor3) +
            ta.claimable(agg1) +
            ta.claimable(agg2) +
            ta.claimable(agg3) +
            ta.treasuryAccrued();

        // Never mints out of thin air, and never strands more than a handful
        // of wei of integer-division dust (3-way client + 3-way auditor +
        // 4-way aggregator splits). A missed aggregator share would be
        // ~aggregatorPool/4 -- orders of magnitude past this bound.
        assertLe(totalCredited, pool);
        assertGe(totalCredited, pool - 100);
    }

    // ─────────────────────────────────────────────────────────────────────
    // endGI gas: O(1) in participant count (BL-10 / #127, task_100926_11 §3)
    //
    // Full methodology parity with SecurityFindings.t.sol's
    // test_gas_finalizeEvaluation_and_slashAuditors_atScale (a two-scale
    // marginal-cost measurement) needs a GI fixture parametrised by client
    // and auditor count, which _runFullHonestGI is not. What these two tests
    // establish instead: endGI/settleRewards read only scalars after BL-10
    // (the rewardableAggregators array and the _settleClient/_settleAuditor/
    // _settleAggregator loops are deleted), so endGI's cost cannot grow with
    // participant count. The pre-BL-10 endGI path cost was measured in
    // SecurityFindings.t.sol and blew the L2 block gas limit at spec scale.
    // ─────────────────────────────────────────────────────────────────────

    function test_gas_endGI_underConstantCeiling() public {
        _runFullHonestGI(10_000 ether);

        uint256 gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.endGI(1);
        uint256 endGIGas = gasBefore - gasleft();

        emit log_named_uint("endGI gas (3 clients / 3 auditors / 3 aggregators)", endGIGas);

        // No participant-indexed loop remains; endGI is a bounded state
        // transition (one cross-contract call, ~4 mul + 4 div, one struct
        // SSTORE, one event). Ceiling is generous headroom over the measured
        // cost, not a tight bound -- its job is to fail loudly if a loop is
        // ever reintroduced into this path.
        assertLt(endGIGas, 150_000, "endGI must stay a bounded O(1) transition");
    }

    function test_gas_endGI_invariantToSettlementScale() public {
        // Baseline: standard 3/3/3 GI.
        _runFullHonestGI(10_000 ether);
        uint256 gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.endGI(1);
        uint256 gasBaseline = gasBefore - gasleft();

        // Fresh GI, but every incremental total endGI's settlement path could
        // conceivably touch is inflated to spec scale (500 clients * 100-pt
        // scores, 500 auditors * 100 votes, 50 batches * 3 aggregators)
        // before endGI. endGI reads totalAggregatorWeight (1 SLOAD) and
        // settleRewards reads none of these -- so the gas must not move.
        _runFullHonestGI(10_000 ether);
        stdstore
            .target(address(ta))
            .sig("giTotalApprovedScore(uint256)")
            .with_key(uint256(1))
            .checked_write(uint256(500 * 100));
        stdstore
            .target(address(ta))
            .sig("giTotalAuditWeight(uint256)")
            .with_key(uint256(1))
            .checked_write(uint256(500 * 100));
        stdstore
            .target(address(tc))
            .sig("totalAggregatorWeight(uint256)")
            .with_key(uint256(1))
            .checked_write(uint256(50 * 3));

        gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.endGI(1);
        uint256 gasAtScale = gasBefore - gasleft();

        emit log_named_uint("endGI gas, 3/3/3 baseline", gasBaseline);
        emit log_named_uint("endGI gas, spec-scale totals injected", gasAtScale);

        // Injecting totals ~16000x larger moves endGI gas by a handful (state
        // access-list bookkeeping from the stdstore writes), not by anything
        // that scales with the injected magnitude. A reintroduced O(n)
        // settlement loop would add thousands of gas per participant.
        assertApproxEqAbs(
            gasAtScale,
            gasBaseline,
            100,
            "endGI gas must not scale with settlement-total magnitude"
        );
    }

    // ─────────────────────────────────────────────────────────────────────
    // Spec-scale endGI gas benchmark (#127 / #121), same measured-marginal-
    // cost-plus-explicit-extrapolation methodology as SecurityFindings.t.sol's
    // test_gas_finalizeEvaluation_and_slashAuditors_atScale.
    //
    // Two real GIs at different participant counts (n and 3n auditors + the
    // same number of submitted models, forming n/3 vs. n audit batches),
    // both driven all the way to AggregatorsSlashed. endGI gas is measured
    // at each; the slope between them is the real per-participant marginal
    // cost of endGI, which is then extrapolated to spec scale (10-50
    // validators / 100-500 clients per model).
    // ─────────────────────────────────────────────────────────────────────

    /// @dev Registers 3 aggregators (T1_AGGREGATORS_PER_BATCH) plus `n`
    ///      auditors and `n` clients, drives the GI to GIstates.AggregatorsSlashed
    ///      (one call before endGI). Only the first audit batch votes (score
    ///      80, eligible) -- enough for one finalized T1 batch and for
    ///      finalizeEvaluation to succeed; every other registered auditor is
    ///      slashed for not voting, exactly as SecurityFindings.t.sol's
    ///      _setupForGasMeasurement does. `lmSubmissions[1]` still holds `n`
    ///      entries and `auditBatches[1]` holds `n/3` -- the arrays the
    ///      pre-#134 settleRewards looped over.
    function _runScaledGIToAggregatorsSlashed(
        uint n,
        uint256 pool
    ) internal {
        _deployPlatform();
        _deployTaskPair();

        address[3] memory aggs = [
            makeAddr("scAgg0"),
            makeAddr("scAgg1"),
            makeAddr("scAgg2")
        ];
        for (uint i = 0; i < 3; i++) {
            _fundAndStake(aggs[i]);
        }

        _fundDinBalance(modelOwner, pool);
        vm.prank(modelOwner);
        ta.depositRewards(1, pool);
        vm.prank(modelOwner);
        tc.startGI(1);

        vm.prank(modelOwner);
        tc.startDINaggregatorsRegistration(1);
        for (uint i = 0; i < 3; i++) {
            vm.prank(aggs[i]);
            tc.registerDINaggregator(1);
        }

        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        for (uint i = 0; i < n; i++) {
            address a = makeAddr(string.concat("scAud", vm.toString(i)));
            _fundAndStake(a);
            vm.prank(a);
            ta.registerDINAuditor(1);
        }

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        for (uint i = 0; i < n; i++) {
            address c = makeAddr(string.concat("scCli", vm.toString(i)));
            vm.prank(c);
            ta.submitLocalModel(bytes32(uint256(9000 + i)), 1);
        }

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory b0Auditors, uint[] memory b0Models, ) = ta
            .getAuditorsBatch(1, 0);
        bytes32 commitHash = keccak256(
            abi.encodePacked(uint256(80), true, TEST_SALT)
        );
        for (uint i = 0; i < b0Auditors.length; i++) {
            for (uint m = 0; m < b0Models.length; m++) {
                vm.prank(b0Auditors[i]);
                ta.commitAuditScore(1, 0, b0Models[m], commitHash);
            }
        }

        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(1);
        for (uint i = 0; i < b0Auditors.length; i++) {
            for (uint m = 0; m < b0Models.length; m++) {
                vm.prank(b0Auditors[i]);
                ta.revealAuditScore(1, 0, b0Models[m], 80, true, TEST_SALT);
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
            tc.submitT1Aggregation(1, 0, bytes32(uint256(0xC1D)));
        }

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        tc.finalizeT2Aggregation(1);
        tc.slashAuditors(1);
        tc.slashAggregators(1);
        vm.stopPrank();
    }

    function test_gas_endGI_atScale_marginalCostPerParticipantIsZero() public {
        uint256 pool = 10_000 ether;

        // ── Small: 30 auditors + 30 clients -> 10 audit batches ──
        _runScaledGIToAggregatorsSlashed(30, pool);
        (address cliSmall, , , , , , ) = ta.lmSubmissions(1, 29);
        assertEq(cliSmall, makeAddr("scCli29"), "sanity: 30 LM submissions recorded");
        uint256 gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.endGI(1);
        uint256 gasSmall = gasBefore - gasleft();

        // ── Large: 90 auditors + 90 clients -> 30 audit batches ──
        _runScaledGIToAggregatorsSlashed(90, pool);
        (address cliLarge, , , , , , ) = ta.lmSubmissions(1, 89);
        assertEq(cliLarge, makeAddr("scCli89"), "sanity: 90 LM submissions recorded");
        gasBefore = gasleft();
        vm.prank(modelOwner);
        tc.endGI(1);
        uint256 gasLarge = gasBefore - gasleft();

        // Real measured marginal cost. Participants: n auditors + n clients
        // + 3 aggregators. delta = (90+90+3) - (30+30+3) = 120.
        uint256 deltaParticipants = (90 + 90 + 3) - (30 + 30 + 3);
        uint256 marginalGasPerParticipant = gasLarge > gasSmall
            ? (gasLarge - gasSmall) / deltaParticipants
            : 0;

        emit log_named_uint("endGI gas @ 63 participants (30 aud / 30 cli / 3 agg)", gasSmall);
        emit log_named_uint("endGI gas @ 183 participants (90 aud / 90 cli / 3 agg)", gasLarge);
        emit log_named_uint("measured marginal endGI gas per participant", marginalGasPerParticipant);

        // Extrapolate to spec scale: 500 clients + 50 validators, ~550
        // participants. With the settlement loops removed (this PR + #134),
        // the measured slope is ~0, so the projection stays flat.
        uint256 specScaleParticipants = 550;
        uint256 projectedSpecScaleGas = gasSmall +
            marginalGasPerParticipant *
            (specScaleParticipants - 63);
        emit log_named_uint("PROJECTED endGI gas @ spec scale (~550 participants)", projectedSpecScaleGas);

        // A real O(n) settlement loop would add >=1 cold SLOAD (~2100 gas)
        // per extra participant -- >=250k gas across this 120-participant
        // delta. 2000 is a generous noise band for storage-warmth jitter.
        assertApproxEqAbs(
            gasLarge,
            gasSmall,
            2000,
            "endGI gas must not grow with participant count (BL-10: no settlement loop)"
        );
        // And the spec-scale projection stays far under any realistic L2
        // block gas limit -- contrast SecurityFindings.t.sol, where the
        // pre-fix endGI-adjacent path projected to multiples of it.
        assertLt(projectedSpecScaleGas, 1_000_000, "endGI stays O(1) at spec scale");
    }
}
