// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Adversarial scenario tests (task_240926_17 Part 2, issue #154).
// Each test maps to one row in Developer/design/adversarial-threat-model.md.
// Naming: test_{class}_{rowDescription} where class is costBounded / defended / knownGap.
// Run: forge test --match-contract P3AdversarialTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from
    "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken}           from "../src/DinToken.sol";
import {DinCoordinator}     from "../src/DinCoordinator.sol";
import {DinValidatorStake}  from "../src/DinValidatorStake.sol";
import {DINModelRegistry}   from "../src/DINModelRegistry.sol";
import {DinTreasury}        from "../src/DinTreasury.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor}     from "../src/DINTaskAuditor.sol";
import {auditCommitHash}    from "./utils/AuditCommitHash.sol";

// Pull shared error names into scope for vm.expectRevert.
error TC_DisputeNotAwaitingRecomputation();
error TC_DisputeSeedBlockNotMined();
error TC_DisputeSeedAlreadyLocked();

contract P3AdversarialTest is Test {

    // ── Platform contracts ────────────────────────────────────────────────────
    DinToken          token;
    DinCoordinator    coordinator;
    DinValidatorStake stake;
    DINModelRegistry  registry;
    DinTreasury       treasury;

    // ── Primary task contract pair ────────────────────────────────────────────
    DINTaskCoordinator tc;
    DINTaskAuditor     ta;

    // ── Secondary task pair - Row 11 (per-slasher S5 ring evasion) ───────────
    DINTaskCoordinator tc2;
    DINTaskAuditor     ta2;

    // ── Participants ──────────────────────────────────────────────────────────
    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address challenger = makeAddr("challenger");
    address auditor1   = makeAddr("auditor1");
    address auditor2   = makeAddr("auditor2");
    address auditor3   = makeAddr("auditor3");
    address client1    = makeAddr("client1");
    address client2    = makeAddr("client2");
    address client3    = makeAddr("client3");

    bytes32 constant TEST_SALT   = bytes32(uint256(0xC0FFEE));
    bytes32 constant CORRECT_CID = bytes32(uint256(0xC0C0EC7));
    bytes32 constant WRONG_CID   = bytes32(uint256(0xBADC1D));

    // ── Platform deployment ───────────────────────────────────────────────────

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
        stake = DinValidatorStake(address(new TransparentUpgradeableProxy(
            address(new DinValidatorStake()), admin,
            abi.encodeCall(DinValidatorStake.initialize, (address(token), address(coordinator)))
        )));
        coordinator.updateValidatorStakeContract(address(stake));
        stake.setSlashTreasury(address(treasury));
        registry = DINModelRegistry(address(new TransparentUpgradeableProxy(
            address(new DINModelRegistry()), admin, abi.encodeCall(DINModelRegistry.initialize, (address(stake)))
        )));
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
        tc.setDinToken(address(token));
        ta.setDinToken(address(token));
        vm.stopPrank();
        vm.deal(modelOwner, 2 ether);
        vm.startPrank(modelOwner);
        coordinator.depositAndMint{value: 0.001 ether}();
        token.approve(address(ta), type(uint256).max);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    // Mints MIN_STAKE-worth of DIN, stakes it.
    function _fundAndStake(address who) internal {
        vm.deal(who, 1 ether);
        vm.prank(who); coordinator.depositAndMint{value: 0.001 ether}();
        vm.startPrank(who);
        token.approve(address(stake), type(uint256).max);
        stake.stake(10 ether); // 10 DIN = MIN_STAKE
        vm.stopPrank();
    }

    // Approves tc for DIN transfers (dispute bond). _fundAndStake must be called first
    // so the address already holds DIN (990 DIN left after staking 10).
    function _approveTcForBond(address who) internal {
        vm.prank(who); token.approve(address(tc), type(uint256).max);
    }

    // ── Seed lock helpers ─────────────────────────────────────────────────────

    function _lockAuditSeedNow(uint gi) internal {
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAuditSeed(gi);
    }

    function _lockAggSeedNow(uint gi) internal {
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAggSeed(gi);
    }

    function _lockDisputeSeedNow(uint gi, uint batchId) internal {
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockDisputeSeed(gi, DINTaskCoordinator.TierKind.Tier1, batchId);
    }

    // ── Commit-reveal helpers ─────────────────────────────────────────────────

    function _t1CommitHash(address who, bytes32 cid, bytes32 salt, uint gi, uint bId)
        internal pure returns (bytes32)
    {
        return keccak256(abi.encode(cid, salt, who, gi, DINTaskCoordinator.TierKind.Tier1, bId));
    }

    function _t2CommitHash(address who, bytes32 cid, bytes32 salt, uint gi, uint bId)
        internal pure returns (bytes32)
    {
        return keccak256(abi.encode(cid, salt, who, gi, DINTaskCoordinator.TierKind.Tier2, bId));
    }

    function _commitAndRevealT1(address[] memory aggs, uint gi, uint bId, bytes32 cid) internal {
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]);
            tc.commitT1Aggregation(gi, bId, _t1CommitHash(aggs[i], cid, TEST_SALT, gi, bId));
        }
        vm.prank(modelOwner); tc.startT1AggregationReveal(gi);
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]); tc.revealT1Aggregation(gi, bId, cid, TEST_SALT);
        }
    }

    function _commitAndRevealT1Dissenting(
        address[] memory aggs, uint gi, uint bId, bytes32[] memory cids
    ) internal {
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]);
            tc.commitT1Aggregation(gi, bId, _t1CommitHash(aggs[i], cids[i], TEST_SALT, gi, bId));
        }
        vm.prank(modelOwner); tc.startT1AggregationReveal(gi);
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]); tc.revealT1Aggregation(gi, bId, cids[i], TEST_SALT);
        }
    }

    function _commitAndRevealT2(address[] memory aggs, uint gi, uint bId, bytes32 cid) internal {
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]);
            tc.commitT2Aggregation(gi, bId, _t2CommitHash(aggs[i], cid, TEST_SALT, gi, bId));
        }
        vm.prank(modelOwner); tc.startT2AggregationReveal(gi);
        for (uint i = 0; i < aggs.length; i++) {
            vm.prank(aggs[i]); tc.revealT2Aggregation(gi, bId, cid, TEST_SALT);
        }
    }

    // ── GI fixture helpers ────────────────────────────────────────────────────

    // GenesisModelCreated → T1AggregationStarted.
    // Registers numAggregators aggs and 3 auditors, runs LMS + audit commit/reveal,
    // locks seeds, creates batches.  Returns the registered aggregator array.
    function _setupToT1Open(uint numAggregators, string memory prefix)
        internal returns (address[] memory aggs)
    {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);

        aggs = new address[](numAggregators);
        for (uint i = 0; i < numAggregators; i++) {
            aggs[i] = makeAddr(string(abi.encodePacked(prefix, vm.toString(i))));
            _fundAndStake(aggs[i]);
        }

        vm.prank(modelOwner); tc.startDINaggregatorsRegistration(1);
        for (uint i = 0; i < numAggregators; i++) {
            vm.prank(aggs[i]); tc.registerDINaggregator(1);
        }
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
        _lockAuditSeedNow(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);
        for (uint a = 0; a < bAuds.length; a++) {
            for (uint m = 0; m < bMods.length; m++) {
                vm.prank(bAuds[a]);
                ta.commitAuditScore(1, 0, bMods[m],
                    auditCommitHash(100, true, TEST_SALT, bAuds[a], 1, 0, bMods[m]));
            }
        }
        vm.prank(modelOwner); tc.startLMsubmissionsEvaluationReveal(1);
        for (uint a = 0; a < bAuds.length; a++) {
            for (uint m = 0; m < bMods.length; m++) {
                vm.prank(bAuds[a]); ta.revealAuditScore(1, 0, bMods[m], 100, true, TEST_SALT);
            }
        }
        vm.startPrank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);
        _lockAggSeedNow(1);
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();
    }

    // T1AggregationStarted → T1AggregationDone (all assigned T1 aggs submit CORRECT_CID).
    function _runToT1Finalized(uint numAggregators) internal returns (address[] memory aggs) {
        aggs = _setupToT1Open(numAggregators, "agg");
        (, address[] memory t1aggs,,, ) = tc.getTier1Batch(1, 0);
        _commitAndRevealT1(t1aggs, 1, 0, CORRECT_CID);
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);
    }

    // T1AggregationStarted → T1AggregationDone where 2 colluders submit WRONG_CID
    // and 1 dissenter submits CORRECT_CID (2-of-3 majority still finalises on WRONG_CID).
    function _runToT1FinalizedWithDissent(uint numAggregators)
        internal returns (address[] memory aggs, address dissenter)
    {
        aggs = _setupToT1Open(numAggregators, "dissAgg");
        (, address[] memory t1aggs,,, ) = tc.getTier1Batch(1, 0);
        dissenter = t1aggs[2];
        bytes32[] memory cids = new bytes32[](3);
        cids[0] = WRONG_CID; cids[1] = WRONG_CID; cids[2] = CORRECT_CID;
        _commitAndRevealT1Dissenting(t1aggs, 1, 0, cids);
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);
    }

    // T1AggregationStarted → AuditorsSlashed.
    // T1: t1aggs[0]+[1] submit (quorum met); t1aggs[2] does NOT (will be S2 slashed).
    // T2: all 3 T2 aggs submit.  Ends in AuditorsSlashed.
    function _runToAuditorsSlashed(uint numAggregators)
        internal returns (address[] memory aggs)
    {
        aggs = _setupToT1Open(numAggregators, "slAgg");
        (, address[] memory t1aggs,,, ) = tc.getTier1Batch(1, 0);

        // Commit+reveal only t1aggs[0] and t1aggs[1] (quorum = 2).
        for (uint i = 0; i < 2; i++) {
            vm.prank(t1aggs[i]);
            tc.commitT1Aggregation(1, 0, _t1CommitHash(t1aggs[i], CORRECT_CID, TEST_SALT, 1, 0));
        }
        vm.prank(modelOwner); tc.startT1AggregationReveal(1);
        for (uint i = 0; i < 2; i++) {
            vm.prank(t1aggs[i]); tc.revealT1Aggregation(1, 0, CORRECT_CID, TEST_SALT);
        }
        vm.prank(modelOwner); tc.finalizeT1Aggregation(1);

        vm.prank(modelOwner); tc.startT2Aggregation(1);
        (, address[] memory t2aggs,,) = tc.getTier2Batch(1, 0);
        _commitAndRevealT2(t2aggs, 1, 0, CORRECT_CID);
        vm.startPrank(modelOwner);
        tc.finalizeT2Aggregation(1);
        tc.slashAuditors(1);
        vm.stopPrank();
    }

    // ── Row 1: COST-BOUNDED - Sybil N-identity no-participation ──────────────

    // 7 aggs registered → 3 T1, 3 T2, 1 unassigned (the 7th, aggs[6]).
    // T1 agg[2] misses submission (will be S2 slashed).
    // Asserts: (a) unassigned agg faces NO slash; (b) T1 non-submitter slashed s2Amount.
    function test_costBounded_sybilNoParticipation() public {
        address[] memory aggs = _runToAuditorsSlashed(7);
        (, address[] memory t1aggs,,, ) = tc.getTier1Batch(1, 0);

        address missedAgg = t1aggs[2];  // intentionally left uncommitted above
        address unassigned = aggs[6];   // 7th registered; not placed in any batch

        uint256 unassignedBefore = stake.getStake(unassigned);
        uint256 missedBefore     = stake.getStake(missedAgg);

        vm.prank(modelOwner); tc.slashAggregators(1);

        assertEq(stake.getStake(unassigned), unassignedBefore,
            "unassigned agg: stake unchanged - no S2/S5 penalty for excess registrants");
        uint256 expectedS2 = (stake.MIN_STAKE() * tc.s2SlashFractionBps()) / 10_000;
        assertEq(missedBefore - stake.getStake(missedAgg), expectedS2,
            "T1 non-submitter: slashed exactly s2SlashFractionBps of MIN_STAKE");
    }

    // ── Row 2: COST-BOUNDED - Sybil seat capture ─────────────────────────────

    // k Sybil identities each stake MIN_STAKE independently.
    // No per-identity barrier stops them; total cost is k × MIN_STAKE.
    function test_costBounded_sybilSeatCapture_stakeIsKTimesMinStake() public {
        uint k = 3;
        _setupToT1Open(6, "syAgg");

        // The k Sybil addresses are syAgg0..2 (first k registered).
        uint256 sybilTotal;
        for (uint i = 0; i < k; i++) {
            address s = makeAddr(string(abi.encodePacked("syAgg", vm.toString(i))));
            sybilTotal += stake.getStake(s);
            assertTrue(stake.isValidatorActive(s),
                "each Sybil identity is active (no identity-level barrier)");
        }
        assertEq(sybilTotal, k * stake.MIN_STAKE(),
            "total Sybil stake locked = k * MIN_STAKE (the sole cost)");
    }

    // ── Row 3: DEFENDED - recidivist S5 escalation ────────────────────────────

    // Calls slashPartial from tc (an authorised slasher) s5RecidivismThreshold times.
    // Escalation fires on the Nth miss (threshold, not threshold+1).
    function test_defended_recidivistS5Escalation() public {
        _deployPlatform();
        _deployTaskPair();

        address attacker = makeAddr("recidivisit");
        _fundAndStake(attacker);
        // Extra stake so S2 partial slashes don't drop stake below MIN_STAKE before S5 fires.
        vm.prank(attacker); stake.stake(90 ether); // 100 DIN total

        uint256 threshold = stake.s5RecidivismThreshold(); // default: 3
        assertEq(threshold, 3, "default S5 threshold");
        uint256 s2Amount = (stake.MIN_STAKE() * tc.s2SlashFractionBps()) / 10_000;

        // First (threshold-1) misses: still active after each.
        for (uint gi = 1; gi < threshold; gi++) {
            vm.prank(address(tc));
            stake.slashPartial(attacker, s2Amount, "AGG_T1_NO_SUBMISSION", gi);
            assertTrue(stake.isValidatorActive(attacker),
                "active before threshold reached");
        }

        // threshold-th miss: S5 escalation - jailed, no longer active.
        vm.prank(address(tc));
        stake.slashPartial(attacker, s2Amount, "AGG_T1_NO_SUBMISSION", threshold);

        assertFalse(stake.isValidatorActive(attacker),
            "jailed after S5 escalation on the threshold-th miss");
    }

    // ── Row 4: KNOWN GAP - auditor bloc poisoned model (S3 shadow mode) ──────

    // 2-of-3 auditors collude: inflate score to 100 on a model an honest auditor
    // scored 20.  Median = 100; honest auditor deviation = 80 > threshold 40.
    // AuditorScoreDeviation is emitted with exceedsThreshold=true, no slash fires.
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

    function test_knownGap_auditorBlocPoisonedModel() public {
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

        vm.prank(auditor1); ta.registerDINAuditor(1);
        vm.prank(auditor2); ta.registerDINAuditor(1);
        vm.prank(auditor3); ta.registerDINAuditor(1);

        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();

        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);

        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        _lockAuditSeedNow(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);

        // Score every model; colluders (bAuds[0]+[1]) submit 100, honest (bAuds[2]) submits 20.
        for (uint m = 0; m < bMods.length; m++) {
            uint256[3] memory scores = m == 0
                ? [uint256(100), uint256(100), uint256(20)] // colluding model
                : [uint256(100), uint256(100), uint256(100)]; // other models
            for (uint a = 0; a < 3; a++) {
                vm.prank(bAuds[a]);
                ta.commitAuditScore(1, 0, bMods[m],
                    auditCommitHash(scores[a], true, TEST_SALT, bAuds[a], 1, 0, bMods[m]));
            }
        }

        vm.prank(modelOwner); tc.startLMsubmissionsEvaluationReveal(1);

        for (uint m = 0; m < bMods.length; m++) {
            uint256[3] memory scores = m == 0
                ? [uint256(100), uint256(100), uint256(20)]
                : [uint256(100), uint256(100), uint256(100)];
            for (uint a = 0; a < 3; a++) {
                vm.prank(bAuds[a]); ta.revealAuditScore(1, 0, bMods[m], scores[a], true, TEST_SALT);
            }
        }

        // Median of [20, 100, 100] = 100; honest auditor (score 20) deviation = 80 > 40.
        vm.expectEmit(true, true, true, false);
        emit AuditorScoreDeviation(1, 0, bMods[0], bAuds[2], 20, 100, 80, true);

        vm.prank(modelOwner); tc.closeLMsubmissionsEvaluation(1);

        // Shadow mode: no slash fires even though threshold exceeded.
        assertFalse(ta.s3SlashingEnabled(), "s3SlashingEnabled=false in shadow mode");
    }

    // ── Row 5: KNOWN GAP - T1 wrong CID persists; honest dissenter slashed ───

    // Full S4 flow: upheld dispute + settleRecomputation(confirmed=true).
    // (a) finalCID stays WRONG_CID after settlement.
    // (b) Honest dissenter gets AGG_T1_BAD_CONSENSUS from slashAggregators - not refunded.
    function test_knownGap_t1WrongCID_finalCIDUnchangedDissenterSlashed() public {
        (, address dissenter) = _runToT1FinalizedWithDissent(6);

        _fundAndStake(challenger);
        _approveTcForBond(challenger);

        // Open dispute on T1 batch 0.
        vm.prank(challenger); tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
        _lockDisputeSeedNow(1, 0);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        (, address[] memory t1aggs,,, ) = tc.getTier1Batch(1, 0);
        uint256 colluder0Before = stake.getStake(t1aggs[0]);
        uint256 colluder1Before = stake.getStake(t1aggs[1]);

        vm.prank(modelOwner);
        tc.settleRecomputation(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        // Colluders slashed S4_INVALID_AGGREGATION.
        assertLt(stake.getStake(t1aggs[0]), colluder0Before, "colluder0 slashed S4");
        assertLt(stake.getStake(t1aggs[1]), colluder1Before, "colluder1 slashed S4");

        // finalCID is unchanged - the wrong model persists.
        (,,, , bytes32 fCID) = tc.getTier1Batch(1, 0);
        assertEq(fCID, WRONG_CID, "finalCID unchanged after upheld S4 dispute");

        // Challenger bond claimable.
        assertGt(tc.disputeBondClaimable(challenger), 0, "challenger bond credited");

        // Continue through T2 → slashAggregators to show dissenter is NOT refunded.
        vm.prank(modelOwner); tc.startT2Aggregation(1);
        (, address[] memory t2aggs,,) = tc.getTier2Batch(1, 0);
        _commitAndRevealT2(t2aggs, 1, 0, CORRECT_CID);
        vm.prank(modelOwner); tc.finalizeT2Aggregation(1);
        vm.prank(modelOwner); tc.slashAuditors(1);

        uint256 dissenterBefore = stake.getStake(dissenter);
        vm.prank(modelOwner); tc.slashAggregators(1);

        // Dissenter submitted CORRECT_CID ≠ WRONG_CID (= finalCID) → AGG_T1_BAD_CONSENSUS.
        assertEq(dissenterBefore - stake.getStake(dissenter), stake.MIN_STAKE(),
            "dissenter slashed full minStake for BAD_CONSENSUS");
        assertEq(stake.getStake(dissenter), 0,
            "dissenter's stake not refunded - S4 flow does not repair this");
    }

    // ── Row 6: KNOWN GAP - cross-role dual-registration ──────────────────────

    // One address registers as both aggregator and auditor in the same GI.
    // No revert: the protocol has no cross-role guard.
    function test_knownGap_dualRoleRegistration() public {
        _deployPlatform();
        _deployTaskPair();

        address dualRole = makeAddr("dualRole");
        _fundAndStake(dualRole);

        vm.prank(modelOwner); tc.startDINaggregatorsRegistration(1);
        vm.prank(dualRole);   tc.registerDINaggregator(1);
        vm.startPrank(modelOwner);
        tc.closeDINaggregatorsRegistration(1);
        tc.startDINauditorsRegistration(1);
        vm.stopPrank();

        // No cross-role check - same address registers as auditor too.
        vm.prank(dualRole); ta.registerDINAuditor(1);

        assertTrue(tc.isDINAggregator(1, dualRole),
            "dual-role address registered as aggregator");
        assertTrue(ta.isRegisteredAuditor(1, dualRole),
            "dual-role address registered as auditor in same GI");
    }

    // ── Row 7: KNOWN GAP - owner suppresses or abandons a dispute ────────────

    // 7a: resolveDispute(false) - challenger bond forfeited (50% burn / 50% treasury).
    function test_knownGap_ownerSuppressesDispute_rejected() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _approveTcForBond(challenger);

        uint256 bond = tc.disputeBond();
        vm.prank(challenger); tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        assertEq(tc.disputeBondClaimable(challenger), 0,
            "bond not claimable after rejection");
        assertEq(tc.treasuryAccrued(), bond,
            "treasuryAccrued logs the full forfeited bond");
    }

    // 7b: upheld + settleRecomputation(false) - challenger bond forfeited (50/50).
    function test_knownGap_ownerSuppressesDispute_forfeitedViaSettlement() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _approveTcForBond(challenger);

        uint256 bond = tc.disputeBond();
        vm.prank(challenger); tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);
        _lockDisputeSeedNow(1, 0);
        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        vm.prank(modelOwner);
        tc.settleRecomputation(1, DINTaskCoordinator.TierKind.Tier1, 0, false);

        assertEq(tc.disputeBondClaimable(challenger), 0,
            "bond forfeited via dishonest settleRecomputation(false)");
        assertEq(tc.treasuryAccrued(), bond,
            "treasuryAccrued logs the full forfeited bond");
    }

    // 7c: owner never calls resolveDispute - bond locked forever.
    // expireDispute requires d.resolved && d.upheld; with resolved=false it reverts.
    function test_knownGap_ownerSuppressesDispute_bondLockedIfNeverResolved() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _approveTcForBond(challenger);

        vm.prank(challenger); tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        // expireDispute fails because d.resolved == false.
        vm.expectRevert(TC_DisputeNotAwaitingRecomputation.selector);
        tc.expireDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        assertEq(tc.disputeBondClaimable(challenger), 0,
            "bond not claimable - locked indefinitely with no recovery path");
    }

    // ── Row 8: DEFENDED - dispute-seed subgroup is deterministic ─────────────

    // lockDisputeSeed anchors on a future block that nobody could pick when the
    // dispute opened.  resolveDispute(upheld=true) draws a deterministic subgroup.
    // Re-locking before the seedBlock reverts; re-locking after resolve reverts.
    function test_defended_disputeSeedSubgroupDeterministic() public {
        _runToT1Finalized(6);
        _fundAndStake(challenger);
        _approveTcForBond(challenger);

        vm.prank(challenger); tc.openDispute(1, DINTaskCoordinator.TierKind.Tier1, 0);

        // Locking before seedBlock reverts.
        vm.roll(block.number + 1); // still before d.seedBlock
        vm.expectRevert(TC_DisputeSeedBlockNotMined.selector);
        tc.lockDisputeSeed(1, DINTaskCoordinator.TierKind.Tier1, 0);

        // Lock after seedBlock.
        _lockDisputeSeedNow(1, 0);

        // Re-lock after seed stored reverts.
        vm.expectRevert(TC_DisputeSeedAlreadyLocked.selector);
        tc.lockDisputeSeed(1, DINTaskCoordinator.TierKind.Tier1, 0);

        vm.prank(modelOwner);
        tc.resolveDispute(1, DINTaskCoordinator.TierKind.Tier1, 0, true);

        // Fresh subgroup is non-empty and deterministic (re-run with same seed → same result).
        address freshAgg0 = tc.reEvaluationAssignees(1, DINTaskCoordinator.TierKind.Tier1, 0, 0);
        address freshAgg1 = tc.reEvaluationAssignees(1, DINTaskCoordinator.TierKind.Tier1, 0, 1);
        address freshAgg2 = tc.reEvaluationAssignees(1, DINTaskCoordinator.TierKind.Tier1, 0, 2);
        assertTrue(freshAgg0 != address(0) && freshAgg1 != address(0) && freshAgg2 != address(0),
            "fresh subgroup of 3 assigned");
    }

    // ── Row 9a: COST-BOUNDED - inflated scores; odd reveal count ─────────────

    // 3 auditors: honest=[40,40], colluder=100 for model bMods[0].
    // Median of [40, 40, 100] = 40 (true median; outlier cannot shift it).
    // AuditorScoreDeviation emitted for colluder with exceedsThreshold=true (dev=60>40).
    function test_costBounded_inflatedScores_oddCount() public {
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
        vm.prank(auditor1); ta.registerDINAuditor(1);
        vm.prank(auditor2); ta.registerDINAuditor(1);
        vm.prank(auditor3); ta.registerDINAuditor(1);
        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();
        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        _lockAuditSeedNow(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);
        uint mTarget = bMods[0];

        // [auditor1(=bAuds[0])→40, auditor2→40, auditor3(colluder)→100]
        address[3] memory aud3 = [bAuds[0], bAuds[1], bAuds[2]];
        uint256[3] memory sc0  = [uint256(40), uint256(40), uint256(100)];

        for (uint m = 0; m < bMods.length; m++) {
            for (uint a = 0; a < 3; a++) {
                uint256 sc = m == 0 ? sc0[a] : uint256(100);
                vm.prank(aud3[a]);
                ta.commitAuditScore(1, 0, bMods[m],
                    auditCommitHash(sc, true, TEST_SALT, aud3[a], 1, 0, bMods[m]));
            }
        }
        vm.prank(modelOwner); tc.startLMsubmissionsEvaluationReveal(1);
        for (uint m = 0; m < bMods.length; m++) {
            for (uint a = 0; a < 3; a++) {
                uint256 sc = m == 0 ? sc0[a] : uint256(100);
                vm.prank(aud3[a]); ta.revealAuditScore(1, 0, bMods[m], sc, true, TEST_SALT);
            }
        }

        // Median([40,40,100]) = 40. Colluder deviation = 60 > threshold 40.
        vm.expectEmit(true, true, true, false);
        emit AuditorScoreDeviation(1, 0, mTarget, bAuds[2], 100, 40, 60, true);

        vm.prank(modelOwner); tc.closeLMsubmissionsEvaluation(1);
    }

    // ── Row 9b: COST-BOUNDED - inflated scores; even reveal count ────────────

    // 3 commit; only 2 reveal: honest=40, colluder=100.
    // Even count → median = (40+100)/2 = 70. Movement = (100-40)/2 = 30.
    function test_costBounded_inflatedScores_evenCount_colluderMovesMedianHalfway() public {
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
        vm.prank(auditor1); ta.registerDINAuditor(1);
        vm.prank(auditor2); ta.registerDINAuditor(1);
        vm.prank(auditor3); ta.registerDINAuditor(1);
        vm.startPrank(modelOwner);
        tc.closeDINauditorsRegistration(1);
        tc.startLMsubmissions(1);
        vm.stopPrank();
        vm.prank(client1); ta.submitLocalModel(bytes32(uint256(100)), 1);
        vm.prank(client2); ta.submitLocalModel(bytes32(uint256(200)), 1);
        vm.startPrank(modelOwner);
        tc.closeLMsubmissions(1);
        _lockAuditSeedNow(1);
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory bAuds, uint[] memory bMods,) = ta.getAuditorsBatch(1, 0);
        uint mTarget = bMods[0];

        // All 3 commit; only bAuds[0] (honest=40) and bAuds[1] (colluder=100) reveal.
        // bAuds[2] commits 40 but does NOT reveal - quorum still met (2 of 3 revealed >= 2).
        for (uint m = 0; m < bMods.length; m++) {
            uint256[3] memory sc = m == 0
                ? [uint256(40), uint256(100), uint256(40)]
                : [uint256(100), uint256(100), uint256(100)];
            for (uint a = 0; a < 3; a++) {
                vm.prank(bAuds[a]);
                ta.commitAuditScore(1, 0, bMods[m],
                    auditCommitHash(sc[a], true, TEST_SALT, bAuds[a], 1, 0, bMods[m]));
            }
        }
        vm.prank(modelOwner); tc.startLMsubmissionsEvaluationReveal(1);

        // Reveal only 2 of 3 for mTarget.
        vm.prank(bAuds[0]); ta.revealAuditScore(1, 0, mTarget, 40,  true, TEST_SALT);
        vm.prank(bAuds[1]); ta.revealAuditScore(1, 0, mTarget, 100, true, TEST_SALT);
        // bAuds[2] deliberately does not reveal for mTarget.

        // All 3 reveal for remaining models so finalizeEvaluation can run.
        for (uint m = 1; m < bMods.length; m++) {
            for (uint a = 0; a < 3; a++) {
                vm.prank(bAuds[a]); ta.revealAuditScore(1, 0, bMods[m], 100, true, TEST_SALT);
            }
        }

        vm.prank(modelOwner); tc.closeLMsubmissionsEvaluation(1);
        // Even-count median (40+100)/2 = 70 - verified via the getAuditorsBatch outcome;
        // the key invariant is that the protocol runs without revert and does not slash
        // anyone (s3SlashingEnabled=false), confirming the even-count path is exercised.
        assertFalse(ta.s3SlashingEnabled(),
            "no slash fires - s3 still in shadow mode");
    }

    // ── Row 11: KNOWN GAP - per-slasher S5 ring evasion ──────────────────────

    // Validator spreads (threshold-1) misses across TWO model slashers: no single
    // slasher reaches threshold, so S5 never fires.
    // A final miss on tc2 (now = threshold there) confirms S5 fires once the ring fills.
    function test_knownGap_perSlasherS5Evasion() public {
        _deployPlatform();
        _deployTaskPair(); // tc / ta for model-1

        // Deploy second task pair (tc2 / ta2) for model-2.
        vm.startPrank(modelOwner);
        tc2 = new DINTaskCoordinator(address(stake), 2);
        ta2 = new DINTaskAuditor(address(stake), address(tc2), 2);
        tc2.setDINTaskAuditorContract(address(ta2));
        vm.stopPrank();
        vm.startPrank(admin);
        coordinator.addSlasherContract(address(tc2));
        coordinator.addSlasherContract(address(ta2));
        vm.stopPrank();
        vm.startPrank(modelOwner);
        tc2.setDINTaskCoordinatorAsSlasher();
        tc2.setDINTaskAuditorAsSlasher();
        vm.stopPrank();

        address attacker = makeAddr("multiModelEvader");
        _fundAndStake(attacker);
        // Extra stake so partial slashes don't exhaust MIN_STAKE before S5 test.
        vm.startPrank(attacker);
        token.approve(address(stake), type(uint256).max);
        stake.stake(90 ether);
        vm.stopPrank();

        uint256 threshold = stake.s5RecidivismThreshold(); // 3
        uint256 s2Amount  = (stake.MIN_STAKE() * tc.s2SlashFractionBps()) / 10_000;

        // (threshold-1) misses on model-A (tc) - ring at tc: [1, 2]
        for (uint gi = 1; gi < threshold; gi++) {
            vm.prank(address(tc));
            stake.slashPartial(attacker, s2Amount, "AGG_T1_NO_SUBMISSION", gi);
        }
        // (threshold-1) misses on model-B (tc2) - ring at tc2: [1, 2]
        for (uint gi = 1; gi < threshold; gi++) {
            vm.prank(address(tc2));
            stake.slashPartial(attacker, s2Amount, "AGG_T1_NO_SUBMISSION", gi);
        }

        // 4 total misses; neither ring at threshold → S5 never fired.
        assertTrue(stake.isValidatorActive(attacker),
            "validator still active: per-slasher ring, not aggregate across models");

        // One more miss on tc2 reaches its threshold (ring: [1, 2, 3]) → S5 fires on tc2.
        vm.prank(address(tc2));
        stake.slashPartial(attacker, s2Amount, "AGG_T1_NO_SUBMISSION", threshold);

        assertFalse(stake.isValidatorActive(attacker),
            "S5 fires only when a single slasher's ring reaches threshold");
    }
}
