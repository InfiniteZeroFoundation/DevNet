// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Contract-level tests for task_210726_6 Part 2 (auditor evaluation mechanism,
// issue #40): commit-then-reveal auditor scoring and the per-validator
// encrypted test-data key mapping.
// Run: forge test --match-contract AuditorCommitRevealTest -vv
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

contract AuditorCommitRevealTest is Test {
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

    // Fixed salt for every commit in this suite. Salt secrecy only matters
    // for hiding a score from OTHER auditors during the live commit window;
    // these tests aren't testing that property (see
    // test_reveal_scoreMismatchWithCommit_reverts and
    // test_reveal_beforeRevealPhase_reverts below, which DO exercise
    // secrecy-adjacent behavior -- a fixed salt doesn't undermine either,
    // since nothing in the contract ever reads salt before the matching
    // reveal call).
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
        _fundDinBalance(modelOwner, 1 ether);
        vm.startPrank(modelOwner);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    /// @dev Drives the GI to LMSevaluationStarted (the commit-phase state)
    ///      with exactly one audit batch (3 auditors, demo auditorsPerBatch)
    ///      and two submitted models (MIN_MODELS_PER_BATCH=2 is the floor
    ///      for a batch to form at all), WITHOUT committing or revealing any
    ///      scores -- callers drive commit/reveal themselves.
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
    // Commit-then-reveal helpers (§2a). `_openRevealPhase` is the
    // model-owner action closing commits and opening reveals.
    // ─────────────────────────────────────────────────────────────────────

    function _commitScore(address who, uint gi, uint batchId, uint modelIdx, uint256 score, bool vote) internal {
        bytes32 hash = keccak256(abi.encodePacked(score, vote, TEST_SALT));
        vm.prank(who);
        ta.commitAuditScore(gi, batchId, modelIdx, hash);
    }

    function _revealScore(address who, uint gi, uint batchId, uint modelIdx, uint256 score, bool vote) internal {
        vm.prank(who);
        ta.revealAuditScore(gi, batchId, modelIdx, score, vote, TEST_SALT);
    }

    function _openRevealPhase(uint gi) internal {
        vm.prank(modelOwner);
        tc.startLMsubmissionsEvaluationReveal(gi);
    }

    // ─────────────────────────────────────────────────────────────────────
    // §2a: commit-then-reveal correctness and anti-copying properties.
    // ─────────────────────────────────────────────────────────────────────

    function test_commitReveal_happyPath_scoreCountedAfterReveal() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);
        _openRevealPhase(1);
        _revealScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);

        assertTrue(ta.hasAuditedLM(1, 0, batchAuditors[0], modelIdxs[0]));
        assertEq(ta.auditScores(1, 0, batchAuditors[0], modelIdxs[0]), 80);
    }

    function test_reveal_beforeRevealPhase_reverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);

        // Still in the commit phase (LMSevaluationStarted) -- reveal must not
        // be accepted yet, which is the entire point of the two-phase split:
        // an auditor who hasn't committed yet must never be able to see a
        // revealed score from someone who already has.
        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_RevealPhaseNotOpen
        ta.revealAuditScore(1, 0, modelIdxs[0], 80, true, TEST_SALT);
    }

    function test_reveal_withoutPriorCommit_reverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _openRevealPhase(1);

        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_NoCommitFound
        ta.revealAuditScore(1, 0, modelIdxs[0], 80, true, TEST_SALT);
    }

    function test_reveal_scoreMismatchWithCommit_reverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // Commit to 80, but try to reveal 95 -- the exact "copy a better
        // score after seeing someone else reveal" attack commit-reveal
        // exists to prevent; the hash simply won't match.
        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);
        _openRevealPhase(1);

        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_RevealHashMismatch
        ta.revealAuditScore(1, 0, modelIdxs[0], 95, true, TEST_SALT);
    }

    function test_reveal_wrongSalt_reverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);
        _openRevealPhase(1);

        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_RevealHashMismatch
        ta.revealAuditScore(1, 0, modelIdxs[0], 80, true, bytes32(uint256(999)));
    }

    function test_commit_duringCommitPhase_twiceReverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);

        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_AlreadyCommitted
        ta.commitAuditScore(1, 0, modelIdxs[0], keccak256(abi.encodePacked(uint256(90), true, TEST_SALT)));
    }

    function test_reveal_twiceReverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);
        _openRevealPhase(1);
        _revealScore(batchAuditors[0], 1, 0, modelIdxs[0], 80, true);

        vm.prank(batchAuditors[0]);
        vm.expectRevert(); // TA_AlreadyVoted
        ta.revealAuditScore(1, 0, modelIdxs[0], 80, true, TEST_SALT);
    }

    function test_commitButNeverReveal_excludedFromQuorumNotCorrupting() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, uint[] memory modelIdxs, ) = ta.getAuditorsBatch(1, 0);

        // All 3 commit, but only 2 ever reveal -- the non-revealer must not
        // silently corrupt quorum/median counting (task_210726_6 §2a).
        _commitScore(batchAuditors[0], 1, 0, modelIdxs[0], 40, true);
        _commitScore(batchAuditors[1], 1, 0, modelIdxs[0], 60, true);
        _commitScore(batchAuditors[2], 1, 0, modelIdxs[0], 100, true);

        _openRevealPhase(1);
        _revealScore(batchAuditors[0], 1, 0, modelIdxs[0], 40, true);
        _revealScore(batchAuditors[1], 1, 0, modelIdxs[0], 60, true);
        // batchAuditors[2] committed but never reveals.

        vm.prank(modelOwner);
        tc.closeLMsubmissionsEvaluation(1);

        // Average of the 2 REVEALED scores [40,60] = 50, not influenced by
        // the un-revealed 100 in any way -- proves the non-revealer is
        // excluded from counting exactly like a total non-participant, with
        // no special-casing required. (This branch predates Part 1's
        // mean->median fix -- see PR #62 -- so the arithmetic here is still
        // a mean; the counting-exclusion property under test is identical
        // either way.)
        (, , , , , , uint256 finalScore) = ta.lmSubmissions(1, modelIdxs[0]);
        assertEq(finalScore, 50);
        assertTrue(ta.hasCommittedLM(1, 0, batchAuditors[2], modelIdxs[0]), "committed");
        assertFalse(ta.hasAuditedLM(1, 0, batchAuditors[2], modelIdxs[0]), "but never revealed/counted");
    }

    // ─────────────────────────────────────────────────────────────────────
    // §2b: per-validator encrypted test-data key mapping.
    // ─────────────────────────────────────────────────────────────────────

    function test_assignAuditTestDataset_populatesPerAuditorKeys() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, , ) = ta.getAuditorsBatch(1, 0);

        bytes[] memory keys = new bytes[](batchAuditors.length);
        for (uint i = 0; i < batchAuditors.length; i++) {
            keys[i] = abi.encodePacked("encrypted-key-for-", batchAuditors[i]);
        }

        vm.prank(modelOwner);
        ta.assignAuditTestDataset(1, 0, bytes32(uint256(0xDA7A)), keys);

        for (uint i = 0; i < batchAuditors.length; i++) {
            assertEq(
                ta.encryptedTestDataKey(1, 0, batchAuditors[i]),
                keys[i],
                "each auditor's own encrypted key should be stored, matching batch order"
            );
        }

        (, , , bytes32 testDataCID) = ta.getAuditorsBatch(1, 0);
        assertEq(testDataCID, bytes32(uint256(0xDA7A)));
    }

    function test_assignAuditTestDataset_keyCountMismatchReverts() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, , ) = ta.getAuditorsBatch(1, 0);

        bytes[] memory tooFewKeys = new bytes[](batchAuditors.length - 1);
        for (uint i = 0; i < tooFewKeys.length; i++) {
            tooFewKeys[i] = "key";
        }

        vm.prank(modelOwner);
        vm.expectRevert(); // TA_EncryptedKeyCountMismatch
        ta.assignAuditTestDataset(1, 0, bytes32(uint256(0xDA7A)), tooFewKeys);
    }

    function test_assignAuditTestDataset_onlyOwner() public {
        _runToLMSevaluationStarted();
        (, address[] memory batchAuditors, , ) = ta.getAuditorsBatch(1, 0);
        bytes[] memory keys = new bytes[](batchAuditors.length);

        vm.prank(auditor1); // not the model owner
        vm.expectRevert();
        ta.assignAuditTestDataset(1, 0, bytes32(uint256(0xDA7A)), keys);
    }

    function test_assignAuditTestDataset_unassignedAuditorHasEmptyKey() public {
        _runToLMSevaluationStarted();
        // Nothing assigned at all -- an address with no key should read back
        // as the zero-length default, not revert or return garbage.
        assertEq(ta.encryptedTestDataKey(1, 0, auditor1).length, 0);
    }
}
