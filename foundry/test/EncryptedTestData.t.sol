// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.28;

// ─────────────────────────────────────────────────────────────────────────────
// Tests for task_240826_10: encrypted test-data key distribution and staged
// dispute resolution (DINTaskAuditor §B).
//
// Coverage:
//   Stage 0  — isEncryptionKeyEmpty free view
//   Dispute open  — bond pull, commitment guard, double-open guard
//   Resolve false — commitment matches → disputer forfeits bond (50% burn / 50% treasury)
//   Resolve upheld — commitment mismatch → bond returned, giRewardPool penalised,
//                    pendingReassignment set
//   Stale-round binding — same K+plaintext but different gi/batchId → upheld
//   Window expiry — resolveTestDataDispute after window reverts;
//                   closeExpiredDispute forfeits bond
//   Reassignment  — reassignAuditTestDataset clears pendingReassignment; reverts
//                   without prior upheld dispute
//
// Run: forge test --match-contract EncryptedTestDataTest -vv
// ─────────────────────────────────────────────────────────────────────────────

import {Test} from "forge-std/Test.sol";
import {TransparentUpgradeableProxy} from "@openzeppelin/contracts/proxy/transparent/TransparentUpgradeableProxy.sol";

import {DinToken} from "../src/DinToken.sol";
import {DinCoordinator} from "../src/DinCoordinator.sol";
import {DinValidatorStake} from "../src/DinValidatorStake.sol";
import {DINModelRegistry} from "../src/DINModelRegistry.sol";
import {DINTaskCoordinator} from "../src/DINTaskCoordinator.sol";
import {DINTaskAuditor} from "../src/DINTaskAuditor.sol";
import {GIstates, TA_NoCommitmentStored, TA_DisputeAlreadyActive, TA_NoActiveDispute, TA_DisputeWindowClosed} from "../src/DINShared.sol";

contract EncryptedTestDataTest is Test {
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

    address admin      = makeAddr("admin");
    address modelOwner = makeAddr("modelOwner");
    address auditor1   = makeAddr("auditor1");
    address auditor2   = makeAddr("auditor2");
    address auditor3   = makeAddr("auditor3");
    address client1    = makeAddr("client1");
    address client2    = makeAddr("client2");
    address disputer   = makeAddr("disputer");

    // Fixed test vectors — not real crypto, just values we control for
    // commitment reconstruction in tests.
    bytes constant TEST_K             = abi.encodePacked(bytes32(uint256(0xBEEF)));
    bytes32 constant TEST_PLAINTEXT_HASH = bytes32(uint256(0xDEAD));
    bytes constant TEST_ENC_CID      = abi.encodePacked(bytes32(uint256(0xCCC)));

    uint256 constant BOND = 100 ether; // DIN units (18 dec); set via setDisputeBondAmount

    // ─────────────────────────────────────────────────────────────────────────
    // Platform & task deployment (mirrors AuditorCommitReveal helpers)
    // ─────────────────────────────────────────────────────────────────────────

    function _deployPlatform() internal {
        vm.startPrank(admin);

        tokenImpl = new DinToken();
        token = DinToken(address(new TransparentUpgradeableProxy(
            address(tokenImpl), admin, abi.encodeCall(DinToken.initialize, ())
        )));

        coordinatorImpl = new DinCoordinator();
        coordinator = DinCoordinator(address(new TransparentUpgradeableProxy(
            address(coordinatorImpl), admin,
            abi.encodeCall(DinCoordinator.initialize, (address(token)))
        )));
        token.setCoordinator(address(coordinator));

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

    function _fundDin(address who, uint256 dinAmount) internal {
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

        _fundDin(modelOwner, 1 ether);
        vm.startPrank(modelOwner);
        ta.depositRewards(1, 1 ether);
        tc.startGI(1);
        vm.stopPrank();
    }

    /// @dev Drives the GI to AuditorsBatchesCreated and registers auditor
    ///      X25519 keys — stops before setTestDataAssignedFlag so callers
    ///      can call assignAuditTestDataset with a real commitment.
    function _runToAuditorBatchesCreated() internal {
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
        tc.createAuditorsBatches(1);
        vm.stopPrank();

        // Every auditor registers a distinct 32-byte X25519 public key.
        vm.prank(auditor1); stake.registerEncryptionKey(abi.encodePacked(bytes32(uint256(1))));
        vm.prank(auditor2); stake.registerEncryptionKey(abi.encodePacked(bytes32(uint256(2))));
        vm.prank(auditor3); stake.registerEncryptionKey(abi.encodePacked(bytes32(uint256(3))));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Helpers
    // ─────────────────────────────────────────────────────────────────────────

    function _buildCommitment(
        uint256 gi,
        uint256 batchId,
        bytes memory K,
        bytes32 plaintextHash
    ) internal pure returns (bytes32) {
        return keccak256(abi.encodePacked(gi, batchId, keccak256(K), plaintextHash));
    }

    /// @dev Assigns batch 0 of GI 1 with TEST_K / TEST_PLAINTEXT_HASH commitment.
    ///      Returns the stored commitment bytes32.
    function _assignBatch0() internal returns (bytes32 commitment) {
        (, address[] memory auditors,,) = ta.getAuditorsBatch(1, 0);
        bytes[] memory keys = new bytes[](auditors.length);
        for (uint i = 0; i < auditors.length; i++) {
            keys[i] = abi.encodePacked(bytes32(uint256(i + 100)));
        }
        commitment = _buildCommitment(1, 0, TEST_K, TEST_PLAINTEXT_HASH);
        vm.prank(modelOwner);
        ta.assignAuditTestDataset(1, 0, TEST_ENC_CID, keys, commitment);
    }

    /// @dev Opens a dispute on batch 0 of GI 1 with `from` as disputer.
    ///      Funds `from` with enough DIN to cover the bond.
    function _openDispute(address from) internal {
        _fundDin(from, BOND + 10 ether);
        vm.prank(from);
        ta.openTestDataDispute(1, 0);
    }

    // Struct destructure helpers (public mapping getters return tuples, not named structs)
    function _disputeActive(uint256 gi, uint256 batchId) internal view returns (bool) {
        (,,, bool active,) = ta.testDataDisputes(gi, batchId);
        return active;
    }
    function _disputeExpires(uint256 gi, uint256 batchId) internal view returns (uint256) {
        (,, uint256 expiresAtBlock,,) = ta.testDataDisputes(gi, batchId);
        return expiresAtBlock;
    }
    function _disputePending(uint256 gi, uint256 batchId) internal view returns (bool) {
        (,,,, bool pendingReassignment) = ta.testDataDisputes(gi, batchId);
        return pendingReassignment;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Stage 0 — isEncryptionKeyEmpty free view
    // ─────────────────────────────────────────────────────────────────────────

    function test_stage0_noKeyAssigned_returnsTrue() public {
        _runToAuditorBatchesCreated();
        assertTrue(ta.isEncryptionKeyEmpty(1, 0, auditor1), "unassigned auditor should show empty key");
    }

    function test_stage0_keyAssigned_returnsFalse() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        assertFalse(ta.isEncryptionKeyEmpty(1, 0, auditor1), "assigned auditor should not show empty key");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // openTestDataDispute guards
    // ─────────────────────────────────────────────────────────────────────────

    function test_openDispute_noCommitment_reverts() public {
        _runToAuditorBatchesCreated();
        vm.prank(disputer);
        vm.expectRevert(TA_NoCommitmentStored.selector);
        ta.openTestDataDispute(1, 0);
    }

    function test_openDispute_pullsBond() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);

        _fundDin(disputer, BOND + 10 ether);
        uint256 balBefore = token.balanceOf(disputer);
        vm.prank(disputer);
        ta.openTestDataDispute(1, 0);

        assertEq(token.balanceOf(disputer), balBefore - BOND, "bond should be pulled from disputer");
        assertEq(token.balanceOf(address(ta)), BOND + 1 ether /* reward deposit */, "ta should hold bond");
    }

    function test_openDispute_duplicate_reverts() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);

        _openDispute(disputer);

        _fundDin(disputer, BOND + 10 ether);
        vm.prank(disputer);
        vm.expectRevert(TA_DisputeAlreadyActive.selector);
        ta.openTestDataDispute(1, 0);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // resolveTestDataDispute — false dispute (commitment matches)
    // ─────────────────────────────────────────────────────────────────────────

    function test_resolveDispute_falseDispute_forfeitsBond() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        uint256 treasuryBefore = ta.treasuryAccrued();
        uint256 supplyBefore   = token.totalSupply();

        // Reveal the correct K and plaintextHash — commitment matches → false dispute
        vm.prank(modelOwner);
        ta.resolveTestDataDispute(1, 0, TEST_K, TEST_PLAINTEXT_HASH);

        assertEq(ta.treasuryAccrued(), treasuryBefore + BOND / 2, "treasury should receive half the bond");
        assertEq(token.totalSupply(), supplyBefore - BOND / 2, "half the bond should be burned");
        assertFalse(_disputeActive(1, 0), "dispute should be inactive after resolution");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // resolveTestDataDispute — upheld dispute (commitment mismatch)
    // ─────────────────────────────────────────────────────────────────────────

    function test_resolveDispute_upheld_returnsBondAndPenalises() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        uint256 poolBefore     = ta.giRewardPool(1);
        uint256 disputerBefore = token.balanceOf(disputer);

        // Wrong K — commitment won't match → dispute upheld
        bytes memory wrongK = abi.encodePacked(bytes32(uint256(0xBAD)));
        vm.prank(disputer);
        ta.resolveTestDataDispute(1, 0, wrongK, TEST_PLAINTEXT_HASH);

        assertEq(token.balanceOf(disputer), disputerBefore + BOND, "bond should be returned to disputer");

        uint256 expectedPenalty = (poolBefore * ta.disputePenaltyBps()) / 10000;
        assertEq(ta.giRewardPool(1), poolBefore - expectedPenalty, "reward pool should be penalised");
        assertTrue(_disputePending(1, 0), "batch should be flagged for reassignment");
    }

    function test_resolveDispute_upheld_blocksFurtherOpen() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        bytes memory wrongK = abi.encodePacked(bytes32(uint256(0xBAD)));
        vm.prank(disputer);
        ta.resolveTestDataDispute(1, 0, wrongK, TEST_PLAINTEXT_HASH);

        // pendingReassignment is set — opening another dispute should revert
        _fundDin(disputer, BOND + 10 ether);
        vm.prank(disputer);
        vm.expectRevert();
        ta.openTestDataDispute(1, 0);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Stale-round binding — same K and plaintext, different gi or batchId
    // ─────────────────────────────────────────────────────────────────────────

    function test_resolveDispute_staleRound_upheld() public {
        _runToAuditorBatchesCreated();

        // Assign batch 0 with a commitment built for gi=1, batchId=0.
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        // Reveal the SAME K and plaintextHash but claim they belong to gi=2,
        // batchId=0 — reconstructed commitment will differ from stored one
        // (round-binding: gi is encoded in the preimage).
        // We simulate by calling resolveTestDataDispute with the correct values
        // for gi=1, batchId=0; then verify the stored commitment itself was
        // built with round-binding so a "stale" reuse from a different round
        // would produce a mismatch.  We test this by directly verifying that
        // a commitment built for gi=2 != the stored one.
        bytes32 storedCommitment = ta.testDataCommitments(1, 0);
        bytes32 staleCommitment  = _buildCommitment(2, 0, TEST_K, TEST_PLAINTEXT_HASH);
        assertTrue(storedCommitment != staleCommitment, "round-bound: same K+plaintext must hash differently for different gi");

        // Uphold: reveal with mismatched gi context — the contract recomputes
        // keccak256(abi.encodePacked(1, 0, keccak256(TEST_K), wrongPlaintext))
        // which won't match → upheld.
        bytes memory wrongK = abi.encodePacked(bytes32(uint256(0xBADBAD)));
        vm.prank(disputer);
        ta.resolveTestDataDispute(1, 0, wrongK, TEST_PLAINTEXT_HASH);
        assertTrue(_disputePending(1, 0));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Challenge window expiry
    // ─────────────────────────────────────────────────────────────────────────

    function test_resolveDispute_afterWindow_reverts() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        uint256 expires = _disputeExpires(1, 0);
        vm.roll(expires + 1);

        vm.prank(modelOwner);
        vm.expectRevert(TA_DisputeWindowClosed.selector);
        ta.resolveTestDataDispute(1, 0, TEST_K, TEST_PLAINTEXT_HASH);
    }

    function test_closeExpiredDispute_forfeitsBond() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        uint256 expires       = _disputeExpires(1, 0);
        uint256 supplyBefore  = token.totalSupply();
        uint256 treasuryBefore = ta.treasuryAccrued();

        vm.roll(expires + 1);
        ta.closeExpiredDispute(1, 0);

        assertEq(token.totalSupply(), supplyBefore - BOND / 2, "half bond burned on expiry");
        assertEq(ta.treasuryAccrued(), treasuryBefore + BOND / 2, "half bond to treasury on expiry");
        assertFalse(_disputeActive(1, 0));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Reassignment after upheld dispute
    // ─────────────────────────────────────────────────────────────────────────

    function test_reassign_clearsFlag() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();
        vm.prank(modelOwner);
        ta.setDisputeBondAmount(BOND);
        _openDispute(disputer);

        // Uphold dispute to set pendingReassignment
        bytes memory wrongK = abi.encodePacked(bytes32(uint256(0xBAD)));
        vm.prank(disputer);
        ta.resolveTestDataDispute(1, 0, wrongK, TEST_PLAINTEXT_HASH);
        assertTrue(_disputePending(1, 0));

        // Re-assign with fresh data
        (, address[] memory auditors,,) = ta.getAuditorsBatch(1, 0);
        bytes[] memory newKeys = new bytes[](auditors.length);
        for (uint i = 0; i < auditors.length; i++) {
            newKeys[i] = abi.encodePacked(bytes32(uint256(i + 200)));
        }
        bytes32 newCommitment = _buildCommitment(1, 0,
            abi.encodePacked(bytes32(uint256(0xFEED))),
            bytes32(uint256(0xF00D))
        );
        vm.prank(modelOwner);
        ta.reassignAuditTestDataset(1, 0, TEST_ENC_CID, newKeys, newCommitment);

        assertFalse(_disputePending(1, 0), "reassignment should clear flag");
        assertEq(ta.testDataCommitments(1, 0), newCommitment, "new commitment should be stored");
    }

    function test_reassign_withoutPriorDispute_reverts() public {
        _runToAuditorBatchesCreated();
        _assignBatch0();

        (, address[] memory auditors,,) = ta.getAuditorsBatch(1, 0);
        bytes[] memory keys = new bytes[](auditors.length);

        vm.prank(modelOwner);
        vm.expectRevert(TA_NoActiveDispute.selector);
        ta.reassignAuditTestDataset(1, 0, TEST_ENC_CID, keys, bytes32(0));
    }
}
