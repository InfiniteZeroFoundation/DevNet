// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Contract-level tests for issue #156 M-1 (task_240926_18 Part C, aggregation
// side): commit-then-reveal for T1/T2 aggregation submissions. Mirrors
// AuditorCommitReveal.t.sol's structure, with one addition specific to this
// side's hardening -- the commit hash binds msg.sender (GI, tier, batchId
// too), unlike PR #63's auditor-side hash, so a lazy aggregator can't copy a
// peer's commit hash and reveal the peer's (cid, salt) under their own name.
// Run: forge test --match-contract AggregatorCommitRevealTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {
    GIstates,
    TC_AlreadySubmitted,
    TC_NotReadyToFinalizeT1,
    TC_NotReadyToFinalizeT2,
    TC_OnlyOneTier2Batch,
    TC_T1AlreadyCommitted,
    TC_T1EmptyCommitHash,
    TC_T1NoCommitFound,
    TC_T1RevealHashMismatch,
    TC_T1RevealPhaseNotOpen,
    TC_T2AlreadyCommitted,
    TC_T2EmptyCommitHash,
    TC_T2NoCommitFound,
    TC_T2RevealHashMismatch,
    TC_T2RevealPhaseNotOpen
} from "../src/DINShared.sol";

contract AggregatorCommitRevealTest is Test {
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
    address client3 = makeAddr("client3");
    address agg1 = makeAddr("agg1");
    address agg2 = makeAddr("agg2");
    address agg3 = makeAddr("agg3");
    address agg4 = makeAddr("agg4");
    address agg5 = makeAddr("agg5");
    address agg6 = makeAddr("agg6");

    // Fixed salt for every commit in this suite -- same rationale as
    // AuditorCommitReveal.t.sol's TEST_SALT (secrecy isn't what these tests
    // exercise; nothing here reads salt before the matching reveal call).
    bytes32 constant TEST_SALT = bytes32(uint256(0xC0FFEE));
    bytes32 constant CID_A = bytes32(uint256(0xA1));
    bytes32 constant CID_B = bytes32(uint256(0xB2));

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
        vm.prank(who);
        token.approve(address(ta), type(uint256).max);
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
        vm.stopPrank();
        _fundDinBalance(modelOwner, 1 ether);
        vm.startPrank(modelOwner);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    /// @dev Drives the GI to T1AggregationStarted (the T1 commit-phase state)
    ///      with 6 registered aggregators (3 T1 + 3 T2 per
    ///      T1_AGGREGATORS_PER_BATCH), 3 auditors, and 3 approved models
    ///      (T1_MODELS_PER_BATCH), WITHOUT committing or revealing any T1
    ///      aggregation -- callers drive commit/reveal themselves.
    function _runToT1AggregationStarted() internal {
        _deployPlatform();
        _deployTaskPair();

        _fundAndStake(auditor1);
        _fundAndStake(auditor2);
        _fundAndStake(auditor3);
        _fundAndStake(agg1);
        _fundAndStake(agg2);
        _fundAndStake(agg3);
        _fundAndStake(agg4);
        _fundAndStake(agg5);
        _fundAndStake(agg6);

        vm.startPrank(modelOwner);
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
        _lockAuditSeedNow(1); // issue #156 H-2
        tc.createAuditorsBatches(1);
        tc.setTestDataAssignedFlag(1, true);
        tc.startLMsubmissionsEvaluation(1);
        vm.stopPrank();

        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);
        bytes32 scoreCommit = keccak256(abi.encodePacked(uint256(100), true, TEST_SALT));
        for (uint i = 0; i < batchAuditors.length; i++) {
            for (uint m = 0; m < modelIdxs.length; m++) {
                vm.prank(batchAuditors[i]);
                ta.commitAuditScore(1, 0, modelIdxs[m], scoreCommit);
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
        _lockAggSeedNow(1); // issue #156 H-2
        tc.autoCreateTier1AndTier2(1);
        tc.startT1Aggregation(1);
        vm.stopPrank();
    }

    /// @dev issue #156 H-2: rolls past disputeSeedDelay and locks the
    ///      auditor-batch seed for `gi`. Small helper (mirrors
    ///      DisputeResolution.t.sol's identically-named helpers) so this
    ///      fixture doesn't inline the roll+lock twice.
    function _lockAuditSeedNow(uint gi) internal {
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAuditSeed(gi);
    }

    /// @dev Same as _lockAuditSeedNow, for the T1/T2 aggregation seed.
    function _lockAggSeedNow(uint gi) internal {
        vm.roll(block.number + tc.disputeSeedDelay() + 1);
        tc.lockAggSeed(gi);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Commit-then-reveal helpers. `_openT1RevealPhase` is the model-owner
    // action closing T1 commits and opening T1 reveals.
    // ─────────────────────────────────────────────────────────────────────

    function _t1CommitHash(address who, bytes32 cid, bytes32 salt, uint batchId) internal pure returns (bytes32) {
        return keccak256(abi.encode(cid, salt, who, uint(1), DINTaskCoordinator.TierKind.Tier1, batchId));
    }

    function _commitT1(address who, uint batchId, bytes32 cid) internal {
        vm.prank(who);
        tc.commitT1Aggregation(1, batchId, _t1CommitHash(who, cid, TEST_SALT, batchId));
    }

    function _revealT1(address who, uint batchId, bytes32 cid) internal {
        vm.prank(who);
        tc.revealT1Aggregation(1, batchId, cid, TEST_SALT);
    }

    function _openT1RevealPhase() internal {
        vm.prank(modelOwner);
        tc.startT1AggregationReveal(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Correctness and anti-copying properties.
    // ─────────────────────────────────────────────────────────────────────

    function test_commitReveal_happyPath_cidCountedAfterReveal() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);
        _openT1RevealPhase();
        _revealT1(t1aggs[0], 0, CID_A);

        assertTrue(tc.t1Submitted(1, 0, t1aggs[0]));
        assertEq(tc.t1SubmissionCID(1, 0, t1aggs[0]), CID_A);
    }

    /// @dev issue #156 M-1's actual hardening: the commit hash binds
    ///      msg.sender, so an aggregator who copies a peer's *commit hash*
    ///      verbatim (observable on-chain the moment the peer commits)
    ///      cannot later reveal the peer's (cid, salt) under their own
    ///      address -- the hash the contract recomputes at reveal time
    ///      includes the revealer's own address, which won't match what the
    ///      copier stored. Without this binding (issue #156's original
    ///      `keccak256(cid, salt)` proposal), this reveal would succeed.
    function test_copyAttack_replayingPeerCommitHash_cannotReveal() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        address honest = t1aggs[0];
        address copier = t1aggs[1];

        bytes32 honestCommitHash = _t1CommitHash(honest, CID_A, TEST_SALT, 0);
        vm.prank(honest);
        tc.commitT1Aggregation(1, 0, honestCommitHash);

        // Copier submits the exact same commit hash bytes as their own commit.
        vm.prank(copier);
        tc.commitT1Aggregation(1, 0, honestCommitHash);

        _openT1RevealPhase();

        // Honest party can reveal their own (cid, salt) fine.
        _revealT1(honest, 0, CID_A);

        // Copier tries to reveal the same (cid, salt) they saw the honest
        // party commit to -- reverts, because the hash the contract expects
        // for the copier's own reveal includes the copier's address, not
        // the honest party's.
        vm.prank(copier);
        vm.expectRevert(TC_T1RevealHashMismatch.selector);
        tc.revealT1Aggregation(1, 0, CID_A, TEST_SALT);
    }

    function test_reveal_beforeRevealPhase_reverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);

        // Still in the commit phase (T1AggregationStarted) -- reveal must
        // not be accepted yet, the entire point of the two-phase split.
        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1RevealPhaseNotOpen.selector);
        tc.revealT1Aggregation(1, 0, CID_A, TEST_SALT);
    }

    function test_reveal_withoutPriorCommit_reverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _openT1RevealPhase();

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1NoCommitFound.selector);
        tc.revealT1Aggregation(1, 0, CID_A, TEST_SALT);
    }

    function test_reveal_wrongCID_reverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);
        _openT1RevealPhase();

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1RevealHashMismatch.selector);
        tc.revealT1Aggregation(1, 0, CID_B, TEST_SALT);
    }

    function test_reveal_wrongSalt_reverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);
        _openT1RevealPhase();

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1RevealHashMismatch.selector);
        tc.revealT1Aggregation(1, 0, CID_A, bytes32(uint256(999)));
    }

    function test_commit_duringCommitPhase_twiceReverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1AlreadyCommitted.selector);
        tc.commitT1Aggregation(1, 0, _t1CommitHash(t1aggs[0], CID_B, TEST_SALT, 0));
    }

    function test_commit_zeroHashReverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_T1EmptyCommitHash.selector);
        tc.commitT1Aggregation(1, 0, bytes32(0));
    }

    function test_reveal_twiceReverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);
        _openT1RevealPhase();
        _revealT1(t1aggs[0], 0, CID_A);

        vm.prank(t1aggs[0]);
        vm.expectRevert(TC_AlreadySubmitted.selector);
        tc.revealT1Aggregation(1, 0, CID_A, TEST_SALT);
    }

    function test_finalize_beforeRevealStarted_reverts() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);

        _commitT1(t1aggs[0], 0, CID_A);
        _commitT1(t1aggs[1], 0, CID_A);

        // Still T1AggregationStarted (commit phase) -- finalize now requires
        // T1AggregationRevealStarted.
        vm.prank(modelOwner);
        vm.expectRevert(TC_NotReadyToFinalizeT1.selector);
        tc.finalizeT1Aggregation(1);
    }

    // ─────────────────────────────────────────────────────────────────────
    // T2 negative paths -- same guards as T1 above, plus T2's single-batch
    // (batchId == 0) check. The T1 fixture's other 3 aggregators form the
    // T2 batch.
    // ─────────────────────────────────────────────────────────────────────

    function _t2CommitHash(address who, bytes32 cid, bytes32 salt) internal pure returns (bytes32) {
        return keccak256(abi.encode(cid, salt, who, uint(1), DINTaskCoordinator.TierKind.Tier2, uint(0)));
    }

    function _commitT2(address who, bytes32 cid) internal {
        vm.prank(who);
        tc.commitT2Aggregation(1, 0, _t2CommitHash(who, cid, TEST_SALT));
    }

    function _revealT2(address who, bytes32 cid) internal {
        vm.prank(who);
        tc.revealT2Aggregation(1, 0, cid, TEST_SALT);
    }

    function _openT2RevealPhase() internal {
        vm.prank(modelOwner);
        tc.startT2AggregationReveal(1);
    }

    /// @dev Runs T1 to T1AggregationDone (all 3 commit + reveal CID_A), then
    ///      opens the T2 commit window. Returns the T2 batch's aggregators.
    function _runToT2AggregationStarted() internal returns (address[] memory t2aggs) {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        for (uint i = 0; i < t1aggs.length; i++) _commitT1(t1aggs[i], 0, CID_A);
        _openT1RevealPhase();
        for (uint i = 0; i < t1aggs.length; i++) _revealT1(t1aggs[i], 0, CID_A);

        vm.startPrank(modelOwner);
        tc.finalizeT1Aggregation(1);
        tc.startT2Aggregation(1);
        vm.stopPrank();

        (, t2aggs, , ) = tc.getTier2Batch(1, 0);
    }

    function test_t2_copyAttack_replayingPeerCommitHash_cannotReveal() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        bytes32 honestCommitHash = _t2CommitHash(t2aggs[0], CID_B, TEST_SALT);

        vm.prank(t2aggs[0]);
        tc.commitT2Aggregation(1, 0, honestCommitHash);
        vm.prank(t2aggs[1]);
        tc.commitT2Aggregation(1, 0, honestCommitHash);

        _openT2RevealPhase();
        _revealT2(t2aggs[0], CID_B);

        vm.prank(t2aggs[1]);
        vm.expectRevert(TC_T2RevealHashMismatch.selector);
        tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
    }

    function test_t2_reveal_beforeRevealPhase_reverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _commitT2(t2aggs[0], CID_B);

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2RevealPhaseNotOpen.selector);
        tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
    }

    function test_t2_reveal_withoutPriorCommit_reverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _openT2RevealPhase();

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2NoCommitFound.selector);
        tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
    }

    function test_t2_reveal_wrongCIDOrSalt_reverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _commitT2(t2aggs[0], CID_B);
        _openT2RevealPhase();

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2RevealHashMismatch.selector);
        tc.revealT2Aggregation(1, 0, CID_A, TEST_SALT);

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2RevealHashMismatch.selector);
        tc.revealT2Aggregation(1, 0, CID_B, bytes32(uint256(999)));
    }

    function test_t2_commit_twiceReverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _commitT2(t2aggs[0], CID_B);

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2AlreadyCommitted.selector);
        tc.commitT2Aggregation(1, 0, _t2CommitHash(t2aggs[0], CID_A, TEST_SALT));
    }

    function test_t2_commit_zeroHashReverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_T2EmptyCommitHash.selector);
        tc.commitT2Aggregation(1, 0, bytes32(0));
    }

    function test_t2_reveal_twiceReverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _commitT2(t2aggs[0], CID_B);
        _openT2RevealPhase();
        _revealT2(t2aggs[0], CID_B);

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_AlreadySubmitted.selector);
        tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
    }

    function test_t2_finalize_beforeRevealStarted_reverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();
        _commitT2(t2aggs[0], CID_B);
        _commitT2(t2aggs[1], CID_B);

        vm.prank(modelOwner);
        vm.expectRevert(TC_NotReadyToFinalizeT2.selector);
        tc.finalizeT2Aggregation(1);
    }

    function test_t2_nonZeroBatchId_reverts() public {
        address[] memory t2aggs = _runToT2AggregationStarted();

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_OnlyOneTier2Batch.selector);
        tc.commitT2Aggregation(1, 1, _t2CommitHash(t2aggs[0], CID_B, TEST_SALT));

        _commitT2(t2aggs[0], CID_B);
        _openT2RevealPhase();

        vm.prank(t2aggs[0]);
        vm.expectRevert(TC_OnlyOneTier2Batch.selector);
        tc.revealT2Aggregation(1, 1, CID_B, TEST_SALT);
    }

    /// @dev A committed-but-never-revealed aggregator must be excluded from
    ///      finalization exactly like a non-participant, and remain
    ///      slashable via the existing slashAggregators() "no submission"
    ///      (S2) check -- no special-casing needed for the non-reveal case.
    function test_commitButNeverReveal_isS2Slashed() public {
        _runToT1AggregationStarted();
        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        assertEq(t1aggs.length, 3, "sanity: T1 batch should have 3 aggregators");

        // All 3 commit, but only 2 ever reveal -- quorum (2 of 3) still met.
        _commitT1(t1aggs[0], 0, CID_A);
        _commitT1(t1aggs[1], 0, CID_A);
        _commitT1(t1aggs[2], 0, CID_A);

        _openT1RevealPhase();
        _revealT1(t1aggs[0], 0, CID_A);
        _revealT1(t1aggs[1], 0, CID_A);
        // t1aggs[2] committed but never reveals.

        vm.prank(modelOwner);
        tc.finalizeT1Aggregation(1);
        assertTrue(tc.t1Submitted(1, 0, t1aggs[0]));
        assertFalse(tc.t1Submitted(1, 0, t1aggs[2]), "committed but never revealed -- excluded like a non-participant");

        // Run T2 to completion too (the fixture's other 3 aggregators form a
        // real T2 batch, not a trivial empty one) so slashAuditors/
        // slashAggregators become callable.
        vm.prank(modelOwner);
        tc.startT2Aggregation(1);
        (, address[] memory t2aggs, , ) = tc.getTier2Batch(1, 0);
        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.commitT2Aggregation(
                1, 0,
                keccak256(abi.encode(CID_B, TEST_SALT, t2aggs[i], uint(1), DINTaskCoordinator.TierKind.Tier2, uint(0)))
            );
        }
        vm.prank(modelOwner);
        tc.startT2AggregationReveal(1);
        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
        }

        vm.startPrank(modelOwner);
        tc.finalizeT2Aggregation(1);
        tc.slashAuditors(1);
        vm.stopPrank();

        uint256 stakeBefore = stake.getStake(t1aggs[2]);
        vm.prank(modelOwner);
        tc.slashAggregators(1);
        uint256 stakeAfter = stake.getStake(t1aggs[2]);

        assertLt(stakeAfter, stakeBefore, "committed-but-never-revealed aggregator must be S2-slashed");
        // The 2 who revealed and matched consensus keep their full stake.
        assertEq(stake.getStake(t1aggs[0]), 10 ether);
        assertEq(stake.getStake(t1aggs[1]), 10 ether);
    }

    // ─────────────────────────────────────────────────────────────────────
    // Full-GI walk through the new T1/T2 reveal states.
    // ─────────────────────────────────────────────────────────────────────

    function test_fullGI_walksThroughT1AndT2RevealStates() public {
        _runToT1AggregationStarted();
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T1AggregationStarted));

        (, address[] memory t1aggs, , , ) = tc.getTier1Batch(1, 0);
        _commitT1(t1aggs[0], 0, CID_A);
        _commitT1(t1aggs[1], 0, CID_A);
        _commitT1(t1aggs[2], 0, CID_A);

        _openT1RevealPhase();
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T1AggregationRevealStarted));

        _revealT1(t1aggs[0], 0, CID_A);
        _revealT1(t1aggs[1], 0, CID_A);
        _revealT1(t1aggs[2], 0, CID_A);

        vm.prank(modelOwner);
        tc.finalizeT1Aggregation(1);
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T1AggregationDone));

        vm.prank(modelOwner);
        tc.startT2Aggregation(1);
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T2AggregationStarted));

        (, address[] memory t2aggs, , ) = tc.getTier2Batch(1, 0);
        assertEq(t2aggs.length, 3, "sanity: remaining 3 aggregators form the T2 batch");
        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.commitT2Aggregation(
                1, 0,
                keccak256(abi.encode(CID_B, TEST_SALT, t2aggs[i], uint(1), DINTaskCoordinator.TierKind.Tier2, uint(0)))
            );
        }

        vm.prank(modelOwner);
        tc.startT2AggregationReveal(1);
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T2AggregationRevealStarted));

        for (uint i = 0; i < t2aggs.length; i++) {
            vm.prank(t2aggs[i]);
            tc.revealT2Aggregation(1, 0, CID_B, TEST_SALT);
        }

        vm.prank(modelOwner);
        tc.finalizeT2Aggregation(1);
        assertEq(uint8(tc.GIstate()), uint8(GIstates.T2AggregationDone));

        (, , bool finalized, bytes32 finalCID) = tc.getTier2Batch(1, 0);
        assertTrue(finalized);
        assertEq(finalCID, CID_B);
    }
}
